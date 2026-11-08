"""Giudizio di sensibilita' con gli screenshot a riquadri (MH-4, scelta P6-D1 d dell'8 nov 2026).

Il giudizio principale della campagna MVP resta quello calibrato (R1.9): tre
immagini per sito, una per larghezza, tagliate a 4000 px. 12 di quelle 45
immagini sono tagliate. Questo modulo rifa' le stesse coppie con la pagina `/`
intera, divisa in riquadri alti quanto la finestra, per vedere se il taglio ha
cambiato i voti. Non sostituisce il giudizio principale.

Tre passi, ciascuno con un comando:
    render  rifa' i riquadri dei workspace della mappa (Docker, nessuna chiamata a modelli);
    plan    deriva il piano a riquadri dal piano principale gia' congelato e lo congela;
    run     giudica le coppie con Codex, solo con `--yes`.

Nota di design (tesi):
    Il piano a riquadri non ricostruisce le coppie dalla mappa: le legge dal piano
    principale congelato (`runs/giudizio-mvp/coppie.json`), cosi' coppie, seme e
    lati sinistro/destro sono gli stessi per costruzione e il piano registra
    l'impronta del piano da cui deriva. I piani principali non si toccano.
"""

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import judge
from judge import WIDTH_ORDER, Guide, JudgeError, PlannedPair, RunConfig
from renderer import TILES_IMAGE, TilesResult, render_tiles

PROJECT_ROOT = Path(__file__).resolve().parent
#: Tetto di riquadri per larghezza al rendering (18.000 px): largo, il tetto del giudice si sceglie dopo.
MAX_TILES_RENDER = 20
TILES_PROMPT = "voto_riquadri.txt"
INDEX_NAME = "riquadri.json"

Render = Callable[..., TilesResult]


@dataclass(frozen=True)
class TileRef:
    """Posizione di un riquadro: larghezza, numero dall'alto e se la pagina continua oltre il tetto."""

    width: int
    index: int
    cut: bool


@dataclass(frozen=True)
class TilesPlan:
    """Le coppie del piano principale con i riquadri al posto delle tre immagini."""

    seed: int
    source_sha256: str
    max_tiles: int
    pairs: tuple[PlannedPair, ...]
    layout: dict[Path, TileRef] = field(default_factory=dict)

    def prompt_for(self, task: str, guide: Guide, first: Sequence[Path], second: Sequence[Path]) -> str:
        """Il prompt di un ordine, da passare a `judge.judge_run_pairs`."""
        return tiles_prompt(task, guide, first, second, self.layout)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise JudgeError(f"{path}: lettura non riuscita: {error}") from error


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise JudgeError(f"lettura di un riquadro non riuscita: {error}") from error


# ── render ─────────────────────────────────────────────────────────────────

def _manifest_row(campaigns_dir: Path, campaign: str, task_id: str) -> dict[str, Any]:
    """La sola riga del compito nel manifesto della campagna (stessa regola di `judge._run_site`)."""
    manifest = campaigns_dir / f"{campaign}.jsonl"
    try:
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as error:
        raise JudgeError(f"{manifest}: lettura del manifesto non riuscita: {error}") from error
    found = [row for row in rows if isinstance(row, dict) and row.get("task_id") == task_id]
    if len(found) != 1:
        raise JudgeError(f"{manifest}: attesa una riga per il compito {task_id}, trovate {len(found)}")
    return found[0]


