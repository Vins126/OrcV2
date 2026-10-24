"""Avvio e rendering di un sito consegnato, nell'immagine «renderer» (R1.4).

Il sito sta in un workspace con `start.sh` nella radice, che lo avvia sulla
porta 8080 (`docs/PROTOCOLLO.md` §2). Il renderer e' l'immagine della sandbox
piu' Chromium e Playwright (`docker/renderer.Dockerfile`): server e browser
girano nello stesso container, senza rete, e lo script interno
(`docker/render_site.py`) scrive un `result.json` con avvio, errori, sbordo e
screenshot per ogni larghezza.

Nota di design (tesi):
    La valutazione lavora su una COPIA del workspace: un server che salva dati
    (cosa che il protocollo chiede alle applicazioni) non deve cambiare il
    workspace archiviato in `runs/`, che e' il dato della tesi. E un risultato
    mancante o illeggibile e' un guasto della valutazione (`RenderError`), non
    un sito che vale 0: le due cose si contano a parte (ROADMAP R1.5, R6.2).
"""

import json
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from task_model import CampaignError

#: Immagine del renderer, costruita da `docker/renderer.Dockerfile`.
RENDERER_IMAGE = "orc-renderer:r1"
#: Larghezze della finestra a cui si guarda il sito (PROTOCOLLO §6).
WIDTHS = (375, 768, 1440)
PORT = 8080
#: Secondi concessi al sito per aprire la porta (PROTOCOLLO §2).
START_TIMEOUT_S = 60
#: Limiti del container del renderer: Chromium non sta nei limiti della sandbox.
RENDERER_MEMORY = "2g"
RENDERER_SHM = "1g"
RENDERER_PIDS = "1024"
#: Tempo massimo dell'intera valutazione di un sito (avvio + tre larghezze).
RENDER_TIMEOUT_S = 240


#: Codice del progetto che serve nel container per eseguire gli script.
PROJECT_ROOT = Path(__file__).resolve().parent


def _copia_codice(destinazione: Path) -> None:
    """Copia solo il codice della valutazione: mai la radice del progetto, che contiene `.env`."""
    shutil.copytree(PROJECT_ROOT / "valutazione", destinazione / "valutazione",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(PROJECT_ROOT / "task_model.py", destinazione / "task_model.py")


class RenderError(CampaignError):
    """Guasto della valutazione: risultato mancante, illeggibile o tempo scaduto."""


@dataclass(frozen=True)
class WidthResult:
    """Cio' che si e' visto a una larghezza."""

    width: int
    errors: list[str]
    overflow: bool
    screenshot: Path | None
    #: Violazioni axe-core di impatto `critical` o `serious`: regola, impatto, quanti elementi.
    a11y: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RenderResult:
    """Esito del rendering di un sito.

    Attributes:
        started: il sito ha aperto la porta in tempo.
        start_error: perche' non e' partito (`None` se e' partito).
        widths: risultati per larghezza, vuoto se il sito non e' partito.
        versions: versioni di browser e Playwright usate.
    """

    started: bool
    start_error: str | None = None
    widths: dict[int, WidthResult] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)
    #: Esito della vetrina dello script: "ok", "assente", "errore: ..."; `None` senza script.
    vetrina: str | None = None


Runner = Callable[..., subprocess.CompletedProcess]


def docker_command(site: Path, out: Path, name: str, *, image: str = RENDERER_IMAGE,
                   start_timeout: int = START_TIMEOUT_S, script: Path | None = None,
                   code: Path | None = None) -> list[str]:
    """Il `docker run` del renderer: copia del sito in /workspace, risultati in /out.

    Il sito gira in /workspace, lo stesso percorso in cui l'agente l'ha costruito:
    i percorsi assoluti scritti dagli strumenti (un venv di Python) restano validi.
    Senza rete, utente 1000 senza privilegi, filesystem in sola lettura tranne
    /workspace, /out e /tmp. I limiti sono quelli di Chromium, non della sandbox
    degli agenti (512 MB e 256 processi lo ucciderebbero); `--init` raccoglie i
    processi orfani del server e del browser. Con uno `script`, prima degli
    screenshot si esegue la sua funzione `vetrina` (dati d'esempio via rotte):
    script e codice della valutazione entrano in sola lettura.
    """
    con_script: list[str] = []
    argomenti_script: list[str] = []
    if script is not None:
        codice = code if code is not None else out.parent / "py"
        con_script = ["-e", "PYTHONPATH=/opt/orc/py",
                      "--volume", f"{script.parent}:/eval:ro",
                      "--volume", f"{codice}:/opt/orc/py:ro"]
        argomenti_script = ["--script", f"/eval/{script.name}"]
    return [
        "docker", "run", "--rm", "--init",
        "--name", name,
        "--network", "none",
        "--user", "1000:1000",
        "--read-only",
        "--tmpfs", "/tmp",
        "--memory", RENDERER_MEMORY,
        "--shm-size", RENDERER_SHM,
        "--pids-limit", RENDERER_PIDS,
        "--workdir", "/workspace",
        "--volume", f"{site}:/workspace",
        "--volume", f"{out}:/out",
        *con_script,
        image,
        "python3", "/opt/orc/render_site.py",
        "--site", "/workspace", "--out", "/out",
        "--port", str(PORT),
        "--widths", ",".join(str(w) for w in WIDTHS),
        "--start-timeout", str(start_timeout),
        *argomenti_script,
    ]


