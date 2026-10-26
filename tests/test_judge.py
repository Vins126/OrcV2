"""Il giudice a coppie vota in entrambi gli ordini e non vede mai il progetto (R1.9).

Nota di design (tesi):
    Nessun test chiama Codex: il giudice riceve un `runner` finto, una funzione
    che prende prompt, immagini e schema e restituisce un `RunOutput`, come fa
    il vero `codex_runner`. Il vero `codex_runner` si prova a sua volta con un
    finto `run` al posto di `subprocess.run`, cosi' si controlla il comando
    esatto (cartella vuota, sola lettura, configurazione utente ignorata) senza
    lanciarlo. I file del pacchetto si costruiscono qui, con lo stesso formato
    di `calibration.build_vote_package`.
"""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from judge import (
    CHECKLIST_SCHEMA,
    FIXED_QUESTIONS,
    JUDGE_EFFORT,
    JUDGE_MODEL,
    VOTE_SCHEMA,
    WIDTH_ORDER,
    Guide,
    JudgeError,
    JudgeQuotaError,
    RunOutput,
    checklist_prompt,
    codex_runner,
    judge_checklist,
    judge_order,
    judge_package,
    judge_pair,
    load_guides,
    load_judgments,
    parse_checklist,
    parse_vote,
    vote_prompt,
)
from task_model import CampaignError

ROOT = Path(__file__).resolve().parent.parent
GUIDE = Guide(title="Un timer", objective="Una pagina per usare un timer.",
              look_for=("Tempo ben leggibile", "Comandi distinti"), note="Non presumere funzioni aggiuntive.")
TASK = "Create a {timer} page with <b>start</b>."


def _out(payload: Any, *, error: str | None = None) -> RunOutput:
    text = None if payload is None else (payload if isinstance(payload, str) else json.dumps(payload))
    return RunOutput(text=text, seconds=1.5, usage={"input_tokens": 100, "output_tokens": 10}, error=error)