def render_campaign(config: RunConfig, campaigns_dir: Path, out_dir: Path, *, scripts_dir: Path,
                    max_tiles: int = MAX_TILES_RENDER, render: Render = render_tiles) -> Path:
    """Rifa' i riquadri di ogni run della mappa e scrive l'indice; restituisce il suo percorso.

    Si valida tutto (manifesti, workspace, script) prima di creare cartelle o
    avviare container. Il renderer lavora su una copia: i workspace di `runs/` e
    `workspace/` non cambiano.

    Raises:
        JudgeError: mappa, manifesto, workspace o script non validi, o indice gia' presente.
        RenderError: guasto del renderer su un sito (l'indice non viene scritto).
    """
    if max_tiles < 1:
        raise JudgeError("max_tiles deve essere almeno 1")
    index = out_dir / INDEX_NAME
    # Cartella nuova o vuota: riquadri di un lancio precedente resterebbero accanto ai nuovi
    # senza comparire nell'indice.
    if out_dir.exists() and any(out_dir.iterdir()):
        raise JudgeError(f"{out_dir}: cartella di uscita non vuota, non si sovrascrive")
    jobs = []
    for arm in sorted(config.runs):
        for task_id in sorted(config.runs[arm]):
            campaign = config.runs[arm][task_id]
            row = _manifest_row(campaigns_dir, campaign, task_id)
            run_id, workspace = row.get("run_id"), row.get("workspace")
            if not isinstance(run_id, str) or not isinstance(workspace, str):
                raise JudgeError(f"{campaign}/{task_id}: run_id o workspace mancante nel manifesto")
            if not (Path(workspace) / "start.sh").is_file():
                raise JudgeError(f"{campaign}/{task_id}: workspace della run {run_id} mancante o senza start.sh: "
                                 f"{workspace}")
            script = scripts_dir / f"{task_id}.py"
            if not script.is_file():
                raise JudgeError(f"script del compito mancante: {script}")
            jobs.append((arm, task_id, campaign, run_id, Path(workspace), script))
    sites = []
    for arm, task_id, campaign, run_id, workspace, script in jobs:
        result = render(workspace, out_dir / f"{arm}-{task_id}", max_tiles=max_tiles, script=script)
        widths = {str(width): {"height": view.height, "truncated": view.truncated,
                               "tiles": [{"path": str(tile), "sha256": _sha256(tile)} for tile in view.tiles]}
                  for width, view in sorted(result.widths.items(), reverse=True)}
        sites.append({"arm": arm, "task_id": task_id, "campaign": campaign, "run_id": run_id,
                      "workspace": str(workspace), "started": result.started, "start_error": result.start_error,
                      "vetrina": result.vetrina, "versions": result.versions, "widths": widths})
    data = {"max_tiles": max_tiles, "image": TILES_IMAGE, "date": datetime.now(timezone.utc).isoformat(),
            "sites": sites}
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        index.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as error:
        raise JudgeError(f"{index}: indice non scritto: {error}") from error
    return index


# ── plan ───────────────────────────────────────────────────────────────────

def _side_tiles(site: dict[str, Any], max_tiles: int, layout: dict[Path, TileRef]) -> tuple[Path, ...]:
    """I riquadri di un sito in ordine di larghezza, al piu' `max_tiles` per larghezza."""
    if not site.get("started"):
        raise JudgeError(f"{site.get('arm')}/{site.get('task_id')}: il sito non e' partito al rendering: "
                         f"{site.get('start_error')}")
    images = []
    for width in WIDTH_ORDER:
        view = site.get("widths", {}).get(str(width))
        if not isinstance(view, dict) or not isinstance(view.get("tiles"), list) or not view["tiles"]:
            raise JudgeError(f"{site.get('arm')}/{site.get('task_id')}: riquadri a {width} px mancanti")
        tiles = view["tiles"]
        cut = bool(view.get("truncated")) or len(tiles) > max_tiles
        for number, tile in enumerate(tiles[:max_tiles], 1):
            path = Path(tile["path"])
            if _sha256(path) != tile.get("sha256"):
                raise JudgeError(f"{path}: riquadro diverso da quello registrato nell'indice")
            layout[path] = TileRef(width, number, cut)
            images.append(path)
    return tuple(images)