def _leggi_risultato(out: Path, out_dir: Path, stderr: str) -> RenderResult:
    """Legge `result.json` scritto dal container e copia gli screenshot in `out_dir`.

    Raises:
        RenderError: file mancante, non JSON o senza i campi attesi.
    """
    file = out / "result.json"
    coda = stderr.strip()[-500:]
    if not file.is_file():
        raise RenderError(f"il renderer non ha scritto result.json; stderr: {coda!r}")
    try:
        dati = json.loads(file.read_text())
    except json.JSONDecodeError as errore:
        raise RenderError(f"result.json non e' JSON valido: {errore}") from errore
    if not isinstance(dati, dict) or not isinstance(dati.get("started"), bool):
        raise RenderError("result.json senza il campo 'started'")
    vetrina = dati.get("vetrina")
    vetrina = str(vetrina) if vetrina is not None else None
    if not dati["started"]:
        return RenderResult(started=False, start_error=str(dati.get("start_error") or "non partito"),
                            versions=dict(dati.get("versions") or {}), vetrina=vetrina)

    grezze = dati.get("widths")
    if not isinstance(grezze, dict) or {str(w) for w in WIDTHS} - set(grezze):
        raise RenderError(f"result.json senza i risultati di tutte le larghezze {WIDTHS}")
    larghezze: dict[int, WidthResult] = {}
    for w in WIDTHS:
        voce = grezze[str(w)]
        try:
            errori = [str(e) for e in voce["errors"]]
            sbordo = bool(voce["overflow"])
            nome = voce["screenshot"]
            accessibilita = [{"id": str(v["id"]), "impact": str(v["impact"]), "nodes": int(v["nodes"])}
                             for v in voce["a11y"]]
        except (KeyError, TypeError) as errore:
            raise RenderError(f"risultato della larghezza {w} incompleto: {errore}") from errore
        screenshot = None
        if nome:
            sorgente = out / Path(str(nome)).name
            if not sorgente.is_file():
                raise RenderError(f"screenshot mancante: {sorgente.name}")
            screenshot = out_dir / sorgente.name
            shutil.copyfile(sorgente, screenshot)
        larghezze[w] = WidthResult(width=w, errors=errori, overflow=sbordo, screenshot=screenshot,
                                   a11y=accessibilita)
    return RenderResult(started=True, widths=larghezze, versions=dict(dati.get("versions") or {}),
                        vetrina=vetrina)