class FakeRunner:
    """Restituisce le uscite in ordine e registra prompt, immagini e schema."""

    def __init__(self, outputs: Sequence[RunOutput] | None = None, decide=None):
        self.outputs = list(outputs or [])
        self.decide = decide
        self.calls: list[tuple[str, list[Path], dict[str, Any]]] = []

    def __call__(self, prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        self.calls.append((prompt, list(images), schema))
        if self.decide is not None:
            return self.decide(prompt, list(images), schema)
        return self.outputs.pop(0)


def _side(tmp_path: Path, name: str) -> list[Path]:
    paths = []
    for width in WIDTH_ORDER:
        path = tmp_path / f"{name}-{width}.png"
        path.write_bytes(f"{name}{width}".encode())
        paths.append(path)
    return paths


# --- prompt e schemi ---------------------------------------------------------

def test_vote_prompt_shows_what_voters_see():
    prompt = vote_prompt(TASK, GUIDE)
    assert GUIDE.note is not None
    for text in (GUIDE.title, GUIDE.objective, *GUIDE.look_for, GUIDE.note, TASK):
        assert text in prompt
    for label in ("A molto meglio", "A meglio", "pari", "B meglio", "B molto meglio"):
        assert label in prompt
    assert "<<" not in prompt and ">>" not in prompt


def test_vote_prompt_comes_from_the_template_file():
    template = (ROOT / "campaigns" / "r1_giudice" / "voto.txt").read_text(encoding="utf-8")
    head = template.split("<<")[0]
    assert vote_prompt(TASK, GUIDE).startswith(head)


def test_prompt_without_note_has_no_note_line():
    guide = Guide(title="T", objective="O", look_for=("x",), note=None)
    assert "Nota" not in vote_prompt(TASK, guide)
    assert "None" not in vote_prompt(TASK, guide)


def test_checklist_prompt_lists_the_fixed_questions_in_order():
    prompt = checklist_prompt(TASK, GUIDE)
    positions = [prompt.index(question) for question in FIXED_QUESTIONS]
    assert positions == sorted(positions)
    assert GUIDE.objective in prompt and TASK in prompt
    assert "<<" not in prompt


def test_fixed_questions_are_those_of_the_protocol():
    assert len(FIXED_QUESTIONS) == 6
    protocol = " ".join((ROOT / "docs" / "PROTOCOLLO.md").read_text(encoding="utf-8").split()).lower()
    for question in FIXED_QUESTIONS:
        assert question.lower() in protocol


def test_schemas_require_the_fields():
    assert VOTE_SCHEMA["required"] == ["voto", "motivo"] or set(VOTE_SCHEMA["required"]) == {"voto", "motivo"}
    assert VOTE_SCHEMA["additionalProperties"] is False
    assert CHECKLIST_SCHEMA["additionalProperties"] is False
    assert "risposte" in CHECKLIST_SCHEMA["required"]


def test_model_and_effort_are_fixed():
    assert JUDGE_MODEL == "gpt-6.1-sol"
    assert JUDGE_EFFORT == "high"
    assert WIDTH_ORDER == (1440, 768, 375)


# --- lettura delle risposte --------------------------------------------------

@pytest.mark.parametrize("value", [-2, -1, 0, 1, 2])
def test_parse_vote_accepts_the_scale(value):
    assert parse_vote(json.dumps({"voto": value, "motivo": "x"})) == value


@pytest.mark.parametrize("text", [
    None, "", "non json", "[1]", json.dumps({"voto": 3, "motivo": "x"}), json.dumps({"voto": -3, "motivo": "x"}),
    json.dumps({"voto": 1.0, "motivo": "x"}), json.dumps({"voto": True, "motivo": "x"}),
    json.dumps({"voto": "1", "motivo": "x"}), json.dumps({"motivo": "x"}), json.dumps({"voto": 1}),
])
def test_parse_vote_rejects_anything_else(text):
    assert parse_vote(text) is None


def test_parse_checklist():
    good = json.dumps({"risposte": [True, False, True, True, False, True]})
    assert parse_checklist(good) == (True, False, True, True, False, True)
    for bad in (None, "x", json.dumps({"risposte": [True] * 5}), json.dumps({"risposte": [1, 0, 1, 1, 0, 1]}),
                json.dumps({"risposte": [True] * 7}), json.dumps({"altro": []})):
        assert parse_checklist(bad) is None


# --- un ordine, due ordini ---------------------------------------------------

def test_judge_order_passes_first_then_second_images(tmp_path):
    first, second = _side(tmp_path, "x"), _side(tmp_path, "y")
    runner = FakeRunner([_out({"voto": 1, "motivo": "m"})])
    result = judge_order(TASK, GUIDE, first, second, runner=runner)
    assert result.value == 1 and result.attempts == 1
    prompt, images, schema = runner.calls[0]
    assert images == first + second
    assert schema == VOTE_SCHEMA
    assert prompt == vote_prompt(TASK, GUIDE)


def test_malformed_answer_gets_one_new_attempt(tmp_path):
    runner = FakeRunner([_out("rotto"), _out({"voto": -2, "motivo": "m"})])
    result = judge_order(TASK, GUIDE, _side(tmp_path, "x"), _side(tmp_path, "y"), runner=runner)
    assert result.value == -2 and result.attempts == 2 and len(result.outputs) == 2


def test_two_failures_mean_not_ratable_never_a_tie(tmp_path):
    runner = FakeRunner([_out(None, error="timeout"), _out({"voto": 9, "motivo": "m"})])
    result = judge_order(TASK, GUIDE, _side(tmp_path, "x"), _side(tmp_path, "y"), runner=runner)
    assert result.value is None and result.attempts == 2
    assert len(runner.calls) == 2


def test_wrong_number_of_images_is_an_error(tmp_path):
    with pytest.raises(JudgeError):
        judge_order(TASK, GUIDE, _side(tmp_path, "x")[:2], _side(tmp_path, "y"), runner=FakeRunner())


def test_judge_error_is_a_campaign_error():
    assert issubclass(JudgeError, CampaignError) and issubclass(JudgeQuotaError, JudgeError)


def _prefers(name: str):
    """Giudice coerente: preferisce sempre il sito `name`, ovunque stia."""

    def decide(prompt, images, schema):
        first_is_name = images[0].name.startswith(name)
        return _out({"voto": -2 if first_is_name else 2, "motivo": "m"})
    return decide


def test_pair_runs_both_orders(tmp_path):
    left, right = _side(tmp_path, "s"), _side(tmp_path, "d")
    runner = FakeRunner(decide=_prefers("d"))
    result = judge_pair(TASK, GUIDE, left, right, runner=runner)
    assert [call[1] for call in runner.calls] == [left + right, right + left]
    assert result.forward.value == 2 and result.backward.value == -2
    assert result.value == 2


def test_inverting_the_sides_flips_the_sign(tmp_path):
    left, right = _side(tmp_path, "s"), _side(tmp_path, "d")
    direct = judge_pair(TASK, GUIDE, left, right, runner=FakeRunner(decide=_prefers("s")))
    swapped = judge_pair(TASK, GUIDE, right, left, runner=FakeRunner(decide=_prefers("s")))
    assert direct.value == -2 and swapped.value == 2


def test_position_bias_cancels_into_a_tie(tmp_path):
    runner = FakeRunner(decide=lambda p, i, s: _out({"voto": -1, "motivo": "vince sempre A"}))
    result = judge_pair(TASK, GUIDE, _side(tmp_path, "s"), _side(tmp_path, "d"), runner=runner)
    assert result.value == 0


def test_half_points_are_kept(tmp_path):
    runner = FakeRunner([_out({"voto": 1, "motivo": "m"}), _out({"voto": 0, "motivo": "m"})])
    result = judge_pair(TASK, GUIDE, _side(tmp_path, "s"), _side(tmp_path, "d"), runner=runner)
    assert result.value == 0.5


def test_one_unratable_order_makes_the_pair_unratable(tmp_path):
    runner = FakeRunner([_out({"voto": 2, "motivo": "m"}), _out("x"), _out("y")])
    result = judge_pair(TASK, GUIDE, _side(tmp_path, "s"), _side(tmp_path, "d"), runner=runner)
    assert result.value is None and result.forward.value == 2 and result.backward.value is None


def test_checklist_sees_one_site(tmp_path):
    images = _side(tmp_path, "s")
    runner = FakeRunner([_out({"risposte": [True] * 3}), _out({"risposte": [True, False] * 3})])
    result = judge_checklist(TASK, GUIDE, images, runner=runner)
    assert result.answers == (True, False, True, False, True, False) and result.attempts == 2
    assert runner.calls[0][1] == images and runner.calls[0][2] == CHECKLIST_SCHEMA


def test_quota_error_is_not_swallowed(tmp_path):
    def decide(prompt, images, schema):
        raise JudgeQuotaError("limite raggiunto")
    with pytest.raises(JudgeQuotaError):
        judge_pair(TASK, GUIDE, _side(tmp_path, "s"), _side(tmp_path, "d"), runner=FakeRunner(decide=decide))


# --- il vero runner, con un finto subprocess.run -----------------------------

def _jsonl(text: str, usage: dict[str, int] | None = None) -> str:
    events = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
              {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": "pensiero"}},
              {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": text}},
              {"type": "turn.completed", "usage": usage or {"input_tokens": 25000, "output_tokens": 90}}]
    return "\n".join(json.dumps(e) for e in events) + "\n"


class FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "", raises: Exception | None = None):
        self.stdout, self.returncode, self.stderr, self.raises = stdout, returncode, stderr, raises
        self.seen: dict[str, Any] = {}

    def __call__(self, cmd, **kwargs):
        workdir = Path(cmd[cmd.index("-C") + 1])
        schema = Path(cmd[cmd.index("--output-schema") + 1])
        self.seen = {"cmd": list(cmd), "kwargs": kwargs, "workdir": workdir,
                     "files": sorted(p.name for p in workdir.iterdir()), "schema": json.loads(schema.read_text()),
                     "images": [Path(cmd[i + 1]) for i, a in enumerate(cmd) if a == "-i"]}
        self.seen["image_bytes"] = [p.read_bytes() for p in self.seen["images"]]
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


def test_codex_command_is_isolated_and_fixed(tmp_path):
    left, right = _side(tmp_path, "secret_model_name"), _side(tmp_path, "other")
    run = FakeRun(_jsonl(json.dumps({"voto": 1, "motivo": "m"})))
    out = codex_runner(run=run)("PROMPT", left + right, VOTE_SCHEMA)
    cmd = run.seen["cmd"]
    assert cmd[0] == "codex" and cmd[1] == "exec"
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json"):
        assert flag in cmd
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert cmd[cmd.index("-m") + 1] == JUDGE_MODEL
    assert f"model_reasoning_effort={JUDGE_EFFORT}" in cmd
    assert cmd[-2:] == ["--", "-"]
    assert run.seen["kwargs"].get("input") == "PROMPT"
    assert run.seen["kwargs"].get("timeout") is not None
    # cartella di lavoro: fuori dal progetto, solo le immagini, con nomi neutri
    workdir = run.seen["workdir"]
    assert ROOT not in workdir.parents and workdir != ROOT
    assert len(run.seen["files"]) == 6 and not any("secret" in f or "other" in f for f in run.seen["files"])
    assert all(img.parent == workdir for img in run.seen["images"])
    assert run.seen["image_bytes"] == [p.read_bytes() for p in left + right]
    assert run.seen["schema"] == VOTE_SCHEMA
    schema_path = Path(cmd[cmd.index("--output-schema") + 1])
    assert schema_path.parent != workdir
    assert out.text == json.dumps({"voto": 1, "motivo": "m"}) and out.error is None
    assert out.usage == {"input_tokens": 25000, "output_tokens": 90} and out.seconds >= 0
    assert not workdir.exists()


def test_codex_failure_and_timeout_become_errors(tmp_path):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    failed = codex_runner(run=FakeRun("", returncode=1, stderr="boom"))("P", images, VOTE_SCHEMA)
    assert failed.text is None and failed.error
    timed = codex_runner(run=FakeRun(raises=subprocess.TimeoutExpired(["codex"], 300)))("P", images, VOTE_SCHEMA)
    assert timed.text is None and "timeout" in (timed.error or "")
    empty = codex_runner(run=FakeRun("{\"type\":\"turn.started\"}\n"))("P", images, VOTE_SCHEMA)
    assert empty.text is None and empty.error


@pytest.mark.parametrize("stderr", ["You've hit your usage limit. Try again later.", "error: rate_limit_reached"])
def test_codex_quota_stops_everything(tmp_path, stderr):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    with pytest.raises(JudgeQuotaError):
        codex_runner(run=FakeRun("", returncode=1, stderr=stderr))("P", images, VOTE_SCHEMA)


# --- il pacchetto intero -----------------------------------------------------

def _package(tmp_path: Path) -> tuple[Path, Path, Path]:
    pkg = tmp_path / "pacchetto"
    (pkg / "img").mkdir(parents=True)
    tasks = {"v001": "task uno", "v002": "task due", "v003": "task uno"}
    items = []
    for item, task in tasks.items():
        images: dict[str, dict[str, str]] = {"s": {}, "d": {}}
        for side in ("s", "d"):
            for width in WIDTH_ORDER:
                rel = f"img/{item}-{side}-{width}.png"
                (pkg / rel).write_bytes(f"{item}{side}{width}".encode())
                images[side][str(width)] = rel
        items.append({"item": item, "task": task, "images": images})
    (pkg / "coppie.js").write_text("window.COPPIE = " + json.dumps(items) + ";\nwindow.PAUSA = 20;\n")
    digest = hashlib.sha256((pkg / "coppie.js").read_bytes()).hexdigest()
    key = {"package_id": digest, "seed": 1, "items": [
        # v001: a destra il modello "maggiore" -> il segno resta
        {"item": "v001", "pair_id": "c001", "left_model": "alfa", "right_model": "beta", "repeat_of": None},
        # v002: a destra il modello "minore" -> il segno si inverte
        {"item": "v002", "pair_id": "c002", "left_model": "gamma", "right_model": "delta", "repeat_of": None},
        # v003: ripetizione di v001, il giudice non la rivota
        {"item": "v003", "pair_id": "c001", "left_model": "beta", "right_model": "alfa", "repeat_of": "v001"},
    ]}
    key_file = tmp_path / "chiave.json"
    key_file.write_text(json.dumps(key))
    guides = {hashlib.sha256(t.encode()).hexdigest(): {"title": "T", "objective": "O", "lookFor": ["x"],
                                                        "ambiguous": False, "note": None}
              for t in set(tasks.values())}
    guides_file = tmp_path / "task-guides.json"
    guides_file.write_text(json.dumps(guides))
    return pkg, key_file, guides_file


def _right_wins(prompt, images, schema):
    return _out({"voto": -2 if b"d" in images[0].read_bytes()[4:5] else 2, "motivo": "m"})


def test_load_guides(tmp_path):
    _, _, guides_file = _package(tmp_path)
    guides = load_guides(guides_file)
    assert guides[hashlib.sha256(b"task uno").hexdigest()] == Guide(title="T", objective="O", look_for=("x",),
                                                                    note=None)


def test_package_values_follow_the_pair_order_like_votes(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    runner = FakeRunner(decide=_right_wins)
    judgments = judge_package(pkg, key_file, guides_file, out, runner=runner, meta={"model": JUDGE_MODEL})
    by_pair = {j.pair_id: j.value for j in judgments}
    # come load_votes: positivo se e' preferito il modello maggiore della coppia
    assert by_pair == {"c001": 2, "c002": -2}
    assert len(runner.calls) == 4  # due coppie, due ordini, nessuna ripetizione
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["item"] for r in rows] == ["v001", "v002"]
    assert all(r["meta"]["model"] == JUDGE_MODEL for r in rows)
    for row in rows:
        for field in ("pair_id", "value", "forward", "backward", "attempts", "seconds", "usage", "date"):
            assert field in row
    assert load_judgments(out) == judgments


def test_package_never_shows_model_names(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    runner = FakeRunner(decide=_right_wins)
    judge_package(pkg, key_file, guides_file, tmp_path / "g.jsonl", runner=runner, meta={})
    for prompt, images, _ in runner.calls:
        for name in ("alfa", "beta", "gamma", "delta"):
            assert name not in prompt and all(name not in str(p) for p in images)


def test_package_resumes_without_new_calls(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    first = judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=_right_wins), meta={})

    def boom(prompt, images, schema):
        raise AssertionError("nessuna chiamata attesa")
    again = judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=boom), meta={})
    assert again == first
    assert len(out.read_text().splitlines()) == 2


