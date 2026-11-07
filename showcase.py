"""Siti vivi e galleria portabile per l'autore, fuori dalla misura."""

import html
import json
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import renderer
from executors.docker import remove_container
from task_model import CampaignError

PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_PORT = 8081
SERVE_SCRIPT = PROJECT_ROOT / "docker" / "serve_site.py"


class ShowcaseError(CampaignError):
    """Manifesto, workspace o destinazione della vetrina non utilizzabile."""


def manifest_rows(manifest: Path) -> dict[str, dict]:
    """Indicizza le righe per task, saltando i metadati dell'ambiente."""
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise ShowcaseError(f"manifesto non trovato: {manifest}") from error
    except (OSError, UnicodeError) as error:
        raise ShowcaseError(f"manifesto non leggibile: {manifest}: {error}") from error
    rows: dict[str, dict] = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ShowcaseError(f"{manifest}, riga {number}: JSON non valido") from error
        if not isinstance(row, dict):
            raise ShowcaseError(f"{manifest}, riga {number}: serve un oggetto")
        if "environment" in row:
            continue
        task = row.get("task_id")
        if not isinstance(task, str) or not task:
            raise ShowcaseError(f"{manifest}, riga {number}: task_id mancante")
        if task in rows:
            raise ShowcaseError(f"task duplicato nel manifesto: {task}")
        rows[task] = row
    return rows


def serve_command(site: Path, name: str, *, host_port: int = 8080,
                  image: str = renderer.RENDERER_IMAGE,
                  server: Path = SERVE_SCRIPT) -> list[str]:
    """Pubblica il sito solo sul computer dell'autore, con i limiti del renderer."""
    return [
        "docker", "run", "--rm", "--init", "--name", name,
        "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp",
        "--memory", renderer.RENDERER_MEMORY, "--pids-limit", renderer.RENDERER_PIDS,
        "--publish", f"127.0.0.1:{host_port}:{PUBLIC_PORT}",
        "--workdir", "/workspace", "--volume", f"{site}:/workspace",
        "--volume", f"{server}:/opt/orc-serve/serve_site.py:ro", image,
        "python3", "/opt/orc-serve/serve_site.py", "--site", "/workspace",
        "--port", "8080", "--public-port", str(PUBLIC_PORT),
        "--start-timeout", str(renderer.START_TIMEOUT_S),
    ]


def serve_site(workspace: Path, *, host_port: int = 8080,
               runner: Callable[..., Any] = subprocess.run,
               image: str = renderer.RENDERER_IMAGE) -> int:
    """Serve una copia del workspace in primo piano e la cancella alla fine."""
    if not (workspace / "start.sh").is_file():
        raise ShowcaseError(f"start.sh mancante nel workspace: {workspace}")
    temporary = Path(tempfile.mkdtemp(prefix="orc-vetrina-"))
    try:
        site = temporary / "site"
        shutil.copytree(workspace, site, symlinks=True)
        name = f"orc-vetrina-{uuid.uuid4().hex[:12]}"
        print(f"http://localhost:{host_port} - Ctrl+C per fermare", flush=True)
        try:
            return runner(serve_command(site, name, host_port=host_port, image=image)).returncode
        except KeyboardInterrupt:
            remove_container(name, runner)
            return 130
    except OSError as error:
        raise ShowcaseError(f"avvio della vetrina non riuscito: {error}") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _screenshots(row: dict, arm: str, task: str, out_dir: Path) -> str:
    """Copia le immagini esistenti e restituisce solo riferimenti relativi."""
    evaluation = row.get("evaluation") or {}
    path = evaluation.get("path")
    screenshots = {}
    if path and Path(path).is_file():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        screenshots = (data.get("riservato") or {}).get("screenshots") or {}
    references: dict[str, str] = {}
    # L'identificativo resta un solo componente di percorso, anche con caratteri speciali.
    folder = quote(task, safe="").replace(".", "%2E")
    for width in ("375", "768", "1440"):
        source = screenshots.get(width)
        if source and Path(source).is_file():
            relative = Path("img") / arm / folder / f"{width}.png"
            destination = out_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            references[width] = html.escape(quote(relative.as_posix(), safe="/"), quote=True)
    if not references:
        return "<p>nessuno screenshot</p>"
    parts = []
    if "1440" in references:
        parts.append(f'<img src="{references["1440"]}" alt="Sito a 1440 pixel">')
    for width in ("375", "768"):
        if width in references:
            parts.append(f'<a href="{references[width]}">{width} pixel</a> ')
    return "".join(parts)