def render_site(workspace: Path, out_dir: Path, *, runner: Runner = subprocess.run,
                image: str = RENDERER_IMAGE, start_timeout: int = START_TIMEOUT_S,
                timeout: int = RENDER_TIMEOUT_S, script: Path | None = None) -> RenderResult:
    """Avvia il sito di `workspace` nel renderer e ne restituisce l'esito.

    Il container lavora su una copia temporanea del workspace, cancellata alla
    fine; gli screenshot finiscono in `out_dir`.

    Args:
        workspace: cartella consegnata dal braccio, con `start.sh` nella radice.
        out_dir: dove copiare gli screenshot (creata se manca).
        runner: chi esegue i comandi `docker` (nei test, un finto).
        image: immagine del renderer.
        start_timeout: secondi concessi al sito per aprire la porta.
        timeout: secondi concessi all'intera valutazione.
        script: script del compito; se ha una funzione `vetrina`, gli
            screenshot si fanno dopo averla eseguita (PROTOCOLLO §6).

    Returns:
        L'esito: anche un sito che non parte e' un esito (`started=False`).

    Raises:
        RenderError: guasto della valutazione (tempo scaduto, risultato
            mancante o illeggibile). Non e' un giudizio sul sito.
    """
    sorgente = Path(workspace)
    if not (sorgente / "start.sh").is_file():
        return RenderResult(started=False, start_error="start.sh mancante nella radice del workspace")
    destinazione = Path(out_dir)
    destinazione.mkdir(parents=True, exist_ok=True)

    temporanea = Path(tempfile.mkdtemp(prefix="orc-render-"))
    try:
        site = temporanea / "site"
        out = temporanea / "out"
        shutil.copytree(sorgente, site, symlinks=True)
        out.mkdir()
        codice = None
        if script is not None:
            codice = temporanea / "py"
            _copia_codice(codice)
            script = Path(script).resolve()
        nome = f"orc-renderer-{uuid.uuid4().hex[:12]}"
        comando = docker_command(site, out, nome, image=image, start_timeout=start_timeout,
                                 script=script, code=codice)
        try:
            esito = runner(comando, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as errore:
            # Il timeout ferma il programma `docker`, non il container: lo si ferma per nome.
            try:
                runner(["docker", "kill", nome], capture_output=True, text=True, timeout=30)
            except (subprocess.SubprocessError, OSError):
                pass
            raise RenderError(f"tempo scaduto dopo {timeout} s: container {nome} fermato") from errore
        return _leggi_risultato(out, destinazione, esito.stderr or "")
    finally:
        shutil.rmtree(temporanea, ignore_errors=True)


# ── Script d'interazione (R1.7) ────────────────────────────────────────────
#: Tempo massimo dell'esecuzione di uno script (un riavvio del sito per passo).
EVAL_TIMEOUT_S = 900


@dataclass(frozen=True)
class EvalResult:
    """Esito di uno script d'interazione su un sito.

    Attributes:
        funziona: passi d'interfaccia superati / valutabili x 100 (PROTOCOLLO §6).
        funziona_server: test delle rotte superati / totali x 100; `None` senza rotte.
        steps: un dizionario per passo: `id`, `tipo`, `stato`, `motivo`.
    """

    funziona: float
    funziona_server: float | None
    steps: list[dict] = field(default_factory=list)


def eval_command(site: Path, script: Path, out: Path, name: str, *, image: str = RENDERER_IMAGE,
                 start_timeout: int = START_TIMEOUT_S, work: Path | None = None,
                 code: Path | None = None) -> list[str]:
    """Il `docker run` di uno script: sito intatto in /site, copia di lavoro in /workspace.

    Lo script e il codice della valutazione entrano in sola lettura; il codice e'
    una copia del solo pacchetto `valutazione` (mai la radice del progetto, che
    contiene `.env`). Stessi limiti e stessa assenza di rete del rendering.
    """
    lavoro = work if work is not None else out.parent / "workspace"
    codice = code if code is not None else out.parent / "py"
    return [
        "docker", "run", "--rm", "--init",
        "--name", name,
        "--network", "none",
        "--user", "1000:1000",
        "--read-only",
        "--tmpfs", "/tmp",
        "--memory", RENDERER_MEMORY,
        "--shm-size", RENDERER_SHM,
        "--pids-limit", RENDERER_PIDS,
        "--workdir", "/workspace",
        "-e", "PYTHONPATH=/opt/orc/py",
        "--volume", f"{site}:/site:ro",
        "--volume", f"{lavoro}:/workspace",
        "--volume", f"{script.parent}:/eval:ro",
        "--volume", f"{codice}:/opt/orc/py:ro",
        "--volume", f"{out}:/out",
        image,
        "python3", "-m", "valutazione.contenitore",
        "--script", f"/eval/{script.name}",
        "--site", "/site", "--work", "/workspace", "--out", "/out",
        "--port", str(PORT),
        "--start-timeout", str(start_timeout),
    ]


def _leggi_valutazione(out: Path, stderr: str) -> EvalResult:
    file = out / "eval.json"
    if not file.is_file():
        raise RenderError(f"lo script non ha scritto eval.json; stderr: {stderr.strip()[-800:]!r}")
    try:
        dati = json.loads(file.read_text())
    except json.JSONDecodeError as errore:
        raise RenderError(f"eval.json non e' JSON valido: {errore}") from errore
    if (not isinstance(dati, dict) or not isinstance(dati.get("funziona"), (int, float))
            or not isinstance(dati.get("steps"), list)):
        raise RenderError("eval.json senza 'funziona' o 'steps'")
    server = dati.get("funziona_server")
    return EvalResult(funziona=float(dati["funziona"]),
                      funziona_server=float(server) if server is not None else None,
                      steps=[dict(s) for s in dati["steps"]])


def evaluate_site(workspace: Path, script: Path, *, runner: Runner = subprocess.run,
                  image: str = RENDERER_IMAGE, start_timeout: int = START_TIMEOUT_S,
                  timeout: int = EVAL_TIMEOUT_S) -> EvalResult:
    """Esegue lo script d'interazione `script` sul sito di `workspace`.

    Il container riceve una copia del workspace, che non viene mai toccato.

    Raises:
        RenderError: guasto della valutazione (tempo scaduto, esito mancante o
            illeggibile). Non e' un giudizio sul sito.
    """
    sorgente = Path(workspace)
    if not (sorgente / "start.sh").is_file():
        return EvalResult(funziona=0.0, funziona_server=None, steps=[])

    temporanea = Path(tempfile.mkdtemp(prefix="orc-eval-"))
    try:
        site, work, out, codice = (temporanea / n for n in ("site", "workspace", "out", "py"))
        shutil.copytree(sorgente, site, symlinks=True)
        for cartella in (work, out):
            cartella.mkdir()
        _copia_codice(codice)
        nome = f"orc-eval-{uuid.uuid4().hex[:12]}"
        comando = eval_command(site, Path(script).resolve(), out, nome, image=image,
                               start_timeout=start_timeout, work=work, code=codice)
        try:
            esito = runner(comando, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as errore:
            try:
                runner(["docker", "kill", nome], capture_output=True, text=True, timeout=30)
            except (subprocess.SubprocessError, OSError):
                pass
            raise RenderError(f"tempo scaduto dopo {timeout} s: container {nome} fermato") from errore
        return _leggi_valutazione(out, esito.stderr or "")
    finally:
        shutil.rmtree(temporanea, ignore_errors=True)
