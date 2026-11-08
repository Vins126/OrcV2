"""Giudice a coppie, isolato e riprendibile: calibrazione R1.9 e coppie della campagna MVP."""

import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from task_model import CampaignError

JUDGE_MODEL = "gpt-6.1-sol"
JUDGE_EFFORT = "high"
WIDTH_ORDER = (1440, 768, 375)
CALL_TIMEOUT_S = 120
ATTEMPTS = 2
TIMEOUT_RETRIES = 3
FIXED_QUESTIONS = (
    "La pagina fa cio' che chiede il compito?",
    "Le informazioni sono organizzate in modo chiaro?",
    "Il testo e' leggibile a tutte e tre le larghezze?",
    "Colori, caratteri e spaziature sono coerenti?",
    "Su telefono il layout si adatta senza elementi tagliati o sovrapposti?",
    "Nel complesso sembra un sito professionale?",
)
PROMPT_DIR = Path(__file__).resolve().parent / "campaigns" / "r1_giudice"
VOTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "voto": {"type": "integer", "minimum": -2, "maximum": 2},
        "motivo": {"type": "string"},
    },
    "required": ["voto", "motivo"],
    "additionalProperties": False,
}
CHECKLIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risposte": {"type": "array", "items": {"type": "boolean"},
                     "minItems": len(FIXED_QUESTIONS), "maxItems": len(FIXED_QUESTIONS)},
    },
    "required": ["risposte"],
    "additionalProperties": False,
}


class JudgeError(CampaignError):
    """Dati o configurazione del giudice non validi."""


class JudgeQuotaError(JudgeError):
    """Quota esaurita: il lotto si ferma conservando i risultati gia' scritti."""


@dataclass(frozen=True)
class Guide:
    """Scheda del compito, uguale a quella mostrata ai votanti."""

    title: str
    objective: str
    look_for: tuple[str, ...]
    note: str | None


@dataclass(frozen=True)
class RunOutput:
    """Risposta, durata e consumo di una chiamata, anche se scaduta."""

    text: str | None
    seconds: float
    usage: dict[str, int]
    error: str | None
    timed_out: bool = False


Runner = Callable[[str, Sequence[Path], dict[str, Any]], RunOutput]


@dataclass(frozen=True)
class OrderResult:
    """Voto in un ordine, con chiamate e tempi scaduti di tutti i tentativi."""

    value: int | None
    attempts: int
    outputs: tuple[RunOutput, ...]
    timeouts: int


@dataclass(frozen=True)
class PairResult:
    """Media dei due ordini: un valore positivo preferisce il lato destro."""

    value: float | None
    forward: OrderResult
    backward: OrderResult


@dataclass(frozen=True)
class ChecklistResult:
    """Risposte alle domande fisse, con chiamate e tempi scaduti registrati."""

    answers: tuple[bool, ...] | None
    attempts: int
    outputs: tuple[RunOutput, ...]
    timeouts: int


@dataclass(frozen=True)
class Judgment:
    """Risultato persistito: positivo se vince il modello maggiore della coppia."""

    item: str
    pair_id: str
    value: float | None
    forward: int | None
    backward: int | None
    attempts: int
    seconds: float
    usage: dict[str, int]
    date: str
    meta: dict[str, Any]
    timeouts: int = 0


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise JudgeError(f"{path}: lettura non riuscita: {error}") from error


def load_guides(path: Path) -> dict[str, Guide]:
    """Legge le schede indicizzate dall'impronta SHA256 del testo originale."""
    data = _read_json(path)
    try:
        if not isinstance(data, dict):
            raise JudgeError(f"{path}: le guide devono essere un oggetto")
        guides = {}
        for digest, row in data.items():
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(row, dict):
                raise JudgeError(f"{path}: chiave o scheda non valida: {digest}")
            title, objective, look_for, note = (row[name] for name in ("title", "objective", "lookFor", "note"))
            if (not isinstance(title, str) or not title.strip()
                    or not isinstance(objective, str) or not objective.strip()
                    or not isinstance(look_for, list)
                    or not all(isinstance(text, str) and text.strip() for text in look_for)
                    or (note is not None and not isinstance(note, str))):
                raise JudgeError(f"{path}: campi della guida non validi: {digest}")
            guides[digest] = Guide(title, objective, tuple(look_for), note if note and note.strip() else None)
        return guides
    except (KeyError, TypeError, ValueError) as error:
        raise JudgeError(f"{path}: formato delle guide non valido: {error}") from error


