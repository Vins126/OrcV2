"""Giudizio a coppie sulle run della campagna MVP (task 7, D52).

Nota di design (tesi):
    Le coppie si costruiscono dai manifesti della campagna, non da un pacchetto di
    voto: una mappa versionata dice quale run vale per ogni braccio e compito, il
    seme decide quale sito compare per primo, e il piano si congela con l'impronta
    di ogni immagine prima della prima chiamata. Nessun test chiama Codex: il runner
    finto riconosce il braccio dal percorso dell'immagine, che il vero runner non
    mostra mai al giudice (copia le immagini con nomi neutri).
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import campaign
import judge
from task_model import CampaignError
from judge import (
    WIDTH_ORDER,
    JudgeError,
    JudgeQuotaError,
    RunOutput,
    freeze_plan,
    judge_run_pairs,
    load_guides,
    load_judgments,
    load_run_config,
    plan_run_pairs,
    summarize_run_judgments,
)

ROOT = Path(__file__).resolve().parent.parent
TASKS = {"t1": "Make a timer page.", "t2": "Make a todo list."}
RUNS = {
    "B": {"t1": "camp-B", "t2": "camp-B-r2"},
    "C": {"t1": "camp-C", "t2": "camp-C"},
    "D": {"t1": "camp-D", "t2": "camp-D"},
}
META = {"model": "finto", "plan_sha256": "x"}


def _write_guides(path: Path, tasks: dict[str, str] = TASKS) -> Path:
    data = {hashlib.sha256(text.encode("utf-8")).hexdigest():
            {"title": f"Scheda {task}", "objective": "Obiettivo.", "lookFor": ["Ordine"], "note": None}
            for task, text in tasks.items()}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_config(root: Path, *, runs: dict[str, dict[str, str]] = RUNS, seed: int = 7) -> Path:
    lines = [f"seed = {seed}", 'tasks = "compiti.toml"', 'guides = "schede.json"',
             'baseline = "B"', 'challengers = ["C", "D"]']
    for arm, tasks in runs.items():
        lines.append(f"[runs.{arm}]")
        lines.extend(f'"{task}" = "{campaign_id}"' for task, campaign_id in tasks.items())
    path = root / "giudizio.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_guides(root / "schede.json")
    return path


def _write_campaigns(campaigns_dir: Path, runs: dict[str, dict[str, str]] = RUNS) -> None:
    """Un manifesto per campagna, con una riga d'ambiente e una riga per compito."""
    rows: dict[str, list[dict[str, Any]]] = {}
    for arm, tasks in runs.items():
        for task, campaign_id in tasks.items():
            run_dir = campaigns_dir / campaign_id / f"{task}-1"
            shots = {}
            for width in WIDTH_ORDER:
                shot = run_dir / "screenshot" / f"shot-{width}.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                shot.write_bytes(f"{arm}-{task}-{width}".encode())
                shots[str(width)] = str(shot)
            evaluation = run_dir / "valutazione.json"
            evaluation.write_text(json.dumps({"riservato": {"screenshots": shots}}), encoding="utf-8")
            rows.setdefault(campaign_id, []).append(
                {"task_id": task, "rep": 1, "run_id": f"run-{arm}-{task}", "status": "completed",
                 "evaluation": {"path": str(evaluation), "started": True}})
    for campaign_id, campaign_rows in rows.items():
        lines = [json.dumps({"environment": {}})] + [json.dumps(row) for row in campaign_rows]
        (campaigns_dir / f"{campaign_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, Path]:
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    return _write_config(tmp_path), campaigns_dir


def _arm_of(image: Path) -> str:
    return image.read_bytes().decode().split("-")[0]


class PreferArm:
    """Preferisce sempre il sito del braccio dato, in qualunque posizione."""

    def __init__(self, arm: str, *, strength: int = 2) -> None:
        self.arm, self.strength = arm, strength
        self.calls: list[tuple[str, tuple[Path, ...]]] = []

    def __call__(self, prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        self.calls.append((prompt, tuple(images)))
        first_is_arm = _arm_of(images[0]) == self.arm
        vote = -self.strength if first_is_arm else self.strength
        return RunOutput(json.dumps({"voto": vote, "motivo": "ok"}), 1.0, {"input_tokens": 10}, None)


def _never(prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
    raise AssertionError("nessuna chiamata attesa")


def _plan(setup: tuple[Path, Path]) -> list[judge.PlannedPair]:
    config_file, campaigns_dir = setup
    return plan_run_pairs(load_run_config(config_file), campaigns_dir)


# --- configurazione e piano ---

def test_config_reads_paths_relative_to_file(setup: tuple[Path, Path]) -> None:
    config = load_run_config(setup[0])
    assert config.seed == 7 and config.baseline == "B" and config.challengers == ("C", "D")
    assert config.guides_file == setup[0].parent / "schede.json"
    assert config.tasks_file == setup[0].parent / "compiti.toml"
    assert config.runs["B"]["t2"] == "camp-B-r2"


@pytest.mark.parametrize("change", [
    lambda runs: runs["C"].pop("t2"),                 # task mancante per un braccio
    lambda runs: runs.pop("D"),                        # braccio in prova senza run
    lambda runs: runs["D"].update({"t3": "camp-D"}),   # task in piu' per un braccio
])
def test_config_rejects_uneven_task_sets(tmp_path: Path, change: Any) -> None:
    runs = json.loads(json.dumps(RUNS))
    change(runs)
    with pytest.raises(JudgeError):
        load_run_config(_write_config(tmp_path, runs=runs))


def test_plan_has_one_pair_per_task_and_challenger(setup: tuple[Path, Path]) -> None:
    pairs = _plan(setup)
    assert [pair.item for pair in pairs] == ["C-B/t1", "D-B/t1", "C-B/t2", "D-B/t2"]
    for pair in pairs:
        assert {pair.left_arm, pair.right_arm} == {pair.challenger, "B"}
        assert pair.pair_id == f"{pair.challenger}-B"
        assert [image.name for image in pair.left] == [f"shot-{w}.png" for w in WIDTH_ORDER]
        assert all(_arm_of(image) == pair.left_arm for image in pair.left)
        assert all(_arm_of(image) == pair.right_arm for image in pair.right)
        assert pair.run_ids == {pair.left_arm: f"run-{pair.left_arm}-{pair.task_id}",
                                pair.right_arm: f"run-{pair.right_arm}-{pair.task_id}"}


def test_plan_uses_the_mapped_campaign(setup: tuple[Path, Path]) -> None:
    pair = next(pair for pair in _plan(setup) if pair.item == "C-B/t2")
    baseline = pair.left if pair.left_arm == "B" else pair.right
    assert "camp-B-r2" in str(baseline[0])


def test_same_seed_same_plan_other_seed_differs(tmp_path: Path) -> None:
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    sides = {}
    for seed in (1, 2, 3, 4):
        config = load_run_config(_write_config(tmp_path, seed=seed))
        first = [pair.left_arm for pair in plan_run_pairs(config, campaigns_dir)]
        assert first == [pair.left_arm for pair in plan_run_pairs(config, campaigns_dir)]
        sides[seed] = tuple(first)
    assert len(set(sides.values())) > 1


@pytest.mark.parametrize("damage", ["manifest", "row", "duplicate", "screenshot", "evaluation"])
def test_plan_rejects_missing_or_ambiguous_runs(setup: tuple[Path, Path], damage: str) -> None:
    config_file, campaigns_dir = setup
    manifest = campaigns_dir / "camp-C.jsonl"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if damage == "manifest":
        manifest.unlink()
    elif damage == "row":
        manifest.write_text("\n".join(line for line in lines if '"t2"' not in line) + "\n", encoding="utf-8")
    elif damage == "duplicate":
        manifest.write_text("\n".join(lines + [lines[-1]]) + "\n", encoding="utf-8")
    elif damage == "screenshot":
        (campaigns_dir / "camp-C" / "t1-1" / "screenshot" / "shot-768.png").unlink()
    else:
        (campaigns_dir / "camp-C" / "t1-1" / "valutazione.json").write_text("{}", encoding="utf-8")
    with pytest.raises(JudgeError):
        plan_run_pairs(load_run_config(config_file), campaigns_dir)


# --- piano congelato ---

def test_freeze_is_stable_and_records_image_hashes(setup: tuple[Path, Path], tmp_path: Path) -> None:
    pairs = _plan(setup)
    path = tmp_path / "out" / "coppie.json"
    digest = freeze_plan(pairs, 7, path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert freeze_plan(_plan(setup), 7, path) == digest
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["seed"] == 7 and len(data["pairs"]) == 4
    row = data["pairs"][0]
    first = pairs[0].left[0]
    assert row["left"][0]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()


def test_freeze_rejects_changed_image_or_seed(setup: tuple[Path, Path], tmp_path: Path) -> None:
    path = tmp_path / "coppie.json"
    pairs = _plan(setup)
    freeze_plan(pairs, 7, path)
    with pytest.raises(JudgeError):
        freeze_plan(pairs, 8, path)
    pairs[0].left[0].write_bytes(b"cambiata")
    with pytest.raises(JudgeError):
        freeze_plan(_plan(setup), 7, path)


# --- giudizio ---

def test_sign_is_positive_when_challenger_wins_in_any_position(setup: tuple[Path, Path], tmp_path: Path) -> None:
    pairs = _plan(setup)
    sides = {pair.left_arm == pair.challenger for pair in pairs}
    assert sides == {True, False}, "il seme del fixture deve mettere il braccio in prova da entrambi i lati"
    guides = setup[0].parent / "schede.json"
    # C preferito ovunque: +2 sulle coppie C-B; sulle D-B il giudice vota sempre la seconda posizione,
    # quindi i due ordini si annullano (preferenza di posizione, non di sito).
    with_c = judge_run_pairs(pairs, TASKS, guides, tmp_path / "c.jsonl", runner=PreferArm("C"), meta=META)
    assert {row.item: row.value for row in with_c} == {"C-B/t1": 2.0, "C-B/t2": 2.0, "D-B/t1": 0.0, "D-B/t2": 0.0}
    with_b = judge_run_pairs(pairs, TASKS, guides, tmp_path / "b.jsonl", runner=PreferArm("B", strength=1),
                             meta=META)
    assert [row.value for row in with_b] == [-1.0] * 4
    with_challenger = judge_run_pairs(pairs, TASKS, guides, tmp_path / "s.jsonl", runner=PreferChallenger(),
                                      meta=META)
    assert [row.value for row in with_challenger] == [2.0] * 4


class PreferChallenger:
    """Preferisce sempre il sito che non e' di B."""

    def __call__(self, prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        vote = -2 if _arm_of(images[0]) != "B" else 2
        return RunOutput(json.dumps({"voto": vote, "motivo": "ok"}), 1.0, {"input_tokens": 10}, None)


def test_two_calls_per_pair_and_rows_written(setup: tuple[Path, Path], tmp_path: Path) -> None:
    runner = PreferArm("B")
    out = tmp_path / "giudizi.jsonl"
    judgments = judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json", out,
                                runner=runner, meta=META)
    assert len(runner.calls) == 8
    assert [row.item for row in load_judgments(out)] == sorted(row.item for row in judgments)
    assert all(row.meta == META and row.attempts == 2 for row in judgments)


def test_prompt_never_names_arm_run_or_path(setup: tuple[Path, Path], tmp_path: Path) -> None:
    runner = PreferArm("B")
    judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json", tmp_path / "g.jsonl",
                    runner=runner, meta=META)
    for prompt, _ in runner.calls:
        assert "Scheda t" in prompt
        for word in ("camp-", "run-", "braccio", "swarm", str(tmp_path)):
            assert word not in prompt


def test_resume_skips_done_pairs_and_rejects_other_meta(setup: tuple[Path, Path], tmp_path: Path) -> None:
    pairs = _plan(setup)
    guides = setup[0].parent / "schede.json"
    out = tmp_path / "giudizi.jsonl"
    first = judge_run_pairs(pairs, TASKS, guides, out, runner=PreferArm("B"), meta=META, items=["C-B/t1"])
    assert [row.item for row in first] == ["C-B/t1"]
    runner = PreferArm("B")
    done = judge_run_pairs(pairs, TASKS, guides, out, runner=runner, meta=META)
    assert len(done) == 4 and len(runner.calls) == 6
    assert judge_run_pairs(pairs, TASKS, guides, out, runner=_never, meta=META) == done
    with pytest.raises(JudgeError):
        judge_run_pairs(pairs, TASKS, guides, out, runner=_never, meta={**META, "model": "altro"})


def test_unknown_item_filter_rejected(setup: tuple[Path, Path], tmp_path: Path) -> None:
    with pytest.raises(JudgeError):
        judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json", tmp_path / "g.jsonl",
                        runner=_never, meta=META, items=["X-B/t1"])


def test_missing_guide_or_task_text_fails_before_any_call(setup: tuple[Path, Path], tmp_path: Path) -> None:
    pairs = _plan(setup)
    partial = _write_guides(tmp_path / "parziali.json", {"t1": TASKS["t1"]})
    with pytest.raises(JudgeError):
        judge_run_pairs(pairs, TASKS, partial, tmp_path / "g.jsonl", runner=_never, meta=META)
    with pytest.raises(JudgeError):
        judge_run_pairs(pairs, {"t1": TASKS["t1"]}, setup[0].parent / "schede.json", tmp_path / "g.jsonl",
                        runner=_never, meta=META)
    assert not (tmp_path / "g.jsonl").exists() or (tmp_path / "g.jsonl").read_text() == ""


def test_unratable_stays_none_and_is_counted(setup: tuple[Path, Path], tmp_path: Path) -> None:
    def broken(prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        return RunOutput("non json", 1.0, {}, None)

    judgments = judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json",
                                tmp_path / "g.jsonl", runner=broken, meta=META)
    assert all(row.value is None for row in judgments)
    summary = summarize_run_judgments(judgments)
    assert summary["C-B"] == {"mean": None, "rated": 0, "unratable": 2, "by_task": {"t1": None, "t2": None}}


def test_summary_means_by_pair_and_task(setup: tuple[Path, Path], tmp_path: Path) -> None:
    judgments = judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json",
                                tmp_path / "g.jsonl", runner=PreferChallenger(), meta=META)
    summary = summarize_run_judgments(judgments)
    assert summary["D-B"] == {"mean": 2.0, "rated": 2, "unratable": 0, "by_task": {"t1": 2.0, "t2": 2.0}}


def test_quota_stops_and_keeps_written_rows(setup: tuple[Path, Path], tmp_path: Path) -> None:
    calls = []

    def quota(prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        calls.append(1)
        if len(calls) > 2:
            raise JudgeQuotaError("limite")
        return RunOutput(json.dumps({"voto": 0, "motivo": "pari"}), 1.0, {}, None)

    out = tmp_path / "g.jsonl"
    with pytest.raises(JudgeQuotaError):
        judge_run_pairs(_plan(setup), TASKS, setup[0].parent / "schede.json", out, runner=quota, meta=META)
    assert len(load_judgments(out)) == 1


# --- file reali del progetto e comando ---

def test_project_guides_cover_campaign_tasks() -> None:
    config = load_run_config(ROOT / "campaigns" / "mvp_giudizio.toml")
    assert set(config.runs) == {"B", "C", "D"}
    guides = load_guides(config.guides_file)
    assert len(guides) == 5
    try:
        texts = campaign._task_texts(config.tasks_file)
    except CampaignError as error:  # dati dei compiti assenti (CI senza download)
        pytest.skip(f"compiti non scaricati: {error}")
    assert set(texts) == set(config.runs["B"])
    assert {hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts.values()} == set(guides)


def test_cd_map_uses_same_runs_as_main_map() -> None:
    # MM-1: le coppie C-D devono confrontare gli stessi siti gia' giudicati contro B.
    main = load_run_config(ROOT / "campaigns" / "mvp_giudizio.toml")
    cd = load_run_config(ROOT / "campaigns" / "mvp_giudizio_cd.toml")
    assert (cd.baseline, cd.challengers) == ("D", ("C",))
    assert cd.runs == {"C": main.runs["C"], "D": main.runs["D"]}
    assert (cd.tasks_file, cd.guides_file) == (main.tasks_file, main.guides_file)
    assert cd.seed != main.seed


def test_command_freezes_plan_and_judges(setup: tuple[Path, Path], tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    config_file, campaigns_dir = setup
    monkeypatch.setattr(campaign, "_task_texts", lambda path: TASKS)
    monkeypatch.setattr(campaign, "_codex_version", lambda: "codex-cli 0.0.0")
    monkeypatch.setattr(judge, "codex_runner", lambda: PreferChallenger())
    out = tmp_path / "giudizio"
    code = campaign.main(["judge-runs", "--config", str(config_file), "--campaigns-dir", str(campaigns_dir),
                          "--out", str(out)])
    assert code == 0
    assert "+2 molto meglio di B, -2 B molto meglio" in capsys.readouterr().out
    rows = load_judgments(out / "giudizi.jsonl")
    assert len(rows) == 4 and all(row.value == 2.0 for row in rows)
    meta = rows[0].meta
    assert meta["plan_sha256"] == hashlib.sha256((out / "coppie.json").read_bytes()).hexdigest()
    assert meta["codex_version"] == "codex-cli 0.0.0"
    assert meta["guides_sha256"] == hashlib.sha256((config_file.parent / "schede.json").read_bytes()).hexdigest()


def test_command_reports_config_errors(tmp_path: Path) -> None:
    assert campaign.main(["judge-runs", "--config", str(tmp_path / "manca.toml")]) == 2