def _column(label: str, row: dict, campaign_id: str, task: str, pictures: str,
            *, cost: float | None = None, choice: str = "") -> str:
    """Mostra i dati del manifesto senza esporre i percorsi della valutazione."""
    gate = row.get("gate") or {}
    verdict = "accettato" if gate.get("accepted") else "rifiutato"
    reason = gate.get("reason")
    if reason:
        verdict += f": {reason}"
    score = (row.get("evaluation") or {}).get("funziona")
    command = shlex.join(["python", "campaign.py", "serve", campaign_id, task])
    total = float(row.get("total_cost") or 0) if cost is None else cost
    return (f'<article><h3>{html.escape(label)}</h3><p>{html.escape(choice)}</p>'
            f'<p>Costo: ${total:.2f}</p><p>Cancello: {html.escape(verdict)}</p>'
            f'<p>funziona: {html.escape(str(score) if score is not None else "n.d.")}</p>'
            f'<p>workspace: <code>{html.escape(str(row.get("workspace") or "n.d."))}</code></p>'
            f'<pre>{html.escape(command)}</pre>{pictures}</article>')


def build_gallery(arms: dict[str, Path], out_dir: Path) -> Path:
    """Costruisce una galleria autonoma, inclusa la cascata virtuale B/D."""
    for arm in arms:
        if arm not in {"B", "C", "D"}:
            raise ShowcaseError(f"etichetta del braccio non ammessa: {arm}")
    if out_dir.exists():
        raise ShowcaseError(f"la cartella della galleria esiste: {out_dir}")
    rows = {arm: manifest_rows(manifest) for arm, manifest in arms.items()}
    tasks = sorted({task for items in rows.values() for task in items})
    sections = []
    try:
        out_dir.mkdir(parents=True)
        for task in tasks:
            columns = []
            pictures: dict[str, str] = {}
            for arm in sorted(arms):
                row = rows[arm].get(task)
                if row is None:
                    columns.append(f"<article><h3>{arm}</h3><p>task assente</p></article>")
                    continue
                pictures[arm] = _screenshots(row, arm, task, out_dir)
                columns.append(_column(arm, row, arms[arm].stem, task, pictures[arm]))
            if "B" in arms and "D" in arms:
                baseline, cheap = rows["B"].get(task), rows["D"].get(task)
                if cheap is not None and (cheap.get("gate") or {}).get("accepted"):
                    selected = "D"
                    cost = float(cheap.get("total_cost") or 0)
                else:
                    selected = "B"
                    cost = float((cheap or {}).get("total_cost") or 0)
                    cost += float((baseline or {}).get("total_cost") or 0)
                if cheap is None or (selected == "B" and baseline is None):
                    columns.append("<article><h3>V</h3><p>cascata non disponibile</p></article>")
                else:
                    columns.append(_column("V", rows[selected][task], arms[selected].stem,
                                           task, pictures[selected], cost=cost,
                                           choice=f"V = {selected}"))
            sections.append(f'<section><h2>{html.escape(task)}</h2><div class="columns">'
                            + "".join(columns) + "</div></section>")
        page = '''<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vetrina dei siti</title><style>
:root { color-scheme: light dark; }
body { font: 16px system-ui, sans-serif; margin: 2rem; }
.columns { display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; }
article { flex: 1 1 280px; min-width: 0; padding: 1rem; border: 1px solid #888;
          border-radius: .5rem; background: #f5f5f5; color: #222; }
img { display: block; width: 100%; height: auto; margin-bottom: .5rem; }
pre, code { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (prefers-color-scheme: dark) { article { background: #222; color: #eee; } }
</style></head><body><h1>Vetrina dei siti</h1>
<p>Vista per l'autore: non entra nella misura</p>
'''
        index = out_dir / "index.html"
        index.write_text(page + "".join(sections) + "</body></html>\n", encoding="utf-8")
        return index
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError) as error:
        raise ShowcaseError(f"creazione della galleria non riuscita: {error}") from error
