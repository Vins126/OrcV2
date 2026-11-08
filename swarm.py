"""Sciame minimo (braccio C, R3): piano, pezzi concorrenti e un solo tentativo di correzione.

Skill obbligatorie: design al planner, lavoro e verifica ai worker e alla correzione.

Nota di design (tesi):
    Il giro e' piano -> ondate -> cancello -> al massimo una correzione.
      - Il planner (Opus) scrive un piano JSON; `swarm_plan.parse_plan` lo controlla e,
        se e' invalido, l'errore torna allo stesso planner al massimo due volte.
      - Il worker di ogni pezzo lo sceglie il planner fra `worker_cheap` (DeepSeek) e
        `worker` (Kimi), vedendo i prezzi del listino (P3/P4 del 2 nov 2026).
      - I pezzi di un'ondata girano in parallelo sullo stesso workspace; un pezzo con
        max_iterations e' parziale e lascia partire i dipendenti; gli altri fallimenti
        bloccano solo chi ne dipende (S4, task 7).
      - Se il cancello rifiuta il sito, ci sono pezzi incompleti o problemi nei file, la correzione la fa
        un agente Opus nuovo: il ragionamento di un modello non si rimanda a un altro
        (R3.4, da R2.2; S2, task 7).
      - Il tetto e' uno per tutta la squadra (`Team`): al tetto non parte altro lavoro e
        si consegna cio' che c'e' (R3.5, opzione (a)).
    Il registro `sciame/swarm.jsonl` lo scrive solo il thread principale.
    A fine ondata il controllo dei file (S3, task 7, P31-D1) segnala modifiche ai file
    di pezzi di ondate gia' chiuse (P48-D1) e file temporanei senza proprietario; le segnalazioni
    fanno partire la correzione S2 se il tetto lo consente.
    Limiti: fra pezzi della stessa ondata non si sa chi ha scritto un file;
    le cartelle in IGNORED_DIRS non si controllano.
"""

import hashlib
import json
import os
import stat
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from accounting import ModelRegistry
from agent_factory import Team
from gate import GateVerdict, check_site
from parallel_runner import Admission, JobOutcome, run_parallel
from swarm_plan import Piece, Plan, PlanError, contract_routes, parse_plan, waves
from tools.load_skill import REQUIRED_SKILLS_PLANNER, REQUIRED_SKILLS_WORKER

WORKER_ROLES = ("worker", "worker_cheap")
PROCEEDING_STATES = ("completed", "max_iterations")
PLANNER_ROLE = "planner"
MAX_PLAN_ATTEMPTS = 3
SWARM_DIR = "sciame"
IGNORED_DIRS = frozenset({"node_modules", "dist", ".taste-skill", ".git", ".vite", "__pycache__"})


