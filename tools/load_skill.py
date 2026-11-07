"""Catalogo fissato delle skill e caricamento delle istruzioni dalla sandbox."""

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Protocol

from tools.base import Tool


SKILLS_ROOT = "/opt/skills"

# P45-D1, 7 nov 2026: design a chi decide lo stile, lavoro e verifica a chi
# scrive codice; i bracci con un solo agente ricevono l'unione.
REQUIRED_SKILLS_SINGLE: tuple[str, ...] = (
    "frontend-design", "design-taste-frontend", "webapp-testing", "verification-before-completion",
)
REQUIRED_SKILLS_PLANNER: tuple[str, ...] = ("frontend-design", "design-taste-frontend")
REQUIRED_SKILLS_WORKER: tuple[str, ...] = (
    "frontend-design", "webapp-testing", "verification-before-completion",
)


class SkillCatalogError(Exception):
    """Catalogo o archivio di una skill assente, incompleto o non sicuro."""


class _SkillExecutor(Protocol):
    """Contratto minimo: basta esporre run, anche negli esecutori dei test."""

    def run(self, command: str) -> dict:
        """Restituisce stdout, stderr ed exit_code del comando."""
        ...


@dataclass(frozen=True)
class SkillEntry:
    """Origine, licenza e descrizione breve di una skill della campagna."""

    name: str
    repo: str
    commit: str
    path: str
    license: str
    description: str


def load_catalog(path: str | Path) -> list[SkillEntry]:
    """Legge e valida il manifesto, senza accessi al disco all'import."""
    try:
        with Path(path).open("rb") as source:
            manifest = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SkillCatalogError(f"catalogo '{path}' non leggibile: {error}") from error
    rows = manifest.get("skills")
    if not isinstance(rows, list) or not rows:
        raise SkillCatalogError("catalogo senza tabelle [[skills]]")
    entries: list[SkillEntry] = []
    names: set[str] = set()
    fields = ("name", "repo", "commit", "path", "license", "description")
    for row in rows:
        if not isinstance(row, dict):
            raise SkillCatalogError("voce del catalogo non valida")
        for field in fields:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SkillCatalogError(f"skill {row.get('name', '?')}: campo '{field}' mancante o vuoto")
        entry = SkillEntry(**{field: row[field] for field in fields})
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.name):
            raise SkillCatalogError(f"nome skill non valido: '{entry.name}'")
        if not re.fullmatch(r"[0-9a-f]{40}", entry.commit):
            raise SkillCatalogError(f"skill '{entry.name}': commit non valido, servono 40 hex minuscoli")
        if entry.name in names:
            raise SkillCatalogError(f"nome skill duplicato: '{entry.name}'")
        if len(entry.description) > 300:
            raise SkillCatalogError(f"skill '{entry.name}': descrizione oltre 300 caratteri")
        names.add(entry.name)
        entries.append(entry)
    return entries


class LoadSkillTool(Tool):
    """Espone le descrizioni e legge il testo completo solo su richiesta."""

    def __init__(self, executor: _SkillExecutor, catalog: list[SkillEntry]) -> None:
        """Inietta esecutore e catalogo gia' validato dal punto d'ingresso."""
        self.executor = executor
        self.catalog = {entry.name: entry for entry in catalog}

    @property
    def name(self) -> str:
        """Nome dello strumento nel contratto del modello."""
        return "load_skill"

    @property
    def description(self) -> str:
        """Presenta lo schema di caricamento e le sole descrizioni brevi."""
        return (
            "Load the full instructions of a skill. Its files and scripts are in "
            "/opt/skills/<name>; use them with bash. Available skills:\n"
            + "\n".join(f"- {entry.name}: {entry.description}" for entry in self.catalog.values())
        )

    @property
    def parameters(self) -> dict:
        """Ammette soltanto i nomi fissati nel catalogo."""
        return {
            "type": "object",
            "properties": {"name": {"type": "string", "enum": list(self.catalog)}},
            "required": ["name"],
        }

    def execute(self, args: dict) -> dict:
        """Legge SKILL.md senza troncarlo e senza eseguire nomi sconosciuti."""
        name = args.get("name")
        if not isinstance(name, str) or name not in self.catalog:
            return {"error": f"skill sconosciuta: {name}; available: {', '.join(self.catalog)}"}
        folder = f"{SKILLS_ROOT}/{name}"
        result = self.executor.run(f"cat {folder}/SKILL.md")
        if result["exit_code"] != 0:
            return {"error": result.get("stderr") or f"impossibile caricare la skill '{name}'"}
        return {"folder": folder, "content": result["stdout"]}
