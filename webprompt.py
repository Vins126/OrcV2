"""Il prompt dei bracci: testo del compito, cornice comune e materiale del compito (R1.2).

Il prompt e' l'unica cosa che i bracci vedono del compito, quindi deve essere lo
stesso per B, C, D e H: e' una funzione pura di tre file e del testo del compito.

- `campaigns/r1_prompt/cornice.md`: regole di consegna uguali per ogni compito
  (`start.sh` sulla porta 8080, niente rete, `data-testid`, `datetime-local`).
- `campaigns/r1_prompt/<id>.md`: contratto delle rotte (se c'e'), marcatori e
  note del compito, con tre soli titoli di sezione ammessi.

Il materiale di valutazione (`campaigns/r1_valutazione/`: script e domande del
giudice) sta in file separati e qui non si legge mai. Un titolo di sezione
diverso dai tre ammessi e' un errore: e' il segno piu' probabile di un pezzo di
valutazione copiato per sbaglio.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from webtasks import WebTask, WebTaskError

PROJECT_ROOT = Path(__file__).resolve().parent
MATERIAL_DIR = PROJECT_ROOT / "campaigns" / "r1_prompt"
FRAME_NAME = "cornice.md"

#: Fino a 12 marcatori per compito (`docs/PROTOCOLLO.md` §6); una famiglia come
#: `nav-link-<section>` conta uno.
MAX_MARKERS = 12

CONTRACT = "Routes contract"
MARKERS = "data-testid markers"
NOTES = "Notes"
SECTIONS = (CONTRACT, MARKERS, NOTES)


@dataclass(frozen=True)
class PromptMaterial:
    """Cio' che il braccio vede di un compito oltre al testo.

    Attributes:
        body: il file com'e', senza spazi in testa e in coda; entra nel prompt intero.
        markers: i `data-testid` nell'ordine della tabella.
        has_contract: se il compito ha il contratto delle rotte.
    """

    body: str
    markers: tuple[str, ...]
    has_contract: bool


def _sezioni(path: Path, testo: str) -> dict[str, list[str]]:
    """Divide il file per titoli `## `.

    Rifiuta testo prima del primo titolo, titoli sconosciuti di qualunque livello
    (i file di valutazione usano sottosezioni `###`) e sezioni ripetute. Le righe
    dentro un blocco di codice non sono titoli.
    """
    sezioni: dict[str, list[str]] = {}
    corrente: list[str] | None = None
    in_codice = False
    for riga in testo.splitlines():
        if riga.startswith("```"):
            in_codice = not in_codice
        titolo_md = None if in_codice else re.match(r"^(#{1,6})\s+(.*)$", riga)
        if titolo_md:
            titolo = titolo_md.group(2).strip()
            if titolo_md.group(1) != "##" or titolo not in SECTIONS:
                raise WebTaskError(f"{path}: titolo non ammesso {riga.strip()!r} "
                                   f"(ammessi solo: ## {', ## '.join(SECTIONS)})")
            if titolo in sezioni:
                raise WebTaskError(f"{path}: sezione {titolo!r} ripetuta")
            corrente = sezioni[titolo] = []
        elif corrente is None:
            if riga.strip():
                raise WebTaskError(f"{path}: testo prima della prima sezione: {riga!r}")
        else:
            corrente.append(riga)
    return sezioni


def _marcatori(path: Path, righe: list[str]) -> tuple[str, ...]:
    """Il primo testo fra backtick di ogni riga della tabella dei marcatori."""
    marcatori: list[str] = []
    for riga in righe:
        trovato = re.search(r"`([^`]+)`", riga) if riga.startswith("|") else None
        if trovato is None:
            continue
        if trovato.group(1) in marcatori:
            raise WebTaskError(f"{path}: marcatore `{trovato.group(1)}` ripetuto")
        marcatori.append(trovato.group(1))
    return tuple(marcatori)


def load_material(path: Path) -> PromptMaterial:
    """Legge e controlla il materiale di un compito.

    Raises:
        WebTaskError: testo fuori sezione, sezione sconosciuta, tabella dei
            marcatori assente o vuota, marcatore ripetuto, piu' di 12 marcatori.
    """
    testo = Path(path).read_text()
    sezioni = _sezioni(path, testo)
    marcatori = _marcatori(path, sezioni.get(MARKERS, []))
    if not marcatori:
        raise WebTaskError(f"{path}: manca la tabella della sezione «{MARKERS}»")
    if len(marcatori) > MAX_MARKERS:
        raise WebTaskError(f"{path}: {len(marcatori)} marcatori, al massimo {MAX_MARKERS}")
    return PromptMaterial(body=testo.strip(), markers=marcatori, has_contract=CONTRACT in sezioni)


def build_prompt(task: WebTask, material_dir: Path = MATERIAL_DIR) -> str:
    """Il prompt di un compito: testo com'e' nel benchmark, poi cornice, poi materiale.

    Raises:
        WebTaskError: cornice o materiale del compito mancanti, o materiale non valido.
    """
    cornice = Path(material_dir) / FRAME_NAME
    materiale = Path(material_dir) / f"{task.candidate.id}.md"
    if not cornice.is_file():
        raise WebTaskError(f"cornice comune mancante: {cornice}")
    if not materiale.is_file():
        raise WebTaskError(f"materiale del prompt mancante per il compito {task.candidate.id}: {materiale}")
    corpo = load_material(materiale).body
    return f"{task.candidate.text}\n\n{cornice.read_text().strip()}\n\n{corpo}\n"
