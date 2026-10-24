"""Compiti di siti web da WebGen-Bench e ArtifactsBench, scelti con un seme.

WebGen-Bench (licenza MIT, scheda Hugging Face `luzimu/WebGen-Bench`) si prende
dalla copia GitHub `mnluzimu/WebGen-Bench`; ArtifactsBench (CC BY 4.0, file
`LICENSE` del repository) da `Tencent-Hunyuan/ArtifactsBenchmark`. Entrambi i
file sono fissati a un commit e verificati con sha256 (docs/PROTOCOLLO.md §2).

Nota di design (tesi):
    La scelta dei compiti non e' a gusto. Ogni fonte, dopo il pre-filtro per
    etichetta, si ordina per identificativo e si mescola con il seme; i compiti
    si leggono in quell'ordine e ciascuno riceve un verdetto scritto. `select`
    rifa' il percorso: un compito raggiunto senza verdetto, o un verdetto dato a
    un compito che non e' ancora il suo turno, e' un errore. Cosi' non si puo'
    saltare un compito sgradito senza scriverne il motivo.
"""

import hashlib
import json
import random
import shutil
import tempfile
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from task_model import CampaignError

WEBGEN = "webgen"
ARTIFACTS = "artifactsbench"
#: Tipi di compito ammessi in un verdetto (PROTOCOLLO §2, «Tipo»).
KINDS = ("sito", "applicazione")


@dataclass(frozen=True)
class Source:
    """Un file di benchmark fissato a un commit."""

    name: str
    url: str
    filename: str
    sha256: str


SOURCES = (
    Source(
        name=WEBGEN,
        url="https://raw.githubusercontent.com/mnluzimu/WebGen-Bench/"
            "c89e0743438e458d617cebaf7a682e0e66e41049/data/test.jsonl",
        filename="webgen_test.jsonl",
        sha256="e6451c1c5aed85ab01a15ab7c6be2bc737d4df28ca8b9ae15805a237878dee29",
    ),
    Source(
        name=ARTIFACTS,
        url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
            "88c968b87e150e63de7660937e6dcfb8e7d643cf/dataset/artifacts_bench.json",
        filename="artifacts_bench.jsonl",
        sha256="3bd4740421f2be075191a64173d3bca8bfb68897f3d58afccc96b733e04b56db",
    ),
)

#: Famiglie di ArtifactsBench che passano il pre-filtro (P9-D1), e le eccezioni.
_FAMIGLIE_ARTIFACTS = ("Web Applications-", "Management Systems-", "Utility Tools-")
_ETICHETTE_ARTIFACTS_IN = ("Data Science-Data Visualization Dashboards",)
_ETICHETTE_ARTIFACTS_OUT = ("Utility Tools-Web Scraping",)
#: Tipo di WebGen-Bench escluso dal pre-filtro (P6-D1).
_GIOCHI_WEBGEN = "Browser-Based Games"


class WebTaskError(CampaignError):
    """Errore nello scaricamento, nella lettura o nella scelta dei compiti."""


@dataclass(frozen=True)
class Candidate:
    """Un compito come sta nel benchmark, prima della scelta.

    Attributes:
        id: identificativo nel benchmark (numerico, come testo).
        source: `WEBGEN` o `ARTIFACTS`.
        label: `application_type` di WebGen o `class` di ArtifactsBench.
        text: testo del compito, cosi' com'e'.
        checks: casi di prova di WebGen (`ui_instruct`) o checklist di ArtifactsBench.
    """

    id: str
    source: str
    label: str
    text: str
    checks: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Verdict:
    """Il giudizio di lettura su un compito: tenuto con il tipo, o scartato con il motivo."""

    id: str
    keep: bool
    kind: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class WebTask:
    """Un compito scelto: il candidato e il tipo assegnato alla lettura."""

    candidate: Candidate
    kind: str


def _righe_jsonl(path: Path, campi: tuple[str, ...]) -> list[dict]:
    """Legge un file con un oggetto JSON per riga e controlla che ci siano i campi."""
    righe = []
    for numero, riga in enumerate(Path(path).read_text().splitlines(), start=1):
        if not riga.strip():
            continue
        try:
            oggetto = json.loads(riga)
        except json.JSONDecodeError as errore:
            raise WebTaskError(f"{path}: riga {numero} non e' JSON valido: {errore}") from errore
        mancanti = [c for c in campi if c not in oggetto]
        if mancanti:
            raise WebTaskError(f"{path}: alla riga {numero} mancano {', '.join(mancanti)}")
        righe.append(oggetto)
    return righe