def test_package_items_filter(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    runner = FakeRunner(decide=_right_wins)
    judgments = judge_package(pkg, key_file, guides_file, tmp_path / "g.jsonl", runner=runner, meta={},
                              items=["v002"])
    assert [j.pair_id for j in judgments] == ["c002"] and len(runner.calls) == 2


def test_quota_stops_the_batch_and_keeps_what_was_done(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    calls = {"n": 0}

    def decide(prompt, images, schema):
        calls["n"] += 1
        if calls["n"] > 2:
            raise JudgeQuotaError("limite")
        return _right_wins(prompt, images, schema)
    with pytest.raises(JudgeQuotaError):
        judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=decide), meta={})
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["item"] for r in rows] == ["v001"]


def test_unratable_pair_is_written_as_null(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    judgments = judge_package(pkg, key_file, guides_file, out,
                              runner=FakeRunner(decide=lambda p, i, s: _out("rotto")), meta={})
    assert [j.value for j in judgments] == [None, None]
    assert [json.loads(line)["value"] for line in out.read_text().splitlines()] == [None, None]


def test_package_checks_the_key(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    key = json.loads(key_file.read_text())
    key["package_id"] = "0" * 64
    key_file.write_text(json.dumps(key))
    with pytest.raises(JudgeError):
        judge_package(pkg, key_file, guides_file, tmp_path / "g.jsonl", runner=FakeRunner(), meta={})


def test_missing_guide_is_an_error(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    guides_file.write_text("{}")
    with pytest.raises(JudgeError):
        judge_package(pkg, key_file, guides_file, tmp_path / "g.jsonl", runner=FakeRunner(), meta={})


# --- correzioni dopo la revisione del 25 ott (R1.9-D5) ------------------------

def test_timeouts_are_retried_without_spending_an_attempt(tmp_path):
    from judge import TIMEOUT_RETRIES
    assert TIMEOUT_RETRIES == 3
    late = RunOutput(text=None, seconds=120.0, usage={}, error="timeout", timed_out=True)
    runner = FakeRunner([late, late, late, _out({"voto": 1, "motivo": "m"})])
    result = judge_order(TASK, GUIDE, _side(tmp_path, "x"), _side(tmp_path, "y"), runner=runner)
    assert result.value == 1 and result.attempts == 1 and result.timeouts == 3
    assert len(result.outputs) == 4


def test_too_many_timeouts_spend_the_attempt(tmp_path):
    late = RunOutput(text=None, seconds=120.0, usage={}, error="timeout", timed_out=True)
    # primo tentativo: 1 + 3 tempi scaduti; secondo tentativo: risposta valida
    runner = FakeRunner([late] * 4 + [_out({"voto": -1, "motivo": "m"})])
    result = judge_order(TASK, GUIDE, _side(tmp_path, "x"), _side(tmp_path, "y"), runner=runner)
    assert result.value == -1 and result.attempts == 2 and result.timeouts == 4
    runner = FakeRunner([late] * 8)
    result = judge_order(TASK, GUIDE, _side(tmp_path, "x"), _side(tmp_path, "y"), runner=runner)
    assert result.value is None and result.attempts == 2 and len(runner.calls) == 8


def test_run_output_is_not_a_timeout_by_default():
    assert _out({"voto": 0, "motivo": "m"}).timed_out is False


def test_timeout_from_codex_is_flagged(tmp_path):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    out = codex_runner(run=FakeRun(raises=subprocess.TimeoutExpired(["codex"], 120)))("P", images, VOTE_SCHEMA)
    assert out.timed_out is True
    failed = codex_runner(run=FakeRun("", returncode=1, stderr="boom"))("P", images, VOTE_SCHEMA)
    assert failed.timed_out is False


def test_timeouts_are_saved_with_the_judgment(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    late = RunOutput(text=None, seconds=120.0, usage={}, error="timeout", timed_out=True)
    first = {"done": False}

    def decide(prompt, images, schema):
        if not first["done"]:
            first["done"] = True
            return late
        return _right_wins(prompt, images, schema)
    judgments = judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=decide), meta={})
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows[0]["timeouts"] == 1 and rows[1]["timeouts"] == 0
    assert judgments[0].value == 2
    assert load_judgments(out) == judgments


def test_codex_gets_a_reduced_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "segreto")
    monkeypatch.setenv("ORC_QUALCOSA", "x")
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    run = FakeRun(_jsonl(json.dumps({"voto": 1, "motivo": "m"})))
    codex_runner(run=run)("P", images, VOTE_SCHEMA)
    env = run.seen["kwargs"].get("env")
    assert isinstance(env, dict) and "PATH" in env and "HOME" in env
    assert set(env) <= {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME"}
    assert "segreto" not in json.dumps(env)


def _jsonl_with(extra: list[dict[str, Any]], text: str) -> str:
    events = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}, *extra,
              {"type": "item.completed", "item": {"id": "i9", "type": "agent_message", "text": text}},
              {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}]
    return "\n".join(json.dumps(e) for e in events) + "\n"


