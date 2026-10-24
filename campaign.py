"""Campagna di misura: lancia task in serie e ne calcola `f` e la quota di output.

Misura M2s.4a: tasso di fallimento `f` e quota di output su una serie di task.
"""

import argparse
import functools
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import config
from run_status import RunStatus
from task_model import CampaignError, Task
from accounting import ModelRegistry
from accounting.errors import ModelNotFound, RegistryError, UnitNotFound
from agent_factory import AgentFactory
from executors import docker as sandbox
from executors.docker import RETI_AMMESSE, DockerExecutor, SandboxImageMissing
from parallel_runner import Admission, JobOutcome, run_parallel
from tools import build_default_tools


@dataclass
class CampaignReport:
    """Numeri di una campagna.

    `runs` sono le run in cui il modello e' stato davvero interpellato;
    `excluded_runs` quelle saltate per un guasto della campagna (setup o
    costruzione dell'agente), che non entrano in `f`; `runs_without_usage` le
    run senza `usage.jsonl`, il cui costo manca dal totale.
    """

    runs: int
    failure_rate: float
    failure_rate_by_task: dict[str, float]
    total_cost: float
    output_cost_share: float
    output_token_share: float
    unpriced_records: int
    excluded_runs: int = 0
    runs_without_usage: int = 0
    #: Somma del costo che il fornitore dichiara per ogni chiamata (`usage.cost`),
    #: oppure `None` se nessun record lo riporta. Affianca `total_cost`, che e'
    #: calcolato sul listino: se i due divergono, il listino non descrive piu'
    #: cio' che si paga (e' successo con un fornitore non fissato).
    reported_cost: float | None = None
    reported_records: int = 0
    #: Le run fallite per causa: lo `status` della run (`max_iterations`,
    #: `budget_exhausted`, `unexpected_error`...), oppure `verification_failed`
    #: se l'incarico e' `completed` ma la verifica non passa. `f` da solo
    #: mescola un modello che sbaglia con uno che non chiude entro il tetto.
    failures_by_cause: dict[str, int] = field(default_factory=dict)
    #: Quanti `request_id` compaiono in piu' di un record. Deve essere zero:
    #: lo stesso identificativo ripetuto indica risposte replicate invece di
    #: chiamate indipendenti, e falserebbe `f` e i costi.
    duplicate_request_ids: int = 0
    #: Chiamate gia' pagate che il listino non sa prezzare (eventi
    #: `unpriced_usage`): non entrano in `total_cost`, ma il loro costo
    #: riportato entra in `reported_cost` e il loro `request_id` nei duplicati.
    unpriced_calls: int = 0