def load_webgen(path: Path) -> list[Candidate]:
    """Compiti della divisione di test di WebGen-Bench, con i loro casi di prova.

    Raises:
        WebTaskError: riga non JSON o campo mancante.
    """
    return [Candidate(id=r["id"], source=WEBGEN, label=r["application_type"],
                      text=r["instruction"], checks=r["ui_instruct"])
            for r in _righe_jsonl(path, ("id", "instruction", "application_type", "ui_instruct"))]


def load_artifacts(path: Path) -> list[Candidate]:
    """Compiti di ArtifactsBench, con la loro checklist. L'indice diventa testo.

    Raises:
        WebTaskError: riga non JSON o campo mancante.
    """
    return [Candidate(id=str(r["index"]), source=ARTIFACTS, label=r["class"],
                      text=r["question"], checks=r["checklist"])
            for r in _righe_jsonl(path, ("index", "question", "class", "checklist"))]


def _passa_prefiltro(candidate: Candidate) -> bool:
    if candidate.source == WEBGEN:
        return candidate.label != _GIOCHI_WEBGEN
    if candidate.label in _ETICHETTE_ARTIFACTS_OUT:
        return False
    return (candidate.label.startswith(_FAMIGLIE_ARTIFACTS)
            or candidate.label in _ETICHETTE_ARTIFACTS_IN)


def prefilter(candidates: list[Candidate]) -> list[Candidate]:
    """Toglie per etichetta cio' che di sicuro non e' un sito (P6-D1, P9-D1); l'ordine resta."""
    return [c for c in candidates if _passa_prefiltro(c)]


def draw_order(candidates: list[Candidate], seed: int) -> list[Candidate]:
    """Ordine di lettura: per identificativo numerico, poi mescolato con il seme.

    L'ordinamento iniziale rende il risultato indipendente dall'ordine del file;
    e' numerico perche' in ordine alfabetico "10" verrebbe prima di "9".
    """
    ordine = sorted(candidates, key=lambda c: int(c.id))
    random.Random(seed).shuffle(ordine)
    return ordine


def select(order: list[Candidate], verdicts: list[Verdict], count: int) -> list[WebTask]:
    """Percorre l'ordine estratto e tiene i primi `count` compiti con verdetto positivo.

    Raises:
        WebTaskError: verdetto doppio o su un compito inesistente; compito
            raggiunto senza verdetto; verdetto dato a un compito oltre il punto
            in cui la scelta si ferma (letto fuori ordine); compiti finiti prima
            di arrivare a `count`.
    """
    per_id: dict[str, Verdict] = {}
    for verdetto in verdicts:
        if verdetto.id in per_id:
            raise WebTaskError(f"verdetto doppio per il compito '{verdetto.id}'")
        per_id[verdetto.id] = verdetto
    esistenti = {c.id for c in order}
    for id_ in per_id:
        if id_ not in esistenti:
            raise WebTaskError(f"verdetto sul compito '{id_}', che non e' fra i candidati")

    scelti: list[WebTask] = []
    letti: set[str] = set()
    for candidato in order:
        if len(scelti) == count:
            break
        verdetto = per_id.get(candidato.id)
        if verdetto is None:
            raise WebTaskError(
                f"il compito '{candidato.id}' e' il prossimo nell'ordine ma non ha un verdetto")
        letti.add(candidato.id)
        if verdetto.keep:
            tipo = verdetto.kind
            if tipo is None or tipo not in KINDS:
                raise WebTaskError(f"il compito '{candidato.id}' e' tenuto senza un tipo ammesso")
            scelti.append(WebTask(candidate=candidato, kind=tipo))
    if len(scelti) < count:
        raise WebTaskError(f"compiti finiti: {len(scelti)} tenuti su {count} richiesti")

    fuori_turno = [id_ for id_ in per_id if id_ not in letti]
    if fuori_turno:
        raise WebTaskError(
            f"verdetti su compiti oltre il punto in cui la scelta si ferma: "
            f"{', '.join(repr(i) for i in fuori_turno)}")
    return scelti