def _prompt(name: str, task: str, guide: Guide, extra: Mapping[str, str] | None = None) -> str:
    try:
        prompt = (PROMPT_DIR / name).read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise JudgeError(f"{name}: lettura del prompt non riuscita: {error}") from error
    replacements = {
        "<<TITOLO>>": guide.title,
        "<<OBIETTIVO>>": guide.objective,
        "<<OSSERVARE>>": "\n".join(f"- {text}" for text in guide.look_for),
        "<<NOTA>>": f"\nNota: {guide.note}\n" if guide.note else "",
        "<<DOMANDE>>": "\n".join(f"{index}. {question}" for index, question in enumerate(FIXED_QUESTIONS, 1)),
        "<<RICHIESTA>>": task,
        **(extra or {}),
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    if re.search(r"<<[A-Z_]+>>", prompt):
        raise JudgeError(f"{name}: segnaposto non risolto nel prompt")
    return prompt


def vote_prompt(task: str, guide: Guide) -> str:
    """Compila il prompt del voto senza interpretare le graffe del compito."""
    return _prompt("voto.txt", task, guide)


def checklist_prompt(task: str, guide: Guide) -> str:
    """Compila il prompt delle sei domande per un solo sito."""
    return _prompt("checklist.txt", task, guide)


def parse_vote(text: str | None) -> int | None:
    """Accetta solo un intero della scala e una motivazione testuale."""
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if (isinstance(data, dict) and set(data) == {"voto", "motivo"}
            and type(data["voto"]) is int and -2 <= data["voto"] <= 2
            and isinstance(data["motivo"], str)):
        return data["voto"]
    return None


def parse_checklist(text: str | None) -> tuple[bool, ...] | None:
    """Accetta esattamente una risposta booleana per domanda fissa."""
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    answers = data.get("risposte") if isinstance(data, dict) and set(data) == {"risposte"} else None
    if (isinstance(answers, list) and len(answers) == len(FIXED_QUESTIONS)
            and all(type(answer) is bool for answer in answers)):
        return tuple(answers)
    return None


_Answer = TypeVar("_Answer")


def _attempts(prompt: str, images: Sequence[Path], schema: dict[str, Any],
              parse: Callable[[str | None], _Answer | None], runner: Runner
              ) -> tuple[_Answer | None, int, tuple[RunOutput, ...]]:
    """Ripete i tempi scaduti prima di consumare un tentativo di valutazione."""
    outputs = []
    for attempt in range(1, ATTEMPTS + 1):
        for _ in range(TIMEOUT_RETRIES + 1):
            output = runner(prompt, images, schema)
            outputs.append(output)
            if output.timed_out:
                continue
            value = parse(output.text) if output.error is None else None
            if value is not None:
                return value, attempt, tuple(outputs)
            break
    return None, ATTEMPTS, tuple(outputs)


def _check_images(images: Sequence[Path]) -> None:
    if len(images) != len(WIDTH_ORDER):
        raise JudgeError(f"servono {len(WIDTH_ORDER)} immagini per sito, in ordine {WIDTH_ORDER}")


#: Prompt di un ordine costruito da chi chiama (compito, scheda, primo sito, secondo sito).
#: Serve al giudizio a riquadri (`judge_tiles.py`), dove il numero di immagini per sito varia.
PromptFor = Callable[[str, Guide, Sequence[Path], Sequence[Path]], str]


def judge_order(task: str, guide: Guide, first: Sequence[Path], second: Sequence[Path], *,
                runner: Runner, prompt: str | None = None) -> OrderResult:
    """Vota un ordine; i tempi scaduti si ripetono entro ciascun tentativo.

    Senza `prompt` vale il protocollo calibrato: `voto.txt` e tre immagini per sito.
    Con un `prompt` proprio basta che ogni sito abbia almeno un'immagine.
    """
    if prompt is None:
        _check_images(first)
        _check_images(second)
        prompt = vote_prompt(task, guide)
    elif not first or not second:
        raise JudgeError("serve almeno un'immagine per sito")
    value, attempts, outputs = _attempts(prompt, [*first, *second], VOTE_SCHEMA, parse_vote, runner)
    return OrderResult(value, attempts, outputs, sum(output.timed_out for output in outputs))


def judge_pair(task: str, guide: Guide, left: Sequence[Path], right: Sequence[Path], *,
               runner: Runner, prompt_for: PromptFor | None = None) -> PairResult:
    """Vota comunque entrambi gli ordini e conserva i mezzi punti della media.

    Con `prompt_for` il prompt si costruisce per ciascun ordine: scambiando i siti
    cambia anche quali immagini appartengono alla proposta A.
    """
    forward_prompt = prompt_for(task, guide, left, right) if prompt_for is not None else None
    backward_prompt = prompt_for(task, guide, right, left) if prompt_for is not None else None
    forward = judge_order(task, guide, left, right, runner=runner, prompt=forward_prompt)
    backward = judge_order(task, guide, right, left, runner=runner, prompt=backward_prompt)
    value = None
    if forward.value is not None and backward.value is not None:
        value = (forward.value - backward.value) / 2
    return PairResult(value, forward, backward)


def judge_checklist(task: str, guide: Guide, images: Sequence[Path], *, runner: Runner) -> ChecklistResult:
    """Controlla un sito con la stessa politica di tentativi del voto."""
    _check_images(images)
    answers, attempts, outputs = _attempts(checklist_prompt(task, guide), images, CHECKLIST_SCHEMA, parse_checklist, runner)
    return ChecklistResult(answers, attempts, outputs, sum(output.timed_out for output in outputs))


def _stream_text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _codex_events(stdout: str | bytes | None) -> Iterator[dict[str, Any]]:
    """Legge solo gli eventi JSON validi, anche da un'uscita parziale in byte."""
    for line in _stream_text(stdout).splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _check_quota(stdout: str | bytes | None, stderr: str | bytes | None) -> None:
    """Cerca limiti reali negli errori, mai nel testo o nel ragionamento del modello."""
    messages = [_stream_text(stderr)]
    for event in _codex_events(stdout):
        message = None
        if event.get("type") == "error":
            message = event.get("message")
        elif event.get("type") == "turn.failed" and isinstance(event.get("error"), dict):
            message = event["error"].get("message")
        if isinstance(message, str):
            messages.append(message)
    for message in messages:
        if "usage limit" in message.lower() or "rate_limit_reached" in message.lower():
            raise JudgeQuotaError("limite di utilizzo del giudice raggiunto")


def _codex_output(stdout: str | bytes | None) -> tuple[str | None, dict[str, int], bool]:
    """Raccoglie risposta e consumo e segnala qualunque uso di strumenti."""
    message, usage = None, {}
    used_tools = False
    for event in _codex_events(stdout):
        item = event.get("item")
        if (event.get("type") in ("item.started", "item.completed") and isinstance(item, dict)
                and item.get("type") not in ("agent_message", "reasoning")):
            used_tools = True
        if (event.get("type") == "item.completed" and isinstance(item, dict)
                and item.get("type") == "agent_message" and isinstance(item.get("text"), str)):
            message = item["text"]
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = {key: value for key, value in event["usage"].items() if type(value) is int and value >= 0}
    return message, usage, used_tools


def codex_runner(*, model: str = JUDGE_MODEL, effort: str = JUDGE_EFFORT,
                 timeout_s: float = CALL_TIMEOUT_S, executable: str = "codex",
                 run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> Runner:
    """Isola immagini e ambiente; scarta le risposte ottenute usando strumenti."""
    def invoke(prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        started = time.perf_counter()
        workdir: Path | None = None
        schema_path: Path | None = None
        try:
            workdir = Path(tempfile.mkdtemp(prefix="orc-judge-"))
            copies = []
            for index, source in enumerate(images, 1):
                target = workdir / f"img-{index}.png"
                shutil.copyfile(source, target)
                copies.append(target)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                             prefix="orc-judge-schema-", delete=False) as stream:
                schema_path = Path(stream.name)
                json.dump(schema, stream, allow_nan=False)
            cmd = [executable, "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                   "--skip-git-repo-check", "-s", "read-only", "-C", str(workdir), "-m", model,
                   "-c", f"model_reasoning_effort={effort}", "--output-schema", str(schema_path), "--json"]
            for target in copies:
                cmd.extend(["-i", str(target)])
            cmd.extend(["--", "-"])
            env = {name: os.environ[name] for name in
                   ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME") if name in os.environ}
            result = run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout_s, env=env)
            _check_quota(result.stdout, result.stderr)
            message, usage, used_tools = _codex_output(result.stdout)
            error = None
            if used_tools:
                error = "il giudice ha usato strumenti"
            elif result.returncode != 0:
                error = f"uscita {result.returncode}: {result.stderr.strip()}"
            elif not message:
                error = "nessun messaggio finale del giudice"
            return RunOutput(message if error is None else None, time.perf_counter() - started, usage, error)
        except subprocess.TimeoutExpired as error:
            _check_quota(error.stdout, error.stderr)
            _, usage, used_tools = _codex_output(error.stdout)
            message = f"timeout dopo {timeout_s} secondi"
            if used_tools:
                message += "; il giudice ha usato strumenti"
            return RunOutput(None, time.perf_counter() - started, usage, message, timed_out=True)
        except OSError as error:
            return RunOutput(None, time.perf_counter() - started, {}, str(error))
        finally:
            if workdir is not None:
                shutil.rmtree(workdir, ignore_errors=True)
            if schema_path is not None:
                schema_path.unlink(missing_ok=True)

    return invoke


def load_judgments(path: Path) -> list[Judgment]:
    """Legge anche le vecchie righe senza timeouts, che valgono zero tempi scaduti."""
    try:
        judgments = []
        seen = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise JudgeError(f"{path}: una riga non e' un oggetto")
            judgment = Judgment(**row)
            if (not isinstance(judgment.item, str) or not judgment.item
                    or judgment.item in seen
                    or not isinstance(judgment.pair_id, str) or not judgment.pair_id
                    or (judgment.value is not None and (type(judgment.value) not in (int, float)
                        or judgment.value not in (-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2)))
                    or any(value is not None and (type(value) is not int or not -2 <= value <= 2)
                           for value in (judgment.forward, judgment.backward))
                    or type(judgment.attempts) is not int or not 2 <= judgment.attempts <= 2 * ATTEMPTS
                    or type(judgment.timeouts) is not int
                    or not 0 <= judgment.timeouts <= judgment.attempts * (TIMEOUT_RETRIES + 1)
                    or type(judgment.seconds) not in (int, float)
                    or not math.isfinite(judgment.seconds) or judgment.seconds < 0
                    or not isinstance(judgment.usage, dict)
                    or not all(isinstance(key, str) and type(value) is int and value >= 0
                               for key, value in judgment.usage.items())
                    or not isinstance(judgment.date, str) or not isinstance(judgment.meta, dict)):
                raise JudgeError(f"{path}: riga del giudizio non valida")
            datetime.fromisoformat(judgment.date)
            seen.add(judgment.item)
            judgments.append(judgment)
        # Un filtro puo' aver salvato prima una voce successiva del pacchetto.
        return sorted(judgments, key=lambda judgment: judgment.item)
    except (OSError, ValueError, TypeError) as error:
        raise JudgeError(f"{path}: lettura dei giudizi non riuscita: {error}") from error


def _package_entries(package_dir: Path, key_file: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Controlla l'impronta e collega le voci pubbliche alla chiave privata."""
    path = package_dir / "coppie.js"
    key = _read_json(key_file)
    try:
        source = path.read_bytes()
        if not isinstance(key, dict) or key["package_id"] != hashlib.sha256(source).hexdigest():
            raise JudgeError("package_id diverso dalla chiave o dal pacchetto")
        prefix = "window.COPPIE = "
        script = source.decode("utf-8")
        if not script.startswith(prefix):
            raise JudgeError(f"{path}: assegnazione COPPIE mancante")
        entries, end = json.JSONDecoder().raw_decode(script[len(prefix):])
        if not script[len(prefix) + end:].lstrip().startswith(";"):
            raise JudgeError(f"{path}: assegnazione COPPIE non terminata")
        if not isinstance(entries, list) or not isinstance(key["items"], list):
            raise JudgeError(f"{path}: elenco delle voci non valido")
        by_item = {}
        for row in key["items"]:
            item = row["item"]
            if (not isinstance(item, str) or not item or item in by_item
                    or not all(isinstance(row[field], str) and row[field]
                               for field in ("pair_id", "left_model", "right_model"))
                    or row["left_model"] == row["right_model"]
                    or (row["repeat_of"] is not None and not isinstance(row["repeat_of"], str))):
                raise JudgeError(f"{key_file}: voce della chiave non valida")
            by_item[item] = row
        seen = set()
        linked = []
        for entry in entries:
            item = entry["item"]
            if not isinstance(item, str) or item in seen or item not in by_item:
                raise JudgeError(f"{path}: voce sconosciuta o doppia: {item}")
            seen.add(item)
            linked.append((entry, by_item[item]))
        if seen != set(by_item):
            raise JudgeError("le voci della chiave e del pacchetto non coincidono")
        return linked
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise JudgeError(f"{path}: formato del pacchetto non valido: {error}") from error


def _package_images(package_dir: Path, entry: dict[str, Any], side: str) -> tuple[Path, ...]:
    paths = []
    for width in WIDTH_ORDER:
        path = (package_dir / entry["images"][side][str(width)]).resolve()
        if not path.is_relative_to(package_dir.resolve()) or not path.is_file():
            raise JudgeError(f"{entry['item']}: immagine mancante o fuori dal pacchetto: {path}")
        paths.append(path)
    return tuple(paths)


def judge_package(package_dir: Path, key_file: Path, guides_file: Path, out_file: Path, *,
                  runner: Runner, meta: dict[str, Any], items: Sequence[str] | None = None) -> list[Judgment]:
    """Riprende solo con metadati identici e salva subito ogni coppia completata."""
    entries = _package_entries(package_dir, key_file)
    guides = load_guides(guides_file)
    existing = {row.item: row for row in load_judgments(out_file)} if out_file.exists() else {}
    selected = set(items) if items is not None else None
    if selected is not None and selected - {entry["item"] for entry, _ in entries}:
        raise JudgeError("il filtro contiene voci sconosciute al pacchetto")
    try:
        json.dumps(meta, allow_nan=False)
        by_item = {entry["item"]: key for entry, key in entries}
        for item, judgment in existing.items():
            if judgment.meta != meta:
                raise JudgeError(f"{out_file}: metadati diversi per il giudizio {item}")
            if (item not in by_item or by_item[item]["repeat_of"] is not None
                    or judgment.pair_id != by_item[item]["pair_id"]):
                raise JudgeError(f"{out_file}: giudizio non appartenente al pacchetto: {item}")
        prepared = []
        # Si validano tutte le voci selezionate prima di spendere una chiamata.
        for entry, key in entries:
            if key["repeat_of"] is not None or (selected is not None and entry["item"] not in selected):
                continue
            task = entry["task"]
            if not isinstance(task, str):
                raise JudgeError(f"{entry['item']}: testo del compito non valido")
            digest = hashlib.sha256(task.encode("utf-8")).hexdigest()
            if digest not in guides:
                raise JudgeError(f"{entry['item']}: guida mancante per il compito {digest}")
            guide = guides[digest]
            left = _package_images(package_dir, entry, "s")
            right = _package_images(package_dir, entry, "d")
            prepared.append((entry, key, guide, left, right))
        out_file.parent.mkdir(parents=True, exist_ok=True)
        judgments = []
        with out_file.open("a", encoding="utf-8") as stream:
            for entry, key, guide, left, right in prepared:
                item = entry["item"]
                if item in existing:
                    judgments.append(existing[item])
                    continue
                pair = judge_pair(entry["task"], guide, left, right, runner=runner)
                outputs = pair.forward.outputs + pair.backward.outputs
                usage: dict[str, int] = {}
                for output in outputs:
                    for name, count in output.usage.items():
                        usage[name] = usage.get(name, 0) + count
                sign = 1 if key["right_model"] > key["left_model"] else -1
                judgment = Judgment(
                    item=item, pair_id=key["pair_id"],
                    value=pair.value * sign if pair.value is not None else None,
                    forward=pair.forward.value, backward=pair.backward.value,
                    attempts=pair.forward.attempts + pair.backward.attempts,
                    seconds=sum(output.seconds for output in outputs), usage=usage,
                    date=datetime.now(timezone.utc).isoformat(), meta=meta,
                    timeouts=pair.forward.timeouts + pair.backward.timeouts,
                )
                stream.write(json.dumps(asdict(judgment), ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                judgments.append(judgment)
        return judgments
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise JudgeError(f"{out_file}: elaborazione dei giudizi non riuscita: {error}") from error


# --- Coppie della campagna MVP (task 7, D52) ---


@dataclass(frozen=True)
class RunConfig:
    """Mappa versionata braccio -> compito -> campagna, con seme e riferimento."""

    seed: int
    tasks_file: Path
    guides_file: Path
    baseline: str
    challengers: tuple[str, ...]
    runs: dict[str, dict[str, str]]


@dataclass(frozen=True)
class PlannedPair:
    """Una coppia da giudicare: lato sinistro e destro deciso dal seme."""

    item: str
    pair_id: str
    task_id: str
    challenger: str
    baseline: str
    left_arm: str
    right_arm: str
    left: tuple[Path, ...]
    right: tuple[Path, ...]
    run_ids: dict[str, str]


def load_run_config(path: Path) -> RunConfig:
    """Legge la mappa; ogni braccio deve coprire esattamente gli stessi compiti."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise JudgeError(f"{path}: lettura della mappa non riuscita: {error}") from error
    seed, tasks, guides = data.get("seed"), data.get("tasks"), data.get("guides")
    baseline, challengers, runs = data.get("baseline"), data.get("challengers"), data.get("runs")
    if (type(seed) is not int or not isinstance(tasks, str) or not isinstance(guides, str)
            or not isinstance(baseline, str) or not isinstance(challengers, list) or not challengers
            or not all(isinstance(arm, str) for arm in challengers)
            or baseline in challengers or len(set(challengers)) != len(challengers)
            or not isinstance(runs, dict)):
        raise JudgeError(f"{path}: campi seed, tasks, guides, baseline, challengers o runs non validi")
    arms = [baseline, *challengers]
    if set(runs) != set(arms):
        raise JudgeError(f"{path}: runs deve avere esattamente i bracci {arms}")
    task_sets = set()
    for arm in arms:
        table = runs[arm]
        if (not isinstance(table, dict) or not table
                or not all(isinstance(campaign, str) and campaign for campaign in table.values())):
            raise JudgeError(f"{path}: run del braccio {arm} non valide")
        task_sets.add(frozenset(table))
    if len(task_sets) != 1:
        raise JudgeError(f"{path}: i bracci non coprono gli stessi compiti")
    return RunConfig(seed, path.parent / tasks, path.parent / guides, baseline, tuple(challengers),
                     {arm: dict(runs[arm]) for arm in arms})


def _run_site(campaigns_dir: Path, campaign: str, task_id: str) -> tuple[str, tuple[Path, ...]]:
    """La sola riga del compito nel manifesto e i suoi screenshot in ordine di larghezza."""
    manifest = campaigns_dir / f"{campaign}.jsonl"
    try:
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as error:
        raise JudgeError(f"{manifest}: lettura del manifesto non riuscita: {error}") from error
    found = [row for row in rows if isinstance(row, dict) and row.get("task_id") == task_id]
    if len(found) != 1:
        raise JudgeError(f"{manifest}: attesa una riga per il compito {task_id}, trovate {len(found)}")
    row = found[0]
    evaluation = row.get("evaluation")
    run_id = row.get("run_id")
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("path"), str) or not isinstance(run_id, str):
        raise JudgeError(f"{manifest}: valutazione o run_id mancante per il compito {task_id}")
    data = _read_json(Path(evaluation["path"]))
    shots = data.get("riservato", {}).get("screenshots") if isinstance(data, dict) else None
    if not isinstance(shots, dict):
        raise JudgeError(f"{evaluation['path']}: screenshot mancanti")
    images = []
    for width in WIDTH_ORDER:
        shot = shots.get(str(width))
        if not isinstance(shot, str) or not Path(shot).is_file():
            raise JudgeError(f"{evaluation['path']}: screenshot a {width} mancante")
        images.append(Path(shot))
    return run_id, tuple(images)


def plan_run_pairs(config: RunConfig, campaigns_dir: Path) -> list[PlannedPair]:
    """Una coppia per compito e braccio in prova; il seme sceglie chi sta a sinistra."""
    rng = random.Random(config.seed)
    pairs = []
    for task_id in sorted(config.runs[config.baseline]):
        base_run, base_images = _run_site(campaigns_dir, config.runs[config.baseline][task_id], task_id)
        for challenger in config.challengers:
            run_id, images = _run_site(campaigns_dir, config.runs[challenger][task_id], task_id)
            sides = [(config.baseline, base_run, base_images), (challenger, run_id, images)]
            if rng.random() < 0.5:
                sides.reverse()
            (left_arm, left_run, left), (right_arm, right_run, right) = sides
            pair_id = f"{challenger}-{config.baseline}"
            pairs.append(PlannedPair(f"{pair_id}/{task_id}", pair_id, task_id, challenger, config.baseline,
                                     left_arm, right_arm, left, right, {left_arm: left_run, right_arm: right_run}))
    return pairs


def freeze_plan(pairs: Sequence[PlannedPair], seed: int, path: Path) -> str:
    """Scrive il piano con l'impronta di ogni immagine; un piano diverso blocca la ripresa."""
    def images(paths: tuple[Path, ...]) -> list[dict[str, Any]]:
        try:
            return [{"width": width, "path": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
                    for width, image in zip(WIDTH_ORDER, paths)]
        except OSError as error:
            raise JudgeError(f"lettura di un'immagine non riuscita: {error}") from error

    rows = [{"item": pair.item, "pair_id": pair.pair_id, "task_id": pair.task_id, "challenger": pair.challenger,
             "baseline": pair.baseline, "left_arm": pair.left_arm, "right_arm": pair.right_arm,
             "run_ids": pair.run_ids, "left": images(pair.left), "right": images(pair.right)} for pair in pairs]
    text = json.dumps({"seed": seed, "widths": list(WIDTH_ORDER), "pairs": rows}, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise JudgeError(f"{path}: piano congelato diverso da quello attuale (seme, run o immagini)")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise JudgeError(f"{path}: piano non scritto: {error}") from error
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def judge_run_pairs(pairs: Sequence[PlannedPair], tasks: Mapping[str, str], guides_file: Path, out_file: Path, *,
                    runner: Runner, meta: dict[str, Any], items: Sequence[str] | None = None,
                    prompt_for: PromptFor | None = None) -> list[Judgment]:
    """Positivo se vince il braccio in prova; riprende solo con metadati identici.

    `prompt_for` e' per il giudizio a riquadri; senza, vale il protocollo calibrato.
    """
    guides = load_guides(guides_file)
    by_item = {pair.item: pair for pair in pairs}
    selected = set(items) if items is not None else None
    if selected is not None and selected - set(by_item):
        raise JudgeError("il filtro contiene coppie sconosciute al piano")
    existing = {row.item: row for row in load_judgments(out_file)} if out_file.exists() else {}
    for item, judgment in existing.items():
        if judgment.meta != meta:
            raise JudgeError(f"{out_file}: metadati diversi per il giudizio {item}")
        if item not in by_item or judgment.pair_id != by_item[item].pair_id:
            raise JudgeError(f"{out_file}: giudizio non appartenente al piano: {item}")
    prepared = []
    # Si controllano tutte le coppie prima di spendere una chiamata.
    for pair in pairs:
        if selected is not None and pair.item not in selected:
            continue
        task = tasks.get(pair.task_id)
        if not isinstance(task, str):
            raise JudgeError(f"{pair.item}: testo del compito mancante")
        guide = guides.get(hashlib.sha256(task.encode("utf-8")).hexdigest())
        if guide is None:
            raise JudgeError(f"{pair.item}: scheda mancante per il compito {pair.task_id}")
        prepared.append((pair, task, guide))
    try:
        json.dumps(meta, allow_nan=False)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        judgments = []
        with out_file.open("a", encoding="utf-8") as stream:
            for pair, task, guide in prepared:
                if pair.item in existing:
                    judgments.append(existing[pair.item])
                    continue
                result = judge_pair(task, guide, pair.left, pair.right, runner=runner, prompt_for=prompt_for)
                outputs = result.forward.outputs + result.backward.outputs
                usage: dict[str, int] = {}
                for output in outputs:
                    for name, count in output.usage.items():
                        usage[name] = usage.get(name, 0) + count
                # judge_pair e' positivo verso destra: si riporta dalla parte del braccio in prova.
                sign = 1 if pair.right_arm == pair.challenger else -1
                judgment = Judgment(
                    item=pair.item, pair_id=pair.pair_id,
                    value=result.value * sign if result.value is not None else None,
                    forward=result.forward.value, backward=result.backward.value,
                    attempts=result.forward.attempts + result.backward.attempts,
                    seconds=sum(output.seconds for output in outputs), usage=usage,
                    date=datetime.now(timezone.utc).isoformat(), meta=meta,
                    timeouts=result.forward.timeouts + result.backward.timeouts,
                )
                stream.write(json.dumps(asdict(judgment), ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                judgments.append(judgment)
        return judgments
    except (OSError, ValueError, TypeError) as error:
        raise JudgeError(f"{out_file}: elaborazione dei giudizi non riuscita: {error}") from error


def summarize_run_judgments(judgments: Sequence[Judgment]) -> dict[str, dict[str, Any]]:
    """Media per coppia sui soli giudizi valutabili, con il voto di ogni compito."""
    summary: dict[str, dict[str, Any]] = {}
    for judgment in sorted(judgments, key=lambda row: row.item):
        entry = summary.setdefault(judgment.pair_id, {"mean": None, "rated": 0, "unratable": 0, "by_task": {}})
        entry["by_task"][judgment.item.split("/", 1)[1]] = judgment.value
        if judgment.value is None:
            entry["unratable"] += 1
        else:
            entry["rated"] += 1
    for entry in summary.values():
        values = [value for value in entry["by_task"].values() if value is not None]
        entry["mean"] = sum(values) / len(values) if values else None
    return summary
