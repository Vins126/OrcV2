"""Scarica le skill fissate nel manifesto per costruire l'immagine sandbox."""

import argparse
from collections.abc import Callable, Iterable
import io
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import tarfile
from urllib.request import urlopen

from tools.load_skill import SkillCatalogError, SkillEntry, load_catalog


def _download(repo: str, commit: str) -> bytes:
    """Legge l'archivio del commit da GitHub con un tempo massimo esplicito."""
    with urlopen(f"https://codeload.github.com/{repo}/tar.gz/{commit}", timeout=60) as response:
        return response.read()


def _inside(folder: Path, relative: str) -> Path:
    """Controlla anche eventuali link gia' presenti prima di usare un percorso."""
    target = folder / relative
    if not target.resolve().is_relative_to(folder):
        raise SkillCatalogError(f"percorso fuori dalla skill: '{relative}'")
    return target


def _extract(archive: tarfile.TarFile, entry: SkillEntry, folder: Path) -> None:
    """Estrae solo la sottocartella scelta, senza seguire link durante la copia."""
    skill_path = PurePosixPath(entry.path)
    if skill_path.is_absolute() or ".." in skill_path.parts or not skill_path.parts:
        raise SkillCatalogError(f"skill '{entry.name}': percorso sorgente non valido")
    members = archive.getmembers()
    roots: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        normalized = PurePosixPath(posixpath.normpath(member.name))
        if path.is_absolute() or not path.parts or not normalized.parts or normalized.parts[0] == "..":
            raise SkillCatalogError(f"skill '{entry.name}': percorso archivio non sicuro: {member.name}")
        roots.add(path.parts[0])
    if len(roots) != 1:
        raise SkillCatalogError(f"skill '{entry.name}': archivio senza una sola cartella radice")
    root = next(iter(roots))
    prefix = f"{root}/{skill_path.as_posix()}/"
    selected: list[tuple[tarfile.TarInfo, str]] = []
    for member in members:
        if not member.name.startswith(prefix):
            continue
        relative = member.name[len(prefix):]
        _inside(folder, relative)
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise SkillCatalogError(f"skill '{entry.name}': tipo di file non ammesso: {member.name}")
        if member.issym():
            _inside(folder, str(PurePosixPath(relative).parent / member.linkname))
        elif member.islnk():
            link = posixpath.normpath(member.linkname)
            if not link.startswith(prefix):
                raise SkillCatalogError(f"skill '{entry.name}': hard link fuori dalla skill")
            _inside(folder, link[len(prefix):])
        selected.append((member, relative))

    # Prima i file normali: nessun contenuto viene scritto attraverso un link.
    for member, relative in selected:
        target = _inside(folder, relative)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise SkillCatalogError(f"skill '{entry.name}': file non leggibile: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)

    for member, relative in selected:
        if member.issym():
            target = _inside(folder, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(member.linkname)
    # La verifica dopo la creazione copre anche catene di link simbolici.
    for _, relative in selected:
        _inside(folder, relative)
    pending = [(member, relative) for member, relative in selected if member.islnk()]
    while pending:
        remaining: list[tuple[tarfile.TarInfo, str]] = []
        for member, relative in pending:
            source = _inside(folder, posixpath.normpath(member.linkname)[len(prefix):])
            if not source.is_file():
                remaining.append((member, relative))
                continue
            target = _inside(folder, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.hardlink_to(source)
        if len(remaining) == len(pending):
            raise SkillCatalogError(f"skill '{entry.name}': hard link senza destinazione valida")
        pending = remaining

    if not (folder / "SKILL.md").is_file():
        raise SkillCatalogError(f"skill '{entry.name}': SKILL.md assente")
    if not any(path.is_file() for path in folder.rglob("LICENSE*")):
        for member in members:
            path = PurePosixPath(member.name)
            if path.parent == PurePosixPath(root) and path.name.startswith("LICENSE") and member.isfile():
                source = archive.extractfile(member)
                if source is not None:
                    target = _inside(folder, path.name)
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)


def fetch_skills(entries: Iterable[SkillEntry], dest: Path, *,
                 download: Callable[[str, str], bytes] = _download) -> None:
    """Ricrea ogni cartella della skill dal suo archivio, preservando le licenze."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.name):
            raise SkillCatalogError(f"nome skill non valido: '{entry.name}'")
        folder = dest / entry.name
        try:
            if folder.is_symlink() or folder.is_file():
                folder.unlink()
            elif folder.exists():
                shutil.rmtree(folder)
            folder.mkdir()
            data = download(entry.repo, entry.commit)
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                _extract(archive, entry, folder)
        except (OSError, tarfile.TarError, RuntimeError) as error:
            raise SkillCatalogError(f"skill '{entry.name}': {error}") from error


def main() -> None:
    """Prepara le cartelle ignorate da git e stampa una riga per skill."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("docker/skills.toml"))
    parser.add_argument("--dest", type=Path, default=Path("docker/skills"))
    args = parser.parse_args()
    try:
        for entry in load_catalog(args.manifest):
            fetch_skills([entry], args.dest)
            print(f"{entry.name}: {entry.repo}@{entry.commit} -> {args.dest / entry.name}")
    except SkillCatalogError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
