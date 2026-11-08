"""Giudizio di sensibilita' con gli screenshot a riquadri (MH-4, P6-D1 d).

Nota di design (tesi):
    Il giudizio principale resta quello calibrato (R1.9): tre immagini per sito,
    tagliate a 4000 px. Questo modulo rifa' le stesse coppie, con lo stesso seme e
    gli stessi lati del piano gia' congelato, mostrando la pagina intera in
    riquadri, solo per vedere se il taglio ha cambiato i voti. I piani esistenti
    non devono cambiare di un byte: da essi dipende la ripresa dei giudizi.
    Nessun test chiama Codex o Docker.
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import judge
import judge_tiles
from judge import WIDTH_ORDER, Guide, JudgeError, RunOutput
from renderer import TileSet, TilesResult
from tests.test_judge_runs import RUNS, TASKS, _write_campaigns, _write_config

ROOT = Path(__file__).resolve().parent.parent
GUIDE = Guide("Scheda", "Obiettivo.", ("Ordine",), None)


# ── Fixture: sito a riquadri, indice e piano principale ───────────────────

def _tiles(root: Path, arm: str, task: str, counts: dict[int, int]) -> dict[str, Any]:
    widths = {}
    for width in WIDTH_ORDER:
        tiles = []
        for k in range(1, counts[width] + 1):
            path = root / f"{arm}-{task}" / f"tile-{width}-{k:02d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{arm}-{task}-{width}-{k}".encode())
            tiles.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        widths[str(width)] = {"height": counts[width] * 900, "truncated": False, "tiles": tiles}
    return widths


def _index(root: Path, counts: dict[int, int], *, skip: tuple[str, str] | None = None) -> Path:
    sites = []
    for arm, tasks in RUNS.items():
        for task, campaign_id in tasks.items():
            if (arm, task) == skip:
                continue
            sites.append({"arm": arm, "task_id": task, "campaign": campaign_id, "run_id": f"run-{arm}-{task}",
                          "started": True, "start_error": None, "vetrina": "ok",
                          "widths": _tiles(root, arm, task, counts)})
    path = root / "riquadri.json"
    path.write_text(json.dumps({"max_tiles": 20, "sites": sites}), encoding="utf-8")
    return path


@pytest.fixture
def main_plan(tmp_path: Path) -> Path:
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    config = judge.load_run_config(_write_config(tmp_path))
    path = tmp_path / "principale" / "coppie.json"
    judge.freeze_plan(judge.plan_run_pairs(config, campaigns_dir), config.seed, path)
    return path


COUNTS = {1440: 2, 768: 1, 375: 3}


# ── Piano a riquadri ───────────────────────────────────────────────────────

def test_j1_stesse_coppie_stessi_lati_stesse_run_del_piano_principale(main_plan, tmp_path):
    plan = judge_tiles.plan_tiles_pairs(main_plan, _index(tmp_path / "riq", COUNTS), max_tiles=20)
    principale = json.loads(main_plan.read_text(encoding="utf-8"))

    assert [p.item for p in plan.pairs] == [row["item"] for row in principale["pairs"]]
    for pair, row in zip(plan.pairs, principale["pairs"]):
        assert (pair.left_arm, pair.right_arm, pair.run_ids) == (row["left_arm"], row["right_arm"], row["run_ids"])
        assert len(pair.left) == len(pair.right) == sum(COUNTS.values())
        larghezze = [plan.layout[p].width for p in pair.left]
        assert larghezze == [1440, 1440, 768, 375, 375, 375]
    assert plan.seed == principale["seed"]
    assert plan.source_sha256 == hashlib.sha256(main_plan.read_bytes()).hexdigest()


def test_j2_il_tetto_del_giudice_tiene_i_primi_riquadri_e_segna_il_taglio(main_plan, tmp_path):
    plan = judge_tiles.plan_tiles_pairs(main_plan, _index(tmp_path / "riq", {1440: 2, 768: 1, 375: 5}),
                                        max_tiles=3)

    pair = plan.pairs[0]
    a375 = [p for p in pair.left if plan.layout[p].width == 375]
    assert [p.name for p in a375] == ["tile-375-01.png", "tile-375-02.png", "tile-375-03.png"]
    assert plan.layout[a375[0]].cut and not plan.layout[pair.left[0]].cut


@pytest.mark.parametrize("difetto", ["manca", "run_diversa"])
def test_j3_un_sito_mancante_o_di_un_altra_run_ferma_tutto(main_plan, tmp_path, difetto):
    index = _index(tmp_path / "riq", COUNTS, skip=("C", "t1") if difetto == "manca" else None)
    if difetto == "run_diversa":
        data = json.loads(index.read_text(encoding="utf-8"))
        data["sites"][0]["run_id"] = "altra"
        index.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(JudgeError):
        judge_tiles.plan_tiles_pairs(main_plan, index, max_tiles=20)


def test_j4_un_sito_che_oggi_non_parte_ferma_il_piano(main_plan, tmp_path):
    index = _index(tmp_path / "riq", COUNTS)
    data = json.loads(index.read_text(encoding="utf-8"))
    data["sites"][1].update({"started": False, "start_error": "porta non aperta", "widths": {}})
    index.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(JudgeError, match="porta non aperta"):
        judge_tiles.plan_tiles_pairs(main_plan, index, max_tiles=20)


def test_j5_il_piano_si_congela_e_uno_diverso_blocca_la_ripresa(main_plan, tmp_path):
    index = _index(tmp_path / "riq", COUNTS)
    out = tmp_path / "riquadri" / "coppie.json"

    sha = judge_tiles.freeze_tiles_plan(judge_tiles.plan_tiles_pairs(main_plan, index, max_tiles=20), out)
    assert sha == hashlib.sha256(out.read_bytes()).hexdigest()
    assert judge_tiles.freeze_tiles_plan(judge_tiles.plan_tiles_pairs(main_plan, index, max_tiles=20), out) == sha
    with pytest.raises(JudgeError, match="diverso"):
        judge_tiles.freeze_tiles_plan(judge_tiles.plan_tiles_pairs(main_plan, index, max_tiles=1), out)


# ── Prompt ─────────────────────────────────────────────────────────────────

def test_j6_il_prompt_dice_quali_immagini_sono_di_quale_sito_e_larghezza(main_plan, tmp_path):
    plan = judge_tiles.plan_tiles_pairs(main_plan, _index(tmp_path / "riq", {1440: 2, 768: 1, 375: 5}),
                                        max_tiles=3)
    pair = plan.pairs[0]

    text = judge_tiles.tiles_prompt("Make a timer page.", GUIDE, pair.left, pair.right, plan.layout)

    assert "immagini 1-2" in text and "immagine 3" in text and "immagini 4-6" in text
    assert "immagini 7-8" in text and "immagine 9" in text and "immagini 10-12" in text
    assert "Make a timer page." in text and "<<" not in text
    assert "tagliat" in text  # la pagina a 375 continua oltre il terzo riquadro


# ── Giudice: prompt diverso solo se richiesto ─────────────────────────────

class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Path, ...]]] = []

    def __call__(self, prompt: str, images: Sequence[Path], schema: dict[str, Any]) -> RunOutput:
        self.calls.append((prompt, tuple(images)))
        return RunOutput(json.dumps({"voto": 1, "motivo": "ok"}), 1.0, {}, None)


def test_j7_judge_pair_costruisce_il_prompt_per_ciascun_ordine(tmp_path):
    a = tuple(tmp_path / f"a{k}.png" for k in range(4))
    b = tuple(tmp_path / f"b{k}.png" for k in range(2))
    runner = Recorder()

    def prompt_for(task: str, guide: Guide, first: Sequence[Path], second: Sequence[Path]) -> str:
        return f"{len(first)}+{len(second)}"

    judge.judge_pair("compito", GUIDE, a, b, runner=runner, prompt_for=prompt_for)

    assert [c[0] for c in runner.calls] == ["4+2", "2+4"]
    assert runner.calls[0][1] == (*a, *b) and runner.calls[1][1] == (*b, *a)


def test_j8_senza_prompt_proprio_servono_ancora_tre_immagini_per_sito(tmp_path):
    a = tuple(tmp_path / f"a{k}.png" for k in range(4))
    b = tuple(tmp_path / f"b{k}.png" for k in range(3))

    with pytest.raises(JudgeError, match="servono 3 immagini"):
        judge.judge_pair("compito", GUIDE, a, b, runner=Recorder())


def test_j9_judge_run_pairs_passa_il_prompt_a_riquadri(main_plan, tmp_path):
    plan = judge_tiles.plan_tiles_pairs(main_plan, _index(tmp_path / "riq", COUNTS), max_tiles=20)
    guides = tmp_path / "schede.json"
    runner = Recorder()

    judge.judge_run_pairs(plan.pairs[:1], TASKS, guides, tmp_path / "out" / "giudizi.jsonl", runner=runner,
                          meta={"m": 1}, prompt_for=plan.prompt_for)

    assert len(runner.calls) == 2 and "riquadr" in runner.calls[0][0]
    assert len(runner.calls[0][1]) == 2 * sum(COUNTS.values())


# ── Rifacimento dei riquadri sui workspace della campagna ─────────────────

def _with_workspaces(campaigns_dir: Path, root: Path, *, missing: str | None = None) -> None:
    """Aggiunge ai manifesti finti il workspace di ogni run, con start.sh."""
    for manifest in campaigns_dir.glob("*.jsonl"):
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            if "task_id" in row:
                ws = root / "ws" / row["run_id"]
                if row["run_id"] != missing:
                    ws.mkdir(parents=True, exist_ok=True)
                    (ws / "start.sh").write_text("true\n")
                row["workspace"] = str(ws)
        manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _scripts(root: Path) -> Path:
    scripts = root / "script"
    scripts.mkdir()
    for task in TASKS:
        (scripts / f"{task}.py").write_text("def vetrina(c):\n    pass\n")
    return scripts


class FakeRender:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path, Path | None, int]] = []

    def __call__(self, workspace: Path, out_dir: Path, *, max_tiles: int, script: Path | None = None) -> TilesResult:
        self.calls.append((workspace, out_dir, script, max_tiles))
        out_dir.mkdir(parents=True, exist_ok=True)
        widths = {}
        for w in WIDTH_ORDER:
            tile = out_dir / f"tile-{w}-01.png"
            tile.write_bytes(f"{workspace.name}-{w}".encode())
            widths[w] = TileSet(width=w, height=800, tiles=(tile,), truncated=False)
        return TilesResult(started=True, widths=widths, vetrina="ok")


def test_j10_si_rifanno_i_riquadri_di_ogni_run_della_mappa(tmp_path):
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    _with_workspaces(campaigns_dir, tmp_path)
    config = judge.load_run_config(_write_config(tmp_path))
    render = FakeRender()

    index = judge_tiles.render_campaign(config, campaigns_dir, tmp_path / "riquadri", scripts_dir=_scripts(tmp_path),
                                        max_tiles=20, render=render)

    data = json.loads(index.read_text(encoding="utf-8"))
    assert len(render.calls) == len(data["sites"]) == sum(len(t) for t in RUNS.values())
    assert {(s["arm"], s["task_id"], s["run_id"]) for s in data["sites"]} == {
        (arm, task, f"run-{arm}-{task}") for arm, tasks in RUNS.items() for task in tasks}
    assert all(call[2] is not None and call[2].name.endswith(".py") for call in render.calls)
    tile = data["sites"][0]["widths"]["1440"]["tiles"][0]
    assert tile["sha256"] == hashlib.sha256(Path(tile["path"]).read_bytes()).hexdigest()


def test_j11_un_workspace_mancante_ferma_tutto_prima_di_creare_cartelle(tmp_path):
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    _with_workspaces(campaigns_dir, tmp_path, missing="run-D-t2")
    config = judge.load_run_config(_write_config(tmp_path))
    render = FakeRender()

    with pytest.raises(JudgeError, match="run-D-t2"):
        judge_tiles.render_campaign(config, campaigns_dir, tmp_path / "riquadri", scripts_dir=_scripts(tmp_path),
                                    max_tiles=20, render=render)
    assert render.calls == [] and not (tmp_path / "riquadri").exists()


# ── I piani gia' congelati della campagna non cambiano di un byte ──────────

@pytest.mark.parametrize(("config_name", "plan_dir"), [
    ("mvp_giudizio.toml", "giudizio-mvp"),
    ("mvp_giudizio_cd.toml", "giudizio-mvp-cd"),
])
def test_j12_i_piani_congelati_della_campagna_restano_identici(config_name, plan_dir):
    config_file = ROOT / "campaigns" / config_name
    frozen = ROOT / "runs" / plan_dir / "coppie.json"
    if not config_file.is_file() or not frozen.is_file():
        pytest.skip("dati della campagna non presenti (runs/ e' fuori da git)")
    before = frozen.read_bytes()
    config = judge.load_run_config(config_file)

    sha = judge.freeze_plan(judge.plan_run_pairs(config, ROOT / "runs" / "campaigns"), config.seed, frozen)

    assert frozen.read_bytes() == before
    assert sha == hashlib.sha256(before).hexdigest()


# ── Correzioni dopo la revisione indipendente (8 nov) ──────────────────────

def test_j13_render_rifiuta_una_cartella_di_uscita_gia_usata(tmp_path):
    campaigns_dir = tmp_path / "campaigns"
    _write_campaigns(campaigns_dir)
    _with_workspaces(campaigns_dir, tmp_path)
    config = judge.load_run_config(_write_config(tmp_path))
    out = tmp_path / "riquadri"
    (out / "B-t1").mkdir(parents=True)
    (out / "B-t1" / "tile-1440-09.png").write_bytes(b"vecchio")
    render = FakeRender()

    with pytest.raises(JudgeError, match="non vuota"):
        judge_tiles.render_campaign(config, campaigns_dir, out, scripts_dir=_scripts(tmp_path), max_tiles=20,
                                    render=render)
    assert render.calls == []


def test_j14_run_senza_yes_non_scrive_nulla(main_plan, tmp_path):
    index = _index(tmp_path / "riq", COUNTS)
    out = tmp_path / "giudizio"

    with pytest.raises(JudgeError, match="--yes"):
        judge_tiles.main(["run", "--main", str(main_plan), "--index", str(index), "--max-tiles", "20",
                          "--out", str(out)])
    assert not out.exists()


def test_j15_un_piano_principale_senza_coppie_e_un_errore_del_giudice(tmp_path):
    vuoto = tmp_path / "coppie.json"
    vuoto.write_text(json.dumps({"seed": 1, "widths": list(WIDTH_ORDER), "pairs": []}), encoding="utf-8")

    with pytest.raises(JudgeError, match="nessuna coppia"):
        judge_tiles.plan_tiles_pairs(vuoto, _index(tmp_path / "riq", COUNTS), max_tiles=20)