def _verdetto(grezzo: object, fonte: str) -> Verdict:
    if not isinstance(grezzo, dict) or not isinstance(grezzo.get("id"), str) \
            or not isinstance(grezzo.get("keep"), bool):
        raise WebTaskError(f"[{fonte}]: ogni verdetto vuole 'id' (testo) e 'keep' (true/false)")
    id_ = grezzo["id"]
    if grezzo["keep"]:
        tipo = grezzo.get("kind")
        if tipo is None:
            raise WebTaskError(f"[{fonte}] '{id_}': tenuto senza 'kind'")
        if tipo not in KINDS:
            raise WebTaskError(f"[{fonte}] '{id_}': tipo '{tipo}' non ammesso ({', '.join(KINDS)})")
        return Verdict(id=id_, keep=True, kind=tipo)
    motivo = grezzo.get("reason")
    if not isinstance(motivo, str) or not motivo.strip():
        raise WebTaskError(f"[{fonte}] '{id_}': scartato senza 'reason'")
    return Verdict(id=id_, keep=False, reason=motivo)


_CARICATORI = {WEBGEN: load_webgen, ARTIFACTS: load_artifacts}


def load_selection(config: Path, data_dir: Path) -> list[WebTask]:
    """Rifa' la scelta dal file dei verdetti: prima i compiti di WebGen, poi di ArtifactsBench.

    Raises:
        WebTaskError: file dei verdetti illeggibile o incompleto, dati non
            scaricati, o uno degli errori di `select`.
    """
    try:
        dati = tomllib.loads(Path(config).read_text())
    except (OSError, tomllib.TOMLDecodeError) as errore:
        raise WebTaskError(f"{config}: file dei verdetti non leggibile: {errore}") from errore
    seme = dati.get("seed")
    if not isinstance(seme, int):
        raise WebTaskError(f"{config}: manca 'seed' (intero)")

    scelti: list[WebTask] = []
    for fonte in SOURCES:
        sezione = dati.get(fonte.name)
        if not isinstance(sezione, dict) or not isinstance(sezione.get("count"), int):
            raise WebTaskError(f"{config}: manca la sezione [{fonte.name}] con 'count'")
        file = Path(data_dir) / fonte.filename
        if not file.is_file():
            raise WebTaskError(
                f"dati non trovati: {file}; scaricali con `python campaign.py fetch-webtasks`")
        verdetti = [_verdetto(v, fonte.name) for v in sezione.get("verdicts", [])]
        ordine = draw_order(prefilter(_CARICATORI[fonte.name](file)), seme)
        scelti.extend(select(ordine, verdetti, sezione["count"]))
    return scelti


def _scarica(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as risposta:
        return risposta.read()


def fetch_webtasks(dest: Path, *, download: Callable[[str], bytes] | None = None) -> Path:
    """Scarica i due file ai commit fissati e li mette in `dest`, dopo averli verificati.

    Si scarica e si verifica tutto prima di toccare il disco; poi i file si
    scrivono in una cartella temporanea accanto a `dest`, che prende il suo
    nome solo alla fine. Non sovrascrive mai una cartella esistente.

    Args:
        dest: cartella di destinazione; non deve esistere.
        download: chi scarica un file dato l'URL; `None` usa la rete.

    Raises:
        WebTaskError: se `dest` esiste, se lo scaricamento fallisce o se uno
            dei file non ha lo sha256 atteso.
    """
    destinazione = Path(dest)
    if destinazione.exists():
        raise WebTaskError(f"la cartella {destinazione} esiste gia': non la sovrascrivo")

    scarica = download if download is not None else _scarica
    contenuti: dict[str, bytes] = {}
    for fonte in SOURCES:
        try:
            contenuto = scarica(fonte.url)
        except (urllib.error.URLError, OSError, TimeoutError) as errore:
            raise WebTaskError(f"scaricamento di {fonte.name} non riuscito: {errore}") from errore
        trovato = hashlib.sha256(contenuto).hexdigest()
        if trovato != fonte.sha256:
            raise WebTaskError(
                f"{fonte.name}: sha256 diverso dall'atteso "
                f"(atteso {fonte.sha256[:12]}..., trovato {trovato[:12]}...)")
        contenuti[fonte.filename] = contenuto

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    temporanea = Path(tempfile.mkdtemp(prefix=".webtasks-", dir=destinazione.parent))
    try:
        for nome, contenuto in contenuti.items():
            (temporanea / nome).write_bytes(contenuto)
        temporanea.rename(destinazione)
    finally:
        shutil.rmtree(temporanea, ignore_errors=True)
    return destinazione