def plan_tiles_pairs(main_plan: Path, index: Path, max_tiles: int) -> TilesPlan:
    """Le coppie del piano principale congelato, con i riquadri dell'indice.

    Raises:
        JudgeError: piano o indice illeggibili, sito mancante, di un'altra run,
            non partito o con riquadri diversi da quelli registrati.
    """
    if max_tiles < 1:
        raise JudgeError("max_tiles deve essere almeno 1")
    try:
        source = main_plan.read_bytes()
    except OSError as error:
        raise JudgeError(f"{main_plan}: lettura del piano non riuscita: {error}") from error
    principale = _read_json(main_plan)
    sites = {(site.get("arm"), site.get("task_id")): site for site in _read_json(index).get("sites", [])}
    layout: dict[Path, TileRef] = {}
    pairs = []
    try:
        for row in principale["pairs"]:
            sides = {}
            for arm in (row["left_arm"], row["right_arm"]):
                site = sites.get((arm, row["task_id"]))
                if site is None:
                    raise JudgeError(f"{row['item']}: riquadri di {arm} mancanti nell'indice")
                if site.get("run_id") != row["run_ids"][arm]:
                    raise JudgeError(f"{row['item']}: l'indice ha la run {site.get('run_id')} per {arm}, "
                                     f"il piano principale {row['run_ids'][arm]}")
                sides[arm] = _side_tiles(site, max_tiles, layout)
            pairs.append(PlannedPair(row["item"], row["pair_id"], row["task_id"], row["challenger"], row["baseline"],
                                     row["left_arm"], row["right_arm"], sides[row["left_arm"]],
                                     sides[row["right_arm"]], dict(row["run_ids"])))
        seed = int(principale["seed"])
    except (KeyError, TypeError, ValueError) as error:
        raise JudgeError(f"{main_plan}: piano principale non valido: {error}") from error
    if not pairs:
        raise JudgeError(f"{main_plan}: nessuna coppia nel piano principale")
    return TilesPlan(seed, hashlib.sha256(source).hexdigest(), max_tiles, tuple(pairs), layout)