def snapshot(workspace: Path) -> dict[str, str]:
    """Rileva contenuti e destinazioni dei link senza attraversare link o cartelle escluse."""
    fingerprints: dict[str, str] = {}
    for root, directories, filenames in os.walk(workspace, followlinks=False):
        directories[:] = [name for name in directories if name not in IGNORED_DIRS]
        # I link a cartelle sono elencati fra le cartelle, ma si registrano come link.
        for name in [*directories, *filenames]:
            path = Path(root) / name
            relative = path.relative_to(workspace).as_posix()
            # Un file sparito o illeggibile non deve far cadere lo sciame: si salta.
            try:
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    fingerprints[relative] = "link:" + os.readlink(path)
                elif stat.S_ISREG(mode):
                    with path.open("rb") as stream:
                        fingerprints[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
            except OSError:
                continue
    return fingerprints


def is_temporary(path: str) -> bool:
    """Riconosce i nomi finali usati per file provvisori o copie di lavoro."""
    name = Path(path).name
    return name.endswith((".bak", ".orig", ".preview", ".tmp", ".old", "~")) or name.startswith(("tmp-", "tmp_"))


@dataclass(frozen=True)
class SwarmResult:
    """Consegna dello sciame con costi, registro e stati dei pezzi."""

    status: str
    gate: GateVerdict | None
    escalated: bool
    total_cost: float
    run_ids: list[str]
    log_path: Path
    pieces: dict[str, str]


def planner_prompt(task_prompt: str, registry: ModelRegistry, routes: Sequence[str]) -> str:
    """Descrive al planner il contratto e i prezzi dei worker disponibili."""
    prices = []
    for role in WORKER_ROLES:
        model = registry.model_for(role)
        price = registry.models[model]["prices"]
        prices.append(f"{role}: {model}, input ${price['input_tokens']:.2f}, "
                      f"output ${price['output_tokens']:.2f} per million tokens")
    return "\n".join([
        "Produce ONLY a JSON plan. Do not write files.",
        'Format: {"style": "shared visual style", '
        '"contract": {"GET /api/items": "200 [{\\"id\\": number, \\"name\\": string}]"}, '
        '"pieces": [{"id": "skeleton", '
        '"files": ["start.sh"], "depends_on": [], "description": "...", '
        '"routes": [], "worker": "worker_cheap"}]}',
        "R3.1 (a): first create a shared skeleton piece: start.sh, package.json or equivalent, "
        "a server with empty contract routes, layout and stylesheet. Then parallel pieces: "
        "one interface section per file and one server module per contract resource. "
        "Make those pieces depend on the skeleton; declare any further dependencies.",
        "Files must be disjoint across pieces. Assign each contract route to exactly one piece. "
        "The skeleton provides the empty wiring; the resource piece owns the route implementation.",
        'In "contract" write, for every contract route, the exact response shape: '
        "status codes and JSON fields with their types, for success and errors. "
        "Server and interface pieces must follow it exactly.",
        "Contract routes:", *routes, "Available workers:", *prices,
        "On the Design Arena Website leaderboard Kimi K3.1 Pro is about 15 Elo above "
        "DeepSeek V4.1 Flash (about 52% of head-to-head preferences) at 13-17 times the price",
        "Default to worker_cheap for every piece. Choose worker only for a piece whose core is "
        "hard to get right: non-trivial client logic (for example drag and drop, canvas drawing, "
        "real-time updates, multi-step state) or articulated animations. Layout, content sections, "
        "forms, styling, the skeleton and server modules go to worker_cheap.",
        "TASK", task_prompt,
    ])


def worker_prompt(task_prompt: str, plan: Plan, piece: Piece) -> str:
    """Assegna un pezzo mostrando anche dove si trovano le interfacce vicine."""
    others = [f"{other.id}: {', '.join(other.files)}" for other in plan.pieces if other.id != piece.id]
    contract = (["ROUTE CONTRACT", *[f"{route}: {shape}" for route, shape in plan.contract.items()]]
                if plan.contract else [])
    # Chi e' solo nella sua ondata non deve aspettare nessuno: lo scheletro di 842 (campagna MVP,
    # 8 nov 2026) ha atteso 300 s i file di pezzi che partono solo dopo di lui.
    wave = next(batch for batch in waves(plan) if piece in batch)
    company = ("The workspace is shared with other workers working in parallel. " if len(wave) > 1 else
               "You are the only worker running now: the pieces that depend on you start after you "
               "finish, so their files may not exist yet. Do not wait for them or check for them. ")
    return "\n".join([
        "TASK", task_prompt, "SHARED STYLE", plan.style,
        "YOUR PIECE", piece.id, piece.description,
        "YOUR FILES", *piece.files, "YOUR ROUTES", *piece.routes,
        *contract,
        "OTHER PIECES (id and files)", *others,
        "Write only your own files. " + company +
        "Do not modify files owned by other pieces. The skeleton writes start.sh. "
        "Never hide, disable or restyle other pieces to inspect your own; "
        "if you add temporary code, remove it before you finish. "
        "Do not leave backup, preview or temporary files in the workspace: "
        "put throwaway scripts in /tmp within the same bash command.",
    ])


def escalation_prompt(task_prompt: str, plan: Plan, reason: str | None,
                      incomplete: Mapping[str, str],
                      file_issues: Mapping[str, str] | None = None) -> str:
    """Chiede una correzione sul sito gia' consegnato."""
    rejection = ["GATE REJECTION", reason] if reason else []
    unfinished = (["INCOMPLETE PIECES", *[
        f"{piece.id}: {incomplete[piece.id]} (files: {', '.join(piece.files)})"
        for piece in plan.pieces if piece.id in incomplete]] if incomplete else [])
    files = (["FILE ISSUES", *[f"{path}: {issue}" for path, issue in file_issues.items()]]
             if file_issues else [])
    return "\n".join([
        "TASK", task_prompt, "PLAN", json.dumps(asdict(plan)), *rejection, *unfinished, *files,
        "Fix the existing site in this shared workspace. Complete the incomplete pieces. "
        "Remove temporary code (for example rules hiding sections) and any temporary, backup "
        "or preview files left by workers. Finish when start.sh starts the site, "
        "/ responds with HTTP status below 400 and there are no JavaScript errors. "
        "You may use view_site to inspect the site. "
        "Restore files changed by a piece that does not own them if that breaks the owner's work, "
        "and delete leftover temporary files.",
    ])


def run_swarm(factory: Any, prompt: str, workspace: Path, out_dir: Path, *,
              budget_usd: float | None, max_iterations: int | None = None,
              max_parallel: int = 4,
              gate: Callable[[Path, Path], GateVerdict] = check_site) -> SwarmResult:
    """Esegue il piano per ondate, con spesa condivisa e registro dal thread chiamante."""
    team = Team(budget_usd)
    log_path = Path(out_dir) / SWARM_DIR / "swarm.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    agents: list[Any] = []
    build_lock = threading.Lock()
    states: dict[str, str] = {}
    budget_stop = exhausted = escalated = False

    def emit(event: str, **details: Any) -> None:
        with log_path.open("a") as stream:
            stream.write(json.dumps({"event": event, **details}) + "\n")

    def build(role: str, required_skills: Sequence[str]) -> Any:
        # La costruzione e la lista seguono lo stesso ordine; gli incarichi restano paralleli.
        with build_lock:
            agent = factory.build(role, workspace=workspace, team=team, required_skills=required_skills)
            agents.append(agent)
        return agent

    def run_id(agent: Any) -> str | None:
        return agent.ledgers[-1].run_id if agent.ledgers else None

    def at_limit() -> bool:
        return budget_usd is not None and team.accountant.total_cost >= budget_usd

    def stop_budget() -> None:
        nonlocal budget_stop
        if not budget_stop:
            budget_stop = True
            emit("budget_stop", total_cost=team.accountant.total_cost, limit=budget_usd)

    def finish(status: str, verdict: GateVerdict | None = None) -> SwarmResult:
        total_cost = team.accountant.total_cost
        emit("end", status=status, total_cost=total_cost, breakdown=team.accountant.breakdown(),
             gate=verdict.to_dict() if verdict is not None else None, escalated=escalated)
        return SwarmResult(status, verdict, escalated, total_cost,
                           [ledger.run_id for agent in agents for ledger in agent.ledgers],
                           log_path, states)

    routes = contract_routes(prompt)
    planner = build(PLANNER_ROLE, REQUIRED_SKILLS_PLANNER)
    instruction = planner_prompt(prompt, factory.registry, routes)
    plan: Plan | None = None
    for attempt in range(1, MAX_PLAN_ATTEMPTS + 1):
        result = planner.assign(instruction, max_iterations=max_iterations)
        error = None
        if result.status == "completed":
            try:
                plan = parse_plan(result.final_message or "", routes=routes, workers=WORKER_ROLES)
            except PlanError as failure:
                error = str(failure)
        else:
            error = str(result.status)
        emit("plan", attempt=attempt, valid=plan is not None, error=error,
             agent_id=planner.agent_id, run_id=run_id(planner))
        if result.status != "completed":
            return finish("budget_exhausted" if result.status == "budget_exhausted" else "plan_failed")
        if plan is not None:
            break
        instruction = f"Correct the plan: {error}. Reply only with the corrected JSON."
    if plan is None:
        return finish("plan_failed")

    # Conserva dipendenze e worker scelti per l'analisi a posteriori dello sciame.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    (log_path.parent / "plan.json").write_text(
        json.dumps(asdict(plan), ensure_ascii=False, indent=2), encoding="utf-8")

    def piece_event(piece: Piece, wave: int, status: str, agent: Any = None,
                    error_type: str | None = None) -> None:
        nonlocal exhausted
        states[piece.id] = status
        exhausted = exhausted or status == "budget_exhausted"
        emit("piece", piece_id=piece.id, wave=wave, role=piece.worker,
             model=agent.model if agent is not None else factory.registry.model_for(piece.worker),
             agent_id=agent.agent_id if agent is not None else None,
             run_id=run_id(agent) if agent is not None else None, status=status,
             cost=agent.accountant.total_cost if agent is not None else 0.0, error_type=error_type)

    def work(piece: Piece) -> tuple[Any, str, str | None]:
        agent = None
        try:
            agent = build(piece.worker, REQUIRED_SKILLS_WORKER)
            result = agent.assign(worker_prompt(prompt, plan, piece), max_iterations=max_iterations)
            return agent, str(result.status), None
        except Exception as error:
            return agent, "unexpected_error", type(error).__name__

    owners = {path: piece.id for piece in plan.pieces for path in piece.files}
    file_issues: dict[str, str] = {}
    # Pezzi delle ondate gia' chiuse: solo il loro lavoro puo' essere rovinato da un altro pezzo.
    # Un file di un pezzo che non ha ancora lavorato (il segnaposto dello scheletro) lo riscrive
    # il proprietario, quindi non si segnala (P48-D1, prova di C su 000058 del 7 nov 2026).
    done_ids: set[str] = set()
    for wave, batch in enumerate(waves(plan)):
        before = snapshot(workspace)
        ready = []
        for piece in batch:
            if at_limit():
                stop_budget()
                piece_event(piece, wave, "not_started")
            elif any(states[dependency] not in PROCEEDING_STATES for dependency in piece.depends_on):
                piece_event(piece, wave, "skipped")
            else:
                ready.append(piece)

        def admit(_piece: Piece, _in_flight: int) -> Admission:
            if at_limit():
                stop_budget()
                return Admission.STOP
            return Admission.START

        def on_done(outcome: JobOutcome[Piece, tuple[Any, str, str | None]]) -> None:
            if outcome.result is not None:
                agent, status, error_type = outcome.result
                piece_event(outcome.job, wave, status, agent, error_type)
            else:
                piece_event(outcome.job, wave, "unexpected_error",
                            error_type=type(outcome.error).__name__)

        outcomes = run_parallel(ready, work, max_workers=max_parallel, admit=admit, on_done=on_done)
        after = snapshot(workspace)
        changed = sorted(path for path in before.keys() | after.keys()
                         if before.get(path) != after.get(path))
        batch_ids = {piece.id for piece in batch}
        foreign: dict[str, str] = {}
        temporary: list[str] = []
        for path in changed:
            owner = owners.get(path)
            if owner is not None and owner in done_ids:
                foreign[path] = owner
                file_issues[path] = f"changed, owned by {owner}"
            elif owner is None and is_temporary(path) and path in after:
                temporary.append(path)
                file_issues[path] = "temporary file"
        emit("file_check", wave=wave, foreign=foreign, temporary=temporary)
        done_ids |= batch_ids
        for outcome in outcomes:
            if not outcome.started:
                piece_event(outcome.job, wave, "not_started")

    def inspect(phase: str) -> GateVerdict | None:
        try:
            verdict = gate(workspace, log_path.parent / f"cancello-{phase}")
        except Exception as error:
            emit("gate", phase=phase, accepted=None, reason=None, error=str(error))
            return None
        emit("gate", phase=phase, accepted=verdict.accepted, reason=verdict.reason)
        return verdict

    verdict = inspect("initial")
    accepted = verdict is not None and verdict.accepted

    # Un pezzo fermato dal limite di iterazioni con tutti i suoi file, in un sito che il
    # cancello accetta, ha fatto il suo lavoro: DeepSeek continua a verificare finche' non lo
    # ferma il limite, e la correzione di Opus partiva lo stesso (1,05 $ su 000040, 8 nov 2026).
    def finished(piece: Piece) -> bool:
        status = states[piece.id]
        return status == "completed" or (
            status == "max_iterations" and accepted
            and all((workspace / path).is_file() for path in piece.files))

    incomplete = {piece.id: states[piece.id] for piece in plan.pieces if not finished(piece)}
    rejected = verdict is not None and not verdict.accepted
    if not (budget_stop or exhausted or at_limit()) and (rejected or incomplete or file_issues):
        escalated = True
        agent = None
        error_type = None
        try:
            agent = build(PLANNER_ROLE, REQUIRED_SKILLS_WORKER)
            reason = verdict.reason if verdict is not None and not verdict.accepted else None
            result = agent.assign(escalation_prompt(prompt, plan, reason, incomplete, file_issues),
                                  max_iterations=max_iterations)
            status = str(result.status)
        except Exception as error:
            status = "unexpected_error"
            error_type = type(error).__name__
        exhausted = exhausted or status == "budget_exhausted"
        emit("escalation", agent_id=agent.agent_id if agent is not None else None,
             run_id=run_id(agent) if agent is not None else None, status=status,
             cost=agent.accountant.total_cost if agent is not None else 0.0, error_type=error_type,
             incomplete=incomplete, file_issues=file_issues)
        verdict = inspect("after_escalation")
    return finish("budget_exhausted" if budget_stop or exhausted else "completed", verdict)