@pytest.mark.parametrize("kind", ["command_execution", "file_change", "mcp_tool_call", "web_search"])
def test_a_judge_that_uses_tools_is_rejected(tmp_path, kind):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    stdout = _jsonl_with([{"type": "item.completed", "item": {"id": "i1", "type": kind}}],
                         json.dumps({"voto": 2, "motivo": "m"}))
    out = codex_runner(run=FakeRun(stdout))("P", images, VOTE_SCHEMA)
    assert out.text is None and out.error and out.timed_out is False


def test_reasoning_and_message_are_not_tools(tmp_path):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    stdout = _jsonl_with([{"type": "item.completed", "item": {"id": "i1", "type": "reasoning", "text": "x"}}],
                         json.dumps({"voto": 2, "motivo": "m"}))
    assert codex_runner(run=FakeRun(stdout))("P", images, VOTE_SCHEMA).text == json.dumps({"voto": 2, "motivo": "m"})


def test_usage_limit_in_the_answer_does_not_stop_the_batch(tmp_path):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    answer = json.dumps({"voto": 1, "motivo": "B spiega meglio i usage limits del piano"})
    stdout = _jsonl_with([{"type": "item.completed",
                           "item": {"id": "i1", "type": "reasoning", "text": "pagina sui rate_limit_reached e usage limit"}}],
                         answer)
    out = codex_runner(run=FakeRun(stdout))("P", images, VOTE_SCHEMA)
    assert out.text == answer and out.error is None