def load_tasks(path: Path) -> list[Task]:
    """Legge e valida il file dei task, senza creare nulla su disco.

    Ogni errore emerge qui, prima che la campagna costruisca agenti o cartelle:
    un task senza `verify` renderebbe `f` privo di significato, e un id doppio
    farebbe confondere le righe del manifesto.

    Raises:
        CampaignError: file illeggibile o malformato, nessun task, campo
            obbligatorio mancante (`id`, `prompt`, `verify`) o id duplicato.
    """
    try:
        dati = tomllib.loads(Path(path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as errore:
        raise CampaignError(f"{path}: file dei task non leggibile: {errore}") from errore

    grezzi = dati.get("task", [])
    if not grezzi:
        raise CampaignError(f"{path}: nessun task dichiarato (sezioni [[task]])")
    if not isinstance(grezzi, list) or not all(isinstance(g, dict) for g in grezzi):
        raise CampaignError(f"{path}: 'task' deve essere una lista di sezioni [[task]]")

    tasks: list[Task] = []
    visti: set[str] = set()
    for posizione, grezzo in enumerate(grezzi, start=1):
        mancanti = [c for c in ("id", "prompt", "verify") if not grezzo.get(c)]
        if mancanti:
            raise CampaignError(
                f"{path}: il task n. {posizione} non ha {', '.join(mancanti)}")
        non_testo = [c for c in ("id", "prompt", "verify", "setup")
                     if c in grezzo and not isinstance(grezzo[c], str)]
        if non_testo:
            raise CampaignError(
                f"{path}: il task n. {posizione} ha campi che non sono testo: "
                f"{', '.join(non_testo)}")
        if grezzo["id"] in visti:
            raise CampaignError(f"{path}: id '{grezzo['id']}' dichiarato due volte")
        visti.add(grezzo["id"])
        tasks.append(Task(id=grezzo["id"], prompt=grezzo["prompt"],
                          verify=grezzo["verify"], setup=grezzo.get("setup")))
    return tasks


def _scrivi_file(workspace: Path, files: dict[str, str]) -> None:
    """Scrive nel workspace i file di un task (percorso relativo -> contenuto).

    Il workspace e' una cartella che l'agente puo' modificare a piacere, quindi
    non ci si fida di cio' che contiene: se un pezzo del percorso e' un link
    simbolico, o se il percorso esce dal workspace, si rifiuta. Senza questo,
    `ln -sf ../../main.py e_test.py` farebbe scrivere il ripristino su un file
    del computer ospite. Un tentativo e' un errore (la verifica fallisce).

    Raises:
        CampaignError: se il percorso passa da un link simbolico o esce dal workspace.
    """
    radice = Path(workspace).resolve()
    for percorso, contenuto in files.items():
        corrente = radice
        for parte in Path(percorso).parts:
            corrente = corrente / parte
            if corrente.is_symlink():
                raise CampaignError(
                    f"'{percorso}': '{parte}' e' un link simbolico nel workspace, non lo seguo")
        destinazione = radice / percorso
        if radice != destinazione.resolve() and radice not in destinazione.resolve().parents:
            raise CampaignError(f"'{percorso}' esce dal workspace")
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        destinazione.write_text(contenuto)


def shell_docker(workspace: Path, command: str) -> int:
    """Esegue un comando nella stessa sandbox degli agenti e ne restituisce l'exit code.

    Serve a `setup` e `verify` dei task: la verifica gira dove ha lavorato
    l'agente, con gli stessi limiti (utente non privilegiato) e **sempre senza
    rete**, qualunque sia la rete dell'agente: il controllo del risultato deve
    essere identico e ripetibile.
    """
    executor = DockerExecutor(
        str(workspace), image=config.DOCKER_IMAGE, timeout=config.EXEC_TIMEOUT,
        memory=config.DOCKER_MEMORY, pids_limit=config.DOCKER_PIDS_LIMIT,
        network="none")
    return int(executor.run(command)["exit_code"])


def _esegui_run(factory: Any, task: Task, rep: int, *, role: str,
                shell: Callable[[Path, str], int],
                max_iterations: int | None) -> dict[str, Any]:
    """Una run: agente nuovo, setup, incarico, verifica. Restituisce la riga del manifesto.

    Gira su un thread del gruppo quando la campagna e' concorrente: non scrive
    nel manifesto e non tocca stato condiviso, restituisce solo la riga. E' la
    parte che non cambia fra la campagna in serie e quella in parallelo.
    """
    riga_base: dict[str, Any] = {
        "task_id": task.id, "rep": rep, "run_id": None, "error_type": None,
    }
    try:
        built = factory.build(role)
    except Exception as errore:
        # Guasto della campagna (chiave mancante, Docker spento): si annota e si
        # prosegue; non e' un fallimento del modello.
        return {**riga_base, "agent_id": None, "model": None, "workspace": None,
                "status": "build_failed", "verified": False, "success": False,
                "total_cost": 0.0, "error_type": type(errore).__name__}

    row: dict[str, Any] = {
        **riga_base, "agent_id": built.agent_id, "model": built.model,
        "workspace": str(built.workspace),
    }
    try:
        _scrivi_file(built.workspace, task.files)
        setup_ok = not task.setup or shell(built.workspace, task.setup) == 0
    except Exception as errore:
        setup_ok = False
        row["error_type"] = type(errore).__name__
    if not setup_ok:
        # Un setup fallito e' un guasto della campagna, non del modello: si
        # annota a parte e non si interpella l'agente.
        row.update(status="setup_failed", verified=False, success=False, total_cost=0.0)
        return row

    try:
        result = built.assign(task.prompt, max_iterations=max_iterations)
        status = result.status
    except Exception as errore:  # una run guasta non deve fermare la campagna
        status = RunStatus.UNEXPECTED_ERROR
        row["error_type"] = type(errore).__name__

    try:
        # I file da ripristinare (i test originali) si riscrivono PRIMA di
        # verificare: se l'agente li ha toccati, cio' non conta.
        _scrivi_file(built.workspace, task.restore)
        verified = shell(built.workspace, task.verify) == 0
    except Exception as errore:
        # La run e' gia' stata pagata: la riga con il suo costo si scrive
        # comunque, con la verifica data per non riuscita.
        verified = False
        row["error_type"] = row["error_type"] or type(errore).__name__

    row.update(
        run_id=built.ledgers[-1].run_id if built.ledgers else None,
        status=status, verified=verified,
        success=status == RunStatus.COMPLETED and verified,
        total_cost=built.accountant.total_cost)
    return row


def run_campaign(factory: Any, tasks: list[Task], *, role: str, repetitions: int,
                 campaign_id: str, campaigns_dir: Path,
                 shell: Callable[[Path, str], int],
                 max_total_usd: float | None = None,
                 max_iterations: int | None = None,
                 environment: dict[str, Any] | None = None,
                 workers: int = 1,
                 reserve_per_run_usd: float | None = None) -> list[dict[str, Any]]:
    """Lancia ogni task `repetitions` volte, fino a `workers` run alla volta, e annota il manifesto.

    Ogni run ha un agente nuovo e quindi un workspace nuovo: le ripetizioni
    sono indipendenti. Una run e' un successo solo se l'incarico e' `completed`
    **e** `verify` esce con 0: un modello che risponde «fatto!» senza aver
    fatto nulla non conta come riuscito.

    Il manifesto (`<campaigns_dir>/<campaign_id>.jsonl`) riceve una riga per
    run, scritta subito: se la campagna si interrompe, quanto gia' speso resta
    documentato. Con piu' operai le righe arrivano nell'ordine in cui le run
    finiscono; il valore restituito segue invece l'ordine dei task. Le righe le
    scrive sempre e solo il thread principale: nessuna scrittura concorrente.

    Il tetto `max_total_usd` governa le **partenze**: una run parte solo se la
    spesa registrata piu' quella **prenotata** per le run in volo **e per lei
    stessa** non supera il tetto. La prenotazione e' `reserve_per_run_usd` (il
    tetto per run della fabbrica): e' il massimo che ogni run puo' spendere, a
    meno di una chiamata. Vale anche con un solo operaio: l'ultima run parte solo
    se il suo tetto ci sta ancora. Una run in corso non si interrompe. Resta uno
    sforamento possibile, limitato: ogni run puo' superare il proprio tetto di una
    chiamata (vedi `TESI_master.md` §9.6). Fino al 17 ott 2026 la run che partiva
    non era contata, e lo sforamento poteva arrivare a un tetto intero per run.

    Se `environment` e' dato (immagine, identificativo, rete), diventa la prima
    riga del manifesto; il report la ignora perche' non e' una run.

    Raises:
        CampaignError: se `repetitions` o `workers` non sono positivi, se il tetto
            per run supera quello totale, o se con
            piu' operai e un tetto totale manca `reserve_per_run_usd`. I
            controlli precedono ogni effetto: nessun agente, nessuna cartella.
    """
    if repetitions < 1:
        raise CampaignError(f"repetitions deve essere almeno 1, non {repetitions}")
    if workers < 1:
        raise CampaignError(f"workers deve essere almeno 1, non {workers}")
    if workers > 1 and max_total_usd is not None and reserve_per_run_usd is None:
        raise CampaignError(
            "con workers > 1 e un tetto totale serve reserve_per_run_usd (il tetto per "
            "run): senza non si sa quanto possono ancora spendere le run in volo")
    if (max_total_usd is not None and reserve_per_run_usd is not None
            and reserve_per_run_usd > max_total_usd):
        # Ogni run prenota il proprio tetto prima di partire: con un tetto per run piu'
        # alto di quello totale non ne partirebbe nessuna, senza un errore visibile.
        raise CampaignError(
            f"il tetto per run ({reserve_per_run_usd}) supera il tetto totale "
            f"({max_total_usd}): non partirebbe nessuna run")

    campaigns_dir = Path(campaigns_dir)
    manifest = campaigns_dir / f"{campaign_id}.jsonl"
    if manifest.exists():
        # Accodare mescolerebbe due campagne nel report, senza avviso.
        raise CampaignError(
            f"la campagna '{campaign_id}' esiste gia' ({manifest}): scegli un altro nome")
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    if environment is not None:
        # In testa al manifesto, fuori dalle righe restituite: non e' una run.
        with open(manifest, "a") as f:
            f.write(json.dumps({"environment": environment}) + "\n")

    def annota(row: dict[str, Any]) -> None:
        # Solo il thread principale scrive: nessun lock, nessuna riga interlacciata.
        with open(manifest, "a") as f:
            f.write(json.dumps(row) + "\n")

    jobs = [(task, rep) for task in tasks for rep in range(1, repetitions + 1)]
    righe_run: dict[int, dict[str, Any]] = {}
    spent = 0.0

    def admit(_job: tuple[Task, int], in_volo: int) -> Admission:
        if max_total_usd is None:
            return Admission.START
        if spent >= max_total_usd:
            return Admission.STOP
        # Si prenota anche la run che sta per partire: contando solo quelle gia' in volo,
        # con tetto 0,05 e 0,02 per run ne partivano 3 (0,06 prenotati) e lo sforamento
        # poteva arrivare a un tetto intero per run invece che a una chiamata.
        if spent + (in_volo + 1) * (reserve_per_run_usd or 0.0) > max_total_usd:
            return Admission.WAIT
        return Admission.START

    def on_done(esito: JobOutcome[tuple[Task, int], dict[str, Any]]) -> None:
        nonlocal spent
        task, rep = esito.job
        if esito.error is not None:
            # Non dovrebbe succedere (`_esegui_run` gestisce i guasti noti): si
            # annota comunque, perche' una riga mancante falserebbe la campagna.
            row = {"task_id": task.id, "rep": rep, "run_id": None, "agent_id": None,
                   "model": None, "workspace": None, "status": RunStatus.UNEXPECTED_ERROR,
                   "verified": False, "success": False, "total_cost": 0.0,
                   "error_type": type(esito.error).__name__}
        else:
            row = esito.result or {}
        spent += row.get("total_cost", 0.0)
        righe_run[esito.index] = row
        annota(row)

    esiti = run_parallel(
        jobs,
        lambda job: _esegui_run(factory, job[0], job[1], role=role, shell=shell,
                                max_iterations=max_iterations),
        max_workers=workers, admit=admit, on_done=on_done)

    rows = [righe_run[i] for i in sorted(righe_run)]
    if any(not e.started for e in esiti):
        fermata = {"stopped": "max_total_usd", "spent": spent, "max_total_usd": max_total_usd}
        annota(fermata)
        rows.append(fermata)
    return rows


def tools_builder_for(network: str) -> Callable[..., list]:
    """Costruttore di strumenti per la fabbrica, con la rete scelta per l'agente.

    La fabbrica chiama `tools_builder(workspace, event_sink=...)`: si fissa la rete
    con `functools.partial`, e il collegamento all'incarico passa intatto.
    """
    return functools.partial(build_default_tools, network=network)


def sandbox_environment(image: str, network: str, *,
                        inspect: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Descrive l'ambiente della sandbox, da scrivere in testa al manifesto.

    Servono nome e identificativo dell'immagine (il nome e' un'etichetta che puo'
    cambiare contenuto, l'identificativo no) e la rete: campagne fatte in
    ambienti diversi non vanno confrontate come se fossero la stessa misura.
    """
    leggi = inspect if inspect is not None else sandbox.image_id
    return {"image": image, "image_id": leggi(image), "network": network}


def ensure_image_available(image: str, *,
                           inspect: Callable[[str], str | None] | None = None,
                           attempts: int = 1, delay: float = 0.0,
                           sleep: Callable[[float], None] | None = None,
                           max_total_s: float | None = None) -> None:
    """Controlla che l'immagine esista, prima di costruire agenti.

    Raises:
        CampaignError: se l'immagine non c'e' (o Docker non e' raggiungibile).
    """
    try:
        sandbox.ensure_image(image, inspect=inspect, attempts=attempts, delay=delay, sleep=sleep,
                             max_total_s=max_total_s)
    except SandboxImageMissing as errore:
        raise CampaignError(str(errore)) from errore


def report(manifest_path: Path, runs_root: Path, registry: Any) -> CampaignReport:
    """Calcola `f` e la quota di output leggendo manifesto e `usage.jsonl` delle run.

    Il costo e' **calcolato** sul listino di `models.toml` a partire dai token
    che il fornitore dichiara, non misurato in fattura. Un consumo con un'unita'
    senza prezzo non si butta: si conta in `unpriced_records`.

    Quota di output: `output_cost_share` e' costo dei token di output su costo
    totale (e' quello che la soglia del 50% giudica); `output_token_share` e'
    la stessa quota in token, a fianco per trasparenza.
    """
    righe = [json.loads(r) for r in Path(manifest_path).read_text().splitlines() if r]
    tutte = [r for r in righe if r.get("task_id")]
    # I guasti della campagna non dicono nulla sul modello: fuori da `f`.
    run = [r for r in tutte if r.get("status") not in ("setup_failed", "build_failed")]

    per_task: dict[str, list[bool]] = {}
    for r in run:
        per_task.setdefault(r["task_id"], []).append(bool(r["success"]))

    costo_riportato: float | None = None
    record_con_costo_riportato = 0
    cause: dict[str, int] = {}
    for r in run:
        if not r.get("success"):
            stato = r.get("status", "unknown")
            causa = stato if stato != RunStatus.COMPLETED else "verification_failed"
            cause[causa] = cause.get(causa, 0) + 1
    request_id_visti: dict[str, int] = {}
    costo_totale = costo_output = 0.0
    token_totali = token_output = 0.0
    non_prezzati = 0
    senza_usage = 0
    chiamate_non_prezzabili = 0
    for r in run:
        cartella = Path(runs_root) / str(r.get("run_id"))
        eventi = cartella / "events.jsonl"
        if r.get("run_id") and eventi.exists():
            for linea in eventi.read_text().splitlines():
                evento = json.loads(linea)
                if evento.get("event_type") != "unpriced_usage":
                    continue
                dettagli = evento.get("details", {})
                chiamate_non_prezzabili += 1
                if dettagli.get("request_id"):
                    request_id_visti[dettagli["request_id"]] = request_id_visti.get(dettagli["request_id"], 0) + 1
                if dettagli.get("reported_cost") is not None:
                    costo_riportato = (costo_riportato or 0.0) + dettagli["reported_cost"]
                    record_con_costo_riportato += 1
        percorso = cartella / "usage.jsonl"
        if not r.get("run_id") or not percorso.exists():
            senza_usage += 1
            continue
        for linea in percorso.read_text().splitlines():
            record = json.loads(linea)["record"]
            record_senza_prezzo = False
            if record.get("request_id"):
                request_id_visti[record["request_id"]] = request_id_visti.get(record["request_id"], 0) + 1
            if record.get("reported_cost") is not None:
                costo_riportato = (costo_riportato or 0.0) + record["reported_cost"]
                record_con_costo_riportato += 1
            for unita, quantita in record["quantities"].items():
                if unita.endswith("_tokens"):
                    token_totali += quantita
                    if unita == "output_tokens":
                        token_output += quantita
                try:
                    costo = registry.cost(record["model"], unita, quantita)
                except (UnitNotFound, ModelNotFound):
                    record_senza_prezzo = True
                    continue
                costo_totale += costo
                if unita == "output_tokens":
                    costo_output += costo
            non_prezzati += record_senza_prezzo

    return CampaignReport(
        runs=len(run),
        failure_rate=1 - sum(bool(r["success"]) for r in run) / len(run) if run else 0.0,
        failure_rate_by_task={t: 1 - sum(v) / len(v) for t, v in per_task.items()},
        total_cost=costo_totale,
        output_cost_share=costo_output / costo_totale if costo_totale else 0.0,
        output_token_share=token_output / token_totali if token_totali else 0.0,
        unpriced_records=non_prezzati,
        excluded_runs=len(tutte) - len(run),
        runs_without_usage=senza_usage,
        reported_cost=costo_riportato,
        reported_records=record_con_costo_riportato,
        failures_by_cause=cause,
        duplicate_request_ids=sum(1 for n in request_id_visti.values() if n > 1),
        unpriced_calls=chiamate_non_prezzabili,
    )


# ── Riga di comando ────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent


def _carica_task(percorso: Path, only: list[str] | None) -> list[Task]:
    """Task da un file TOML o da una cartella di esercizi polyglot, con filtro per nome."""
    if Path(percorso).is_dir():
        from polyglot import load_tasks as carica_polyglot
        return carica_polyglot(percorso, only)
    tasks = load_tasks(percorso)
    if only is not None:
        ignoti = [nome for nome in only if nome not in {t.id for t in tasks}]
        if ignoti:
            raise CampaignError(f"task inesistenti: {', '.join(ignoti)}")
        tasks = [t for t in tasks if t.id in only]
    return tasks


def build_parser() -> argparse.ArgumentParser:
    """Costruisce la CLI senza accedere a ambiente, rete o Docker."""
    parser = argparse.ArgumentParser(description="Campagna di misura ORC (M2s.4)")
    sotto = parser.add_subparsers(dest="comando", required=True)

    run = sotto.add_parser("run", help="lancia i task (in serie, o in parallelo con --workers)")
    run.add_argument("--tasks", type=Path, default=PROJECT_ROOT / "campaigns" / "m2s4a.toml",
                     help="file TOML dei task, oppure cartella di esercizi polyglot "
                          "(vedi fetch-polyglot)")
    run.add_argument("--only", default=None,
                     help="solo questi task, separati da virgola (utile per le prove)")
    run.add_argument("--role", default="worker")
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--budget-usd", type=float, required=True,
                     help="tetto in USD per ogni agente (obbligatorio: ogni run reale ha un tetto)")
    run.add_argument("--max-total-usd", type=float, required=True,
                     help="tetto in USD per l'intera campagna (obbligatorio)")
    run.add_argument("--max-iterations", type=int, default=config.MAX_ITERAZIONI)
    run.add_argument("--workers", type=int, default=1,
                     help="quante run in parallelo (predefinito 1: in serie, come sempre). "
                          "Ogni run ha il suo agente e il suo container; il tetto totale conta "
                          "anche il tetto per run di quelle in volo")
    run.add_argument("--network", choices=RETI_AMMESSE, default="none",
                     help="rete della sandbox degli agenti: none (la base delle misure) o bridge "
                          "(condizione 'con internet'); setup e verifica restano sempre senza rete")
    run.add_argument("--campaign-id", default=None,
                     help="nome della campagna; predefinito: data e ora")

    fetch = sotto.add_parser("fetch-polyglot", help="scarica gli esercizi polyglot al commit fissato")
    fetch.add_argument("--dest", type=Path, default=PROJECT_ROOT / "campaigns" / "data" / "polyglot-python")

    web = sotto.add_parser("fetch-webtasks",
                           help="scarica WebGen-Bench e ArtifactsBench ai commit fissati (R1)")
    web.add_argument("--dest", type=Path, default=PROJECT_ROOT / "campaigns" / "data" / "webtasks")

    rep = sotto.add_parser("report", help="calcola f e quota di output di una campagna")
    rep.add_argument("campaign_id")
    return parser


def main(argv: Sequence[str] | None = None, *, dotenv_path: Path | None = None) -> int:
    """Esegue `run` o `report`. Restituisce 0 se non ci sono errori di configurazione."""
    args = build_parser().parse_args(argv)
    runs_root = PROJECT_ROOT / "runs"
    campaigns_dir = runs_root / "campaigns"
    registry = ModelRegistry.from_file(PROJECT_ROOT / "models.toml")
    dotenv = dotenv_path if dotenv_path is not None else PROJECT_ROOT / ".env"

    if args.comando == "fetch-polyglot":
        from polyglot import fetch_polyglot
        try:
            cartella = fetch_polyglot(args.dest)
        except CampaignError as errore:
            print(f"errore: {errore}", file=sys.stderr)
            return 2
        print(f"esercizi scaricati in {cartella}")
        return 0

    if args.comando == "fetch-webtasks":
        from webtasks import fetch_webtasks
        try:
            cartella = fetch_webtasks(args.dest)
        except CampaignError as errore:
            print(f"errore: {errore}", file=sys.stderr)
            return 2
        print(f"compiti dei siti scaricati in {cartella}")
        return 0

    if args.comando == "report":
        manifesto = campaigns_dir / f"{args.campaign_id}.jsonl"
        if not manifesto.exists():
            print(f"errore: campagna '{args.campaign_id}' non trovata ({manifesto})",
                  file=sys.stderr)
            return 2
        esito = report(manifesto, runs_root, registry)
        print(f"run con il modello interpellato: {esito.runs}")
        print(f"run escluse per guasto della campagna: {esito.excluded_runs}")
        print(f"run senza usage.jsonl (costo mancante dal totale): {esito.runs_without_usage}")
        print(f"f (tasso di fallimento): {esito.failure_rate:.1%}")
        if esito.failures_by_cause:
            elenco = ", ".join(f"{c}: {n}" for c, n in sorted(esito.failures_by_cause.items()))
            print(f"fallimenti per causa: {elenco}")
        else:
            print("fallimenti per causa: nessuno")
        print(f"request_id duplicati: {esito.duplicate_request_ids}")
        for task, f in sorted(esito.failure_rate_by_task.items()):
            print(f"  {task}: {f:.1%}")
        print(f"costo CALCOLATO sul listino (non addebitato): ${esito.total_cost:.5f}")
        if esito.reported_cost is None:
            print("costo RIPORTATO dal fornitore: nessun record lo riporta")
        else:
            print(f"costo RIPORTATO dal fornitore: ${esito.reported_cost:.5f} "
                  f"({esito.reported_records} record)")
        print(f"quota di output in costo: {esito.output_cost_share:.1%}")
        print(f"quota di output in token: {esito.output_token_share:.1%}")
        print(f"record con consumi senza prezzo: {esito.unpriced_records}")
        print(f"chiamate non prezzabili: {esito.unpriced_calls} (fuori dal costo calcolato, "
              f"dentro quello riportato)")
        return 0

    try:
        if args.workers < 1:
            raise CampaignError(f"workers deve essere almeno 1, non {args.workers}")
        tasks = _carica_task(args.tasks, args.only.split(",") if args.only else None)
        ensure_image_available(config.DOCKER_IMAGE, attempts=config.DOCKER_TENTATIVI_AVVIO,
                               delay=config.DOCKER_ATTESA_AVVIO_S,
                               max_total_s=config.DOCKER_ATTESA_AVVIO_MAX_S)
        config.load_environment(dotenv)
        factory = AgentFactory(
            registry, runs_root=runs_root, workspaces_root=PROJECT_ROOT / "workspace",
            budget_usd=args.budget_usd,
            tools_builder=tools_builder_for(args.network))
    except (CampaignError, RegistryError, RuntimeError, ValueError) as errore:
        print(f"errore: {errore}", file=sys.stderr)
        return 2

    campaign_id = args.campaign_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        righe = run_campaign(
            factory, tasks, role=args.role, repetitions=args.repetitions,
            campaign_id=campaign_id, campaigns_dir=campaigns_dir, shell=shell_docker,
            max_total_usd=args.max_total_usd, max_iterations=args.max_iterations,
            environment=sandbox_environment(config.DOCKER_IMAGE, args.network),
            workers=args.workers, reserve_per_run_usd=args.budget_usd)
    except CampaignError as errore:
        print(f"errore: {errore}", file=sys.stderr)
        return 2
    print(f"campagna '{campaign_id}': {len([r for r in righe if r.get('task_id')])} run; "
          f"poi: python campaign.py report {campaign_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
