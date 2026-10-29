"""Prova del giudice sui voti pubblici di Vibe Design Arena (R1.12).

Nota di design (tesi):
    Il giudice di R1.9 resta invariato: `vibe.py` ne riusa tentativi, schema e
    lettura del voto, e cambia solo prompt e numero di immagini (uno screenshot
    per sito). Nessun test chiama Codex: il `runner` e' una funzione finta che
    restituisce un voto scelto dal test, come in `test_judge.py`.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from judge import JUDGE_EFFORT, JUDGE_MODEL, VOTE_SCHEMA, JudgeError, Judgment, RunOutput, load_judgments
from vibe import (
    VIBE_PAIRS,
    VIBE_SEED,
    VibePair,
    accept_vibe,
    check_screenshots,
    freeze_selection,
    judge_vibe,
    load_pairs,
    sample_pairs,
    vibe_report,
    vote_prompt,
)

META = {"model": JUDGE_MODEL, "effort": JUDGE_EFFORT}


def _pairs_file(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "coppie.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _row(a: str, b: str, va: int, vb: int) -> dict[str, Any]:
    return {"app_a": a, "app_b": b, "votes_a": va, "votes_b": vb, "winner": "app_a" if va > vb else "app_b"}


def _many(count: int) -> list[VibePair]:
    return [VibePair(f"a{i:04d}", f"b{i:04d}", 20, 10) for i in range(count)]


def _screens(tmp_path: Path, apps: Sequence[str]) -> Path:
    folder = tmp_path / "screenshot"
    folder.mkdir()
    for app in apps:
        (folder / f"{app}.png").write_bytes(b"png " + app.encode())
    return folder


def _runner(votes: dict[tuple[str, str], int | None], calls: list[tuple[str, ...]]):
    """Vota in base ai nomi delle immagini: (prima, seconda) -> voto."""
    def run(prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        assert schema == VOTE_SCHEMA
        key = (images[0].stem, images[1].stem)
        calls.append(key)
        value = votes[key]
        text = None if value is None else json.dumps({"voto": value, "motivo": "prova"})
        return RunOutput(text=text, seconds=1.0, usage={"input_tokens": 10}, error=None)
    return run


def _judgment(item: str, value: float | None) -> Judgment:
    return Judgment(item=item, pair_id=item, value=value, forward=None, backward=None, attempts=2,
                    seconds=1.0, usage={}, date="2026-10-29T00:00:00+00:00", meta=META)


# --- dati e estrazione ---

def test_v1_load_pairs_reads_totals(tmp_path: Path) -> None:
    pairs = load_pairs(_pairs_file(tmp_path, [_row("x", "y", 22, 8)]))
    assert pairs == [VibePair("x", "y", 22, 8)]
    assert pairs[0].item == "x|y"


@pytest.mark.parametrize("row", [
    {"app_a": "x", "app_b": "x", "votes_a": 1, "votes_b": 2},
    {"app_a": "x", "app_b": "y", "votes_a": -1, "votes_b": 2},
    {"app_a": "x", "app_b": "y", "votes_a": 1.5, "votes_b": 2},
    {"app_a": "x", "app_b": "y", "votes_a": 0, "votes_b": 0},
    {"app_a": "x", "votes_a": 1, "votes_b": 2},
])
def test_v2_load_pairs_rejects_bad_rows(tmp_path: Path, row: dict[str, Any]) -> None:
    with pytest.raises(JudgeError):
        load_pairs(_pairs_file(tmp_path, [row]))


def test_v3_load_pairs_rejects_duplicates(tmp_path: Path) -> None:
    with pytest.raises(JudgeError):
        load_pairs(_pairs_file(tmp_path, [_row("x", "y", 2, 1), _row("y", "x", 1, 2)]))


def test_v4_sample_is_deterministic_distinct_and_skips_ties() -> None:
    pairs = _many(400) + [VibePair(f"t{i}", f"u{i}", 15, 15) for i in range(50)]
    first = sample_pairs(pairs)
    assert len(first) == VIBE_PAIRS == 150 and VIBE_SEED == 20261029
    assert len({pair.item for pair in first}) == 150
    assert all(pair.votes_a != pair.votes_b for pair in first)
    assert sample_pairs(list(reversed(pairs))) == first


def test_v5_sample_fails_with_too_few_pairs() -> None:
    with pytest.raises(JudgeError):
        sample_pairs(_many(149))


# --- prompt e voto ---

def test_v6_prompt_has_no_placeholders_and_asks_visual_design() -> None:
    prompt = vote_prompt()
    assert "<<" not in prompt
    assert "design visivo" in prompt
    assert "-2 = A molto meglio" in prompt


def test_v7_judge_votes_both_orders_and_averages(tmp_path: Path) -> None:
    pair = VibePair("x", "y", 8, 22)
    folder = _screens(tmp_path, ["x", "y"])
    calls: list[tuple[str, ...]] = []
    out = tmp_path / "giudizi.jsonl"
    result = judge_vibe([pair], folder, out, runner=_runner({("x", "y"): 2, ("y", "x"): -1}, calls), meta=META)
    assert calls == [("x", "y"), ("y", "x")]
    # positivo = preferisce app_b: (2 - (-1)) / 2
    assert result[0].value == 1.5 and result[0].item == "x|y"
    assert load_judgments(out) == result


def test_v8_missing_screenshot_stops_before_any_call(tmp_path: Path) -> None:
    folder = _screens(tmp_path, ["x"])
    calls: list[tuple[str, ...]] = []
    with pytest.raises(JudgeError):
        judge_vibe([VibePair("x", "y", 1, 2)], folder, tmp_path / "g.jsonl",
                   runner=_runner({}, calls), meta=META)
    assert calls == []


def test_v9_resume_skips_judged_pairs(tmp_path: Path) -> None:
    pairs = [VibePair("x", "y", 1, 2), VibePair("x", "z", 2, 1)]
    folder = _screens(tmp_path, ["x", "y", "z"])
    out = tmp_path / "g.jsonl"
    out.write_text(json.dumps(asdict(_judgment("x|y", 1.0))) + "\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    result = judge_vibe(pairs, folder, out, runner=_runner({("x", "z"): 0, ("z", "x"): 0}, calls), meta=META)
    assert calls == [("x", "z"), ("z", "x")]
    assert [row.item for row in result] == ["x|y", "x|z"]


def test_v10_resume_rejects_different_meta_or_foreign_pair(tmp_path: Path) -> None:
    folder = _screens(tmp_path, ["x", "y"])
    out = tmp_path / "g.jsonl"
    other = Judgment(**{**asdict(_judgment("x|y", 1.0)), "meta": {"model": "altro"}})
    out.write_text(json.dumps(asdict(other)) + "\n", encoding="utf-8")
    with pytest.raises(JudgeError):
        judge_vibe([VibePair("x", "y", 1, 2)], folder, out, runner=_runner({}, []), meta=META)
    out.write_text(json.dumps(asdict(_judgment("q|r", 1.0))) + "\n", encoding="utf-8")
    with pytest.raises(JudgeError):
        judge_vibe([VibePair("x", "y", 1, 2)], folder, out, runner=_runner({}, []), meta=META)


def test_v11_unratable_order_gives_none(tmp_path: Path) -> None:
    folder = _screens(tmp_path, ["x", "y"])
    result = judge_vibe([VibePair("x", "y", 1, 2)], folder, tmp_path / "g.jsonl",
                        runner=_runner({("x", "y"): None, ("y", "x"): 1}, []), meta=META)
    assert result[0].value is None


# --- calcolo e regola ---

def test_v12_report_point_estimates_by_hand() -> None:
    pairs = [VibePair("a", "b", 22, 8), VibePair("c", "d", 5, 25), VibePair("e", "f", 6, 4),
             VibePair("g", "h", 10, 20)]
    # d'accordo (A vince, giudice negativo); d'accordo; pareggio = disaccordo; non valutabile = disaccordo
    judgments = [_judgment("a|b", -1.0), _judgment("c|d", 0.5), _judgment("e|f", 0.0), _judgment("g|h", None)]
    report = vibe_report(pairs, judgments, samples=200, seed=1)
    reference = (22 / 30 + 25 / 30 + 6 / 10 + 20 / 30) / 4
    assert report["pairs"] == 4
    assert report["accuracy"]["point"] == pytest.approx(0.5)
    assert report["reference"]["point"] == pytest.approx(reference)
    assert report["delta"]["point"] == pytest.approx(0.5 - reference)
    assert report["judge_ties"] == 1 and report["unratable"] == 1


def test_v13_report_requires_same_pairs() -> None:
    pairs = [VibePair("a", "b", 22, 8), VibePair("c", "d", 5, 25)]
    with pytest.raises(JudgeError):
        vibe_report(pairs, [_judgment("a|b", -1.0)], samples=10, seed=1)
    with pytest.raises(JudgeError):
        vibe_report(pairs[:1], [_judgment("a|b", -1.0), _judgment("a|b", -1.0)], samples=10, seed=1)


def test_v14_bootstrap_is_reproducible_and_bounds_contain_point() -> None:
    pairs = [VibePair(f"a{i}", f"b{i}", 10 + i % 15, 5) for i in range(60)]
    judgments = [_judgment(pair.item, -1.0 if i % 3 else 1.0) for i, pair in enumerate(pairs)]
    one = vibe_report(pairs, judgments, samples=500, seed=7)
    two = vibe_report(pairs, judgments, samples=500, seed=7)
    assert one == two
    for name in ("accuracy", "reference", "delta"):
        assert one[name]["low"] <= one[name]["point"] <= one[name]["high"]
    assert one["samples"] == 500 and one["seed"] == 7


def test_v15_bootstrap_uses_same_resample_for_both() -> None:
    # Coppie unanimi (m/n = 1) dove il giudice e' d'accordo e coppie 11-9 (m/n = 0,55) dove sbaglia.
    # Con k coppie sbagliate su n nello stesso ripescaggio: accordo = 1 - k/n, riferimento = 1 - 0,45 k/n,
    # quindi delta = -0,55 (1 - accordo) esattamente. Con ripescaggi separati il legame si rompe.
    pairs = [VibePair(f"a{i}", f"b{i}", 30, 0) if i % 3 else VibePair(f"a{i}", f"b{i}", 11, 9) for i in range(60)]
    judgments = [_judgment(pair.item, -1.0 if pair.votes_a == 30 else 1.0) for pair in pairs]
    report = vibe_report(pairs, judgments, samples=500, seed=3)
    assert report["accuracy"]["low"] < report["accuracy"]["high"]
    assert report["delta"]["low"] == pytest.approx(-0.55 * (1 - report["accuracy"]["low"]))
    assert report["delta"]["high"] == pytest.approx(-0.55 * (1 - report["accuracy"]["high"]))


def test_v16_acceptance_thresholds_are_strict() -> None:
    assert accept_vibe(0.51, -0.09)
    assert not accept_vibe(0.5, 0.2)
    assert not accept_vibe(0.9, -0.10)
    assert not accept_vibe(0.4, 0.0)


def test_v17_report_records_verdict() -> None:
    pairs = [VibePair(f"a{i}", f"b{i}", 30, 0) for i in range(40)]
    good = vibe_report(pairs, [_judgment(pair.item, -2.0) for pair in pairs], samples=200, seed=1)
    bad = vibe_report(pairs, [_judgment(pair.item, 2.0) for pair in pairs], samples=200, seed=1)
    assert good["accepted"] is True and bad["accepted"] is False


# --- correzioni dopo la revisione indipendente ---

def test_v18_winner_must_match_votes(tmp_path: Path) -> None:
    row = _row("x", "y", 22, 8)
    row["winner"] = "app_b"
    with pytest.raises(JudgeError):
        load_pairs(_pairs_file(tmp_path, [row]))


def test_v19_report_with_no_pairs_is_a_project_error() -> None:
    with pytest.raises(JudgeError):
        vibe_report([], [], samples=10, seed=1)


def test_v20_limit_judges_first_pairs_and_resume_accepts_later_ones(tmp_path: Path) -> None:
    pairs = [VibePair("x", "y", 1, 2), VibePair("x", "z", 2, 1), VibePair("y", "z", 2, 1)]
    folder = _screens(tmp_path, ["x", "y", "z"])
    out = tmp_path / "g.jsonl"
    votes: dict[tuple[str, str], int | None] = {(a, b): 1 for a in "xyz" for b in "xyz" if a != b}
    calls: list[tuple[str, ...]] = []
    assert len(judge_vibe(pairs, folder, out, runner=_runner(votes, calls), meta=META, limit=2)) == 2
    # un lancio piu' corto dopo uno piu' lungo non rifiuta le coppie gia' giudicate
    assert len(judge_vibe(pairs, folder, out, runner=_runner(votes, calls), meta=META, limit=1)) == 1
    assert len(calls) == 4
    for bad in (0, -3):
        with pytest.raises(JudgeError):
            judge_vibe(pairs, folder, out, runner=_runner(votes, calls), meta=META, limit=bad)


def test_v21_check_screenshots_maps_every_app(tmp_path: Path) -> None:
    folder = _screens(tmp_path, ["x", "y"])
    assert check_screenshots([VibePair("x", "y", 1, 2)], folder) == {"x": folder / "x.png", "y": folder / "y.png"}
    with pytest.raises(JudgeError):
        check_screenshots([VibePair("x", "z", 1, 2)], folder)


def test_v22_selection_is_written_once_and_then_checked(tmp_path: Path) -> None:
    pairs = [VibePair("x", "y", 1, 2), VibePair("x", "z", 2, 1)]
    path = tmp_path / "scelte.json"
    freeze_selection(pairs, path)
    assert json.loads(path.read_text(encoding="utf-8")) == ["x|y", "x|z"]
    freeze_selection(pairs, path)
    with pytest.raises(JudgeError):
        freeze_selection(list(reversed(pairs)), path)
    with pytest.raises(JudgeError):
        freeze_selection(pairs, tmp_path / "manca.json", create=False)


def test_v23_cli_has_vibe_phases_and_positive_limit() -> None:
    from campaign import build_parser

    args = build_parser().parse_args(["calibration", "vibe-judge", "--limit", "2"])
    assert args.fase == "vibe-judge" and args.limit == 2
    assert build_parser().parse_args(["calibration", "vibe-agreement"]).samples == 10_000
    for bad in ("0", "-3"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["calibration", "vibe-judge", "--limit", bad])


def test_v24_cli_checks_screenshots_before_codex_or_selection(tmp_path: Path, monkeypatch) -> None:
    import campaign

    data = tmp_path / "campaigns" / "data" / "vibe" / "estratto"
    data.mkdir(parents=True)
    rows = [_row(f"a{i:03d}", f"b{i:03d}", 20, 10) for i in range(160)]
    (data / "coppie.json").write_text(json.dumps(rows), encoding="utf-8")
    (data / "screenshot").mkdir()
    monkeypatch.setattr(campaign, "PROJECT_ROOT", tmp_path)
    called: list[Any] = []
    monkeypatch.setattr(campaign.subprocess, "run", lambda *a, **k: called.append(a))
    args = campaign.build_parser().parse_args(["calibration", "vibe-judge"])
    with pytest.raises(JudgeError):
        campaign._calibration_phase(args)
    assert called == []
    assert not (tmp_path / "campaigns" / "r1_vibe_coppie.json").exists()