@pytest.mark.parametrize("event", [
    {"type": "error", "message": "You've hit your usage limit. Upgrade or try again later."},
    {"type": "turn.failed", "error": {"message": "usage limit reached"}},
])
def test_usage_limit_in_an_error_event_stops_the_batch(tmp_path, event):
    images = _side(tmp_path, "s") + _side(tmp_path, "d")
    stdout = "\n".join(json.dumps(e) for e in [{"type": "thread.started", "thread_id": "t"}, event]) + "\n"
    with pytest.raises(JudgeQuotaError):
        codex_runner(run=FakeRun(stdout, returncode=1))("P", images, VOTE_SCHEMA)


def test_resume_refuses_different_meta(tmp_path):
    pkg, key_file, guides_file = _package(tmp_path)
    out = tmp_path / "giudizi.jsonl"
    judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=_right_wins),
                  meta={"vote_sha256": "a"}, items=["v001"])

    def boom(prompt, images, schema):
        raise AssertionError("nessuna chiamata attesa")
    with pytest.raises(JudgeError):
        judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=boom), meta={"vote_sha256": "b"})
    assert len(out.read_text().splitlines()) == 1
    # stessi metadati: la ripresa continua
    judge_package(pkg, key_file, guides_file, out, runner=FakeRunner(decide=_right_wins), meta={"vote_sha256": "a"})
    assert len(out.read_text().splitlines()) == 2