def freeze_tiles_plan(plan: TilesPlan, path: Path) -> str:
    """Scrive il piano a riquadri; uno diverso da quello gia' scritto blocca la ripresa."""
    def images(paths: tuple[Path, ...]) -> list[dict[str, Any]]:
        return [{"width": plan.layout[p].width, "tile": plan.layout[p].index, "cut": plan.layout[p].cut,
                 "path": str(p), "sha256": _sha256(p)} for p in paths]

    rows = [{"item": pair.item, "pair_id": pair.pair_id, "task_id": pair.task_id, "challenger": pair.challenger,
             "baseline": pair.baseline, "left_arm": pair.left_arm, "right_arm": pair.right_arm,
             "run_ids": pair.run_ids, "left": images(pair.left), "right": images(pair.right)} for pair in plan.pairs]
    text = json.dumps({"seed": plan.seed, "source_plan_sha256": plan.source_sha256, "max_tiles": plan.max_tiles,
                       "widths": list(WIDTH_ORDER), "pairs": rows}, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise JudgeError(f"{path}: piano a riquadri congelato diverso da quello attuale")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise JudgeError(f"{path}: piano non scritto: {error}") from error
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── prompt ─────────────────────────────────────────────────────────────────

def _images_text(label: str, paths: Sequence[Path], layout: Mapping[Path, TileRef], start: int) -> list[str]:
    lines = [f"Proposta {label}:"]
    position = start
    for width in WIDTH_ORDER:
        tiles = [p for p in paths if layout[p].width == width]
        first, last = position, position + len(tiles) - 1
        where = f"immagine {first}" if first == last else f"immagini {first}-{last}"
        cut = any(layout[p].cut for p in tiles)
        tail = "; la pagina continua oltre e qui e' tagliata" if cut else ""
        lines.append(f"- larga {width} pixel: {where} ({len(tiles)} riquadri{tail})")
        position = last + 1
    return lines


def tiles_prompt(task: str, guide: Guide, first: Sequence[Path], second: Sequence[Path],
                 layout: Mapping[Path, TileRef]) -> str:
    """Il prompt di `voto_riquadri.txt` con l'elenco delle immagini di A e di B."""
    a = _images_text("A", first, layout, 1)
    b = _images_text("B", second, layout, len(first) + 1)
    return judge._prompt(TILES_PROMPT, task, guide, {"<<IMMAGINI>>": "\n".join(a + b)})


# ── comandi ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """CLI senza accedere a Docker, Codex o rete finche' non si esegue un comando."""
    parser = argparse.ArgumentParser(description="Giudizio di sensibilita' a riquadri (MH-4)")
    sotto = parser.add_subparsers(dest="comando", required=True)
    render = sotto.add_parser("render", help="rifa' i riquadri dei workspace della mappa (Docker)")
    render.add_argument("--config", type=Path, default=PROJECT_ROOT / "campaigns" / "mvp_giudizio.toml")
    render.add_argument("--campaigns-dir", type=Path, default=PROJECT_ROOT / "runs" / "campaigns")
    render.add_argument("--scripts-dir", type=Path, default=PROJECT_ROOT / "campaigns" / "r1_valutazione")
    render.add_argument("--max-tiles", type=int, default=MAX_TILES_RENDER)
    render.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs" / "riquadri-mvp")
    for name in ("plan", "run"):
        sub = sotto.add_parser(name, help="congela il piano a riquadri" if name == "plan"
                               else "giudica le coppie con Codex (serve --yes)")
        sub.add_argument("--main", type=Path, default=PROJECT_ROOT / "runs" / "giudizio-mvp" / "coppie.json")
        sub.add_argument("--index", type=Path, default=PROJECT_ROOT / "runs" / "riquadri-mvp" / INDEX_NAME)
        sub.add_argument("--max-tiles", type=int, required=True, help="riquadri per larghezza mostrati al giudice")
        sub.add_argument("--out", type=Path, default=PROJECT_ROOT / "runs" / "giudizio-mvp-riquadri")
        if name == "run":
            sub.add_argument("--config", type=Path, default=PROJECT_ROOT / "campaigns" / "mvp_giudizio.toml")
            sub.add_argument("--yes", action="store_true", help="conferma le chiamate a Codex")
            sub.add_argument("--items", default=None, help="solo queste coppie, separate da virgola (es. C-B/000058)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.comando == "render":
        index = render_campaign(judge.load_run_config(args.config), args.campaigns_dir, args.out,
                                scripts_dir=args.scripts_dir, max_tiles=args.max_tiles)
        for site in _read_json(index)["sites"]:
            heights = ", ".join(f"{w}: {v['height']} px ({len(v['tiles'])})" for w, v in site["widths"].items())
            print(f"{site['arm']} {site['task_id']}: {heights or site['start_error']}")
        print(f"indice: {index}")
        return 0
    # Prima di scrivere il piano: un `run` rifiutato non deve lasciare nulla su disco.
    if args.comando == "run" and not args.yes:
        raise JudgeError("le chiamate a Codex partono solo con --yes")
    plan = plan_tiles_pairs(args.main, args.index, args.max_tiles)
    plan_sha = freeze_tiles_plan(plan, args.out / "coppie.json")
    per_call = max(len(pair.left) + len(pair.right) for pair in plan.pairs)
    print(f"coppie: {len(plan.pairs)}; chiamate: {2 * len(plan.pairs)}; immagini per chiamata: al piu' {per_call}")
    print(f"piano: {args.out / 'coppie.json'} (sha256 {plan_sha})")
    if args.comando == "plan":
        return 0
    import campaign

    config = judge.load_run_config(args.config)
    items = [item.strip() for item in args.items.split(",") if item.strip()] if args.items is not None else None
    meta = {"model": judge.JUDGE_MODEL, "effort": judge.JUDGE_EFFORT, "codex_version": campaign._codex_version(),
            "vote_sha256": _sha256(judge.PROMPT_DIR / TILES_PROMPT),
            "guides_sha256": _sha256(config.guides_file), "plan_sha256": plan_sha}
    judgments = judge.judge_run_pairs(plan.pairs, campaign._task_texts(config.tasks_file), config.guides_file,
                                      args.out / "giudizi.jsonl", runner=judge.codex_runner(), meta=meta,
                                      prompt_for=plan.prompt_for, items=items)
    for pair_id, entry in judge.summarize_run_judgments(judgments).items():
        mean = f"{entry['mean']:+.2f}" if entry["mean"] is not None else "n.d."
        print(f"{pair_id}: media {mean} su {entry['rated']} compiti; non valutabili {entry['unratable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
