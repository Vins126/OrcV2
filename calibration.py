"""Coppie di calibrazione, rendering riprendibile e voti anonimi (R1.8)."""

import hashlib
import http.client
import itertools
import json
import math
import random
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parallel_runner import run_parallel
from renderer import WIDTHS, RenderError, RenderResult, render_site
from webtasks import Source, WebTaskError, _sha256

RESPONSES_COMMIT = "88c968b87e150e63de7660937e6dcfb8e7d643cf"
RESPONSE_SOURCES: tuple[Source, ...] = (
    Source(name="Claude_3.5_Sonnet_20241022",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Claude_3.5_Sonnet_20241022.jsonl",
           filename="gemini_2.5_pro_judge_Claude_3.5_Sonnet_20241022.jsonl",
           sha256="7199f8500664a73b912498c73d75c745d8d1a9304829ecbe112c1d539365b23c"),
    Source(name="Claude_3.7_Sonnet_20250219",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Claude_3.7_Sonnet_20250219.jsonl",
           filename="gemini_2.5_pro_judge_Claude_3.7_Sonnet_20250219.jsonl",
           sha256="bd65e47c6d07d8d47fa6871187a6b0362e5d1addbbd2273a1871c0f456fd4224"),
    Source(name="Claude_Sonnet_4_20250514",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Claude_Sonnet_4_20250514.jsonl",
           filename="gemini_2.5_pro_judge_Claude_Sonnet_4_20250514.jsonl",
           sha256="4372d75dca5bbc2d9c66400b86d74c8a4113ebbaab573087fe262eef3582e74f"),
    Source(name="DeepSeek-R1-0528",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_DeepSeek-R1-0528.jsonl",
           filename="gemini_2.5_pro_judge_DeepSeek-R1-0528.jsonl",
           sha256="5cbd7c91b56ce2c60471b77ffa2d89b6cac7bcf56d79cf2a3c851f8ec9437bf1"),
    Source(name="DeepSeek-R1",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_DeepSeek-R1.jsonl",
           filename="gemini_2.5_pro_judge_DeepSeek-R1.jsonl",
           sha256="b52d61321b21231072ff8e79bc451dd9fa117cb2ca5b858cce239ff706c83f92"),
    Source(name="DeepSeek-V3-0324",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_DeepSeek-V3-0324.jsonl",
           filename="gemini_2.5_pro_judge_DeepSeek-V3-0324.jsonl",
           sha256="aa84aa893f97998f4eadf03027e5f57329b30f6cefa25686c8e7c516d4f5cd8f"),
    Source(name="Hunyuan_A13B",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Hunyuan_A13B.jsonl",
           filename="gemini_2.5_pro_judge_Hunyuan_A13B.jsonl",
           sha256="fd091e68a8ed7a047a21532de5a05366f134c1c5842d85ab2f6c2c4e65aef86e"),
    Source(name="KAT-V1",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_KAT-V1.jsonl",
           filename="gemini_2.5_pro_judge_KAT-V1.jsonl",
           sha256="3d88554233f6e564fb3057d5fe749a57e9cb46eae084f13cc87a163545567b29"),
    Source(name="Qwen3-235B-A22B-Instruct-2507",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Qwen3-235B-A22B-Instruct-2507.jsonl",
           filename="gemini_2.5_pro_judge_Qwen3-235B-A22B-Instruct-2507.jsonl",
           sha256="e373cb38496754c94af4fc8714402c798ae57dfcad8ae4a9e2b97fb4156a4dd9"),
    Source(name="Qwen3-235B-A22B-Thinking-2507",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Qwen3-235B-A22B-Thinking-2507.jsonl",
           filename="gemini_2.5_pro_judge_Qwen3-235B-A22B-Thinking-2507.jsonl",
           sha256="999b5fbed88ec65eb4c8ba1cc751824a206cd2d721fdd5ac793f9e0404e3c3c7"),
    Source(name="Qwen3-235B-A22B",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Qwen3-235B-A22B.jsonl",
           filename="gemini_2.5_pro_judge_Qwen3-235B-A22B.jsonl",
           sha256="a3937bad3566e77d6bdcfb92ef36fdb2a036933ed67dee47cf12072712f81524"),
    Source(name="Qwen3-Coder-480B-A35B-Instruct",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_Qwen3-Coder-480B-A35B-Instruct.jsonl",
           filename="gemini_2.5_pro_judge_Qwen3-Coder-480B-A35B-Instruct.jsonl",
           sha256="2a2de235e5725b07beb397d5f568a9be585aff93a5accae7007279ffd2f6befc"),
    Source(name="gemini-2.5-pro",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_gemini-2.5-pro.jsonl",
           filename="gemini_2.5_pro_judge_gemini-2.5-pro.jsonl",
           sha256="72153c68d629c0c85e43243828b35ab8958fe2fc38eb21522e7693c205192208"),
    Source(name="glm-4.5",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_glm-4.5.jsonl",
           filename="gemini_2.5_pro_judge_glm-4.5.jsonl",
           sha256="cd9f08d210670838855da1c2d845fc0a26ca1e539724b66572f9aedd2ad6c49d"),
    Source(name="gpt-5-chat-latest",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_gpt-5-chat-latest.jsonl",
           filename="gemini_2.5_pro_judge_gpt-5-chat-latest.jsonl",
           sha256="49f388588e4e5f0eaab9d33fbdc53e090bca1e020570563c4e3acfd021aa472c"),
    Source(name="gpt-5",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_gpt-5.jsonl",
           filename="gemini_2.5_pro_judge_gpt-5.jsonl",
           sha256="eab68e0cf640dcd9b33802acbc16a8463ea798b1cad18b116c0421a54173577a"),
    Source(name="gpt4o",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_gpt4o.jsonl",
           filename="gemini_2.5_pro_judge_gpt4o.jsonl",
           sha256="59b0ebf0b05d4e38c776c57bdfba88cc268c39038a2ee4506a50b3421a172045"),
    Source(name="gpt_4.1",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_gpt_4.1.jsonl",
           filename="gemini_2.5_pro_judge_gpt_4.1.jsonl",
           sha256="26c7988668010f388043e7fc0415a53a916331ec219c9212e04b2424392431bd"),
    Source(name="kimi-k2",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_kimi-k2.jsonl",
           filename="gemini_2.5_pro_judge_kimi-k2.jsonl",
           sha256="2e2a6c49efa47b3ab4dabc200a17687bb6ab170cb15be424771ab76e7ac9027a"),
    Source(name="o3",
           url="https://raw.githubusercontent.com/Tencent-Hunyuan/ArtifactsBenchmark/"
               f"{RESPONSES_COMMIT}/dataset/release_data_20250725/gemini_2.5_pro_judge_o3.jsonl",
           filename="gemini_2.5_pro_judge_o3.jsonl",
           sha256="e95a729ec744b38aeeba34973032e5557ae82ad48bc522eb2f9841834078d6a1"),
)


FENCE = re.compile(r"^[ \t]*```[ \t]*([A-Za-z0-9_+\-.#]*)[^\n]*\n(.*?)^[ \t]*```", re.S | re.M)
DOCSTART = re.compile(r"^\s*(<!doctype\s+html|<html)", re.I)
SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
HREF = re.compile(r"\bhref\s*=\s*[\"']?([^\"'\s>]+)", re.I)
REL = re.compile(r"\brel\s*=\s*[\"']?([^\"'>]+)", re.I)
MEDIA_SRC = re.compile(r"<(?:img|audio|video|source|iframe|embed)\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.I)
CSS_IMPORT = re.compile(r"@import\s+(?:url\()?\s*[\"']?(https?:)?//", re.I)
CSS_URL_NET = re.compile(r"url\(\s*[\"']?(?:https?:)?//", re.I)
JS_NET = re.compile(r"\b(?:fetch|import)\s*\(\s*[\"'`](?:https?:)?//|\bimport\s+[^;\n]*from\s+[\"'](?:https?:)?//|new\s+WebSocket\s*\(|XMLHttpRequest", re.I)

def is_net(u: str) -> bool:
    return bool(re.match(r"^(https?:)?//", u, re.I))

def is_local_file(u: str) -> bool:
    if is_net(u) or u.startswith(("data:", "blob:", "#", "javascript:", "about:")):
        return False
    return True

def classify(text: str) -> tuple[str, str | None]:
    blocks = FENCE.findall(text)
    info = {}
    if not blocks:
        if DOCSTART.match(text):
            return "doc_senza_blocco", text
        if re.search(r"<html|<!doctype", text, re.I):
            return "html_non_estraibile", None  # html in mezzo a prosa senza blocco
        return "nessun_codice", None
    langs = [b[0].lower() for b in blocks]
    def is_html_block(lang: str, body: str) -> bool:
        return lang in ("html", "htm", "xhtml") or (lang == "" and bool(DOCSTART.match(body)))
    html_idx = [i for i, (l, b) in enumerate(blocks) if is_html_block(l.lower(), b)]
    if len(blocks) == 1 and html_idx:
        return "un_blocco_html", blocks[0][1]
    if not html_idx:
        return "blocchi_non_html", None
    if len(html_idx) == len(blocks):
        return "piu_blocchi_html", None
    return "blocchi_misti", None

def analyze_html(h: str) -> dict[str, Any]:
    d = {}
    low = h.lower()
    d["completo"] = ("<html" in low or "<body" in low or "<!doctype" in low)
    d["chiuso"] = "</html>" in low
    loc_script = [u for u in SCRIPT_SRC.findall(h) if is_local_file(u)]
    net_script = [u for u in SCRIPT_SRC.findall(h) if is_net(u)]
    loc_css, net_css, net_font = [], [], []
    for tag in LINK_TAG.findall(h):
        m = HREF.search(tag)
        if not m:
            continue
        u = m.group(1)
        match_rel = REL.search(tag)
        rel = match_rel.group(1).lower() if match_rel else ""
        if "stylesheet" not in rel and "preload" not in rel and "modulepreload" not in rel:
            continue  # icon, preconnect, canonical: non bloccano il rendering
        if is_net(u):
            (net_font if "fonts.googleapis" in u or "fonts.gstatic" in u else net_css).append(u)
        elif is_local_file(u):
            loc_css.append(u)
    d["locali"] = len(loc_script) + len(loc_css)
    d["net_script"] = len(net_script)
    d["net_css"] = len(net_css)
    d["net_font"] = len(net_font) + (1 if re.search(r"@import[^;]*fonts\.googleapis", h, re.I) else 0)
    d["net_css_import"] = 1 if CSS_IMPORT.search(h) else 0
    d["net_media"] = sum(1 for u in MEDIA_SRC.findall(h) if is_net(u)) + len(CSS_URL_NET.findall(h))
    d["net_js"] = 1 if JS_NET.search(h) else 0
    d["hosts_script"] = sorted({re.sub(r"^(https?:)?//", "", u).split("/")[0] for u in net_script})
    d["len"] = len(h)
    return d


@dataclass(frozen=True)
class Response:
    """Una risposta collegata al testo originale del compito."""

    task_id: str
    model: str
    text: str
    score: float | None


@dataclass(frozen=True)
class Pair:
    """Due modelli sullo stesso compito, in ordine alfabetico."""

    pair_id: str
    task_id: str
    model_a: str
    model_b: str
    score_a: float
    score_b: float


@dataclass(frozen=True)
class Vote:
    """Voto riportato alla coppia: positivo se e' preferito model_b."""

    voter: str
    pair_id: str
    value: int
    repeat: bool
    ms: int


@dataclass(frozen=True)
class RenderSummary:
    """Conteggi delle pagine elaborate, saltate, guaste e non partite."""

    rendered: int
    skipped: int
    failed: list[str]
    not_started: list[str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WebTaskError(f"{path}: lettura non riuscita: {error}") from error


def _write_json(path: Path, data: Any) -> None:
    """Sostituisce il file solo quando la scrittura e' completa."""
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".calibration-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=1, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    except (OSError, ValueError) as error:
        raise WebTaskError(f"{path}: scrittura non riuscita: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _verify_sources(data_dir: Path, sources: Sequence[Source]) -> None:
    for source in sources:
        path = data_dir / source.filename
        try:
            digest = _sha256(path)
        except OSError as error:
            raise WebTaskError(f"{path}: file non leggibile: {error}") from error
        if digest != source.sha256:
            raise WebTaskError(f"{path}: sha256 diverso dall'atteso")


def _download(url: str) -> Iterable[bytes]:
    with urllib.request.urlopen(url, timeout=120) as stream:
        while chunk := stream.read(1024 * 1024):
            yield chunk


def fetch_responses(dest: Path, *, download: Callable[[str], Iterable[bytes]] | None = None,
                    sources: Sequence[Source] = RESPONSE_SOURCES) -> Path:
    """Scarica a pezzi e pubblica la cartella solo dopo tutti i controlli sha256."""
    if dest.exists():
        _verify_sources(dest, sources)
        return dest
    temporary: Path | None = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".responses-", dir=dest.parent))
        for source in sources:
            digest = hashlib.sha256()
            with (temporary / source.filename).open("wb") as stream:
                for chunk in (download or _download)(source.url):
                    digest.update(chunk)
                    stream.write(chunk)
            if digest.hexdigest() != source.sha256:
                raise WebTaskError(f"{source.name}: sha256 diverso dall'atteso")
        temporary.rename(dest)
    except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
        raise WebTaskError(f"scaricamento delle risposte non riuscito: {error}") from error
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
    return dest


def _rows(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise WebTaskError(f"{path}: riga {number} non e' un oggetto")
                yield row
    except (OSError, ValueError) as error:
        raise WebTaskError(f"{path}: lettura delle righe non riuscita: {error}") from error


def load_responses(data_dir: Path, tasks_file: Path, *,
                   sources: Sequence[Source] = RESPONSE_SOURCES) -> tuple[list[Response], int]:
    """Verifica le fonti e collega soltanto domande identiche, senza normalizzarle."""
    _verify_sources(data_dir, sources)
    tasks: dict[str, str] = {}
    responses: list[Response] = []
    unmatched = 0
    seen: set[tuple[str, str]] = set()
    try:
        for row in _rows(tasks_file):
            question, task_id = row["question"], str(row["index"])
            if question in tasks and tasks[question] != task_id:
                raise WebTaskError(f"{tasks_file}: domanda collegata a piu' compiti")
            tasks[question] = task_id
        for source in sources:
            for row in _rows(data_dir / source.filename):
                task_id = tasks.get(row["question"])
                if task_id is None:
                    unmatched += 1
                    continue
                key = (task_id, source.name)
                if key in seen:
                    raise WebTaskError(f"risposta doppia per {task_id}-{source.name}")
                seen.add(key)
                try:
                    score = float(str(row.get("gemini_mllm_score")).strip())
                    if not math.isfinite(score):
                        score = None
                except ValueError:
                    score = None
                text = row.get("model_infer_result") or ""
                if not isinstance(text, str):
                    raise WebTaskError(f"{task_id}-{source.name}: risposta non testuale")
                responses.append(Response(task_id, source.name, text, score))
    except (KeyError, TypeError) as error:
        raise WebTaskError(f"dati delle risposte incompleti: {error}") from error
    return responses, unmatched


def extract_html(text: str) -> str | None:
    """Estrae un solo documento o un solo blocco HTML, senza combinare blocchi."""
    return classify(text)[1]


def is_valid_page(html: str) -> bool:
    """Richiede una pagina completa e senza riferimenti a script o CSS locali."""
    analysis = analyze_html(html)
    return bool(analysis["completo"] and analysis["locali"] == 0)


def uses_network(html: str) -> bool:
    """Applica le sei categorie di rete usate nell'analisi delle risposte."""
    analysis = analyze_html(html)
    return sum(analysis[key] for key in ("net_script", "net_css", "net_font",
                                        "net_css_import", "net_media", "net_js")) > 0


_MODEL_NAME = re.compile(
    r"\b(?:claude|anthropic|gpt|openai|chatgpt|gemini|google ai|deepseek|qwen|kimi|"
    r"moonshot|glm|zhipu|hunyuan|tencent|kat)\b", re.I)


def names_a_model(html: str) -> bool:
    """Cerca firme a parola intera anche in script e commenti della pagina."""
    return bool(_MODEL_NAME.search(html))


def calibration_task_ids(order_file: Path) -> list[str]:
    """Usa la coda dalla trecentesima posizione dell'ordine registrato."""
    data = _read_json(order_file)
    if not isinstance(data, dict) or not isinstance(data.get("artifactsbench"), list):
        raise WebTaskError(f"{order_file}: ordine artifactsbench mancante")
    return [str(task_id) for task_id in data["artifactsbench"][299:]]


def usable_responses(responses: Sequence[Response], eligible_ids: Sequence[str], *,
                     exclude_named: bool = True) -> tuple[list[Response], dict[str, int]]:
    """Filtra in cascata, attribuendo ogni scarto al primo motivo applicabile."""
    eligible = set(eligible_ids)
    rejected: dict[str, int] = dict.fromkeys(
        ("fuori_coda", "non_estraibile", "non_valida", "senza_punteggio", "rete", "nome_modello"), 0)
    usable: list[Response] = []
    for response in responses:
        html = extract_html(response.text) if response.task_id in eligible else None
        reason = None
        if response.task_id not in eligible:
            reason = "fuori_coda"
        elif html is None:
            reason = "non_estraibile"
        elif not is_valid_page(html):
            reason = "non_valida"
        elif response.score is None or not math.isfinite(response.score):
            reason = "senza_punteggio"
        elif uses_network(html):
            reason = "rete"
        elif exclude_named and names_a_model(html):
            reason = "nome_modello"
        if reason is not None:
            rejected[reason] += 1
        else:
            usable.append(response)
    return usable, rejected


def _balance(candidates: dict[str, list[Pair]], cap: int, seed: int, iterations: int,
             initial: Counter[str]) -> list[Pair]:
    best: list[Pair] = []
    for iteration in range(iterations):
        rnd = random.Random(seed + iteration)
        tasks = sorted(candidates)
        rnd.shuffle(tasks)
        counts = initial.copy()
        chosen = []
        for task in tasks:
            options = [pair for pair in candidates[task]
                       if counts[pair.model_a] < cap and counts[pair.model_b] < cap]
            if not options:
                continue
            options.sort(key=lambda pair: (max(counts[pair.model_a], counts[pair.model_b]),
                                           counts[pair.model_a] + counts[pair.model_b], rnd.random()))
            pair = options[0]
            chosen.append(pair)
            counts.update((pair.model_a, pair.model_b))
        if len(chosen) > len(best):
            best = chosen
    return best


def select_pairs(responses: Sequence[Response], eligible_ids: Sequence[str], *,
                 max_diff: float = 10.0, min_score: float = 30.0, cap_per_model: int = 15,
                 reserve_cap: int = 20, seed: int = 20261024, iterations: int = 50,
                 exclude_named: bool = True) -> list[Pair]:
    """Bilancia le principali e poi la riserva continuando i conteggi dei modelli."""
    if iterations < 1 or cap_per_model < 1 or reserve_cap < cap_per_model or max_diff <= 0:
        raise WebTaskError("parametri di bilanciamento non validi")
    usable, _ = usable_responses(responses, eligible_ids, exclude_named=exclude_named)
    by_task: dict[str, list[Response]] = defaultdict(list)
    for response in usable:
        by_task[response.task_id].append(response)
    candidates: dict[str, list[Pair]] = {}
    for task in sorted(by_task):
        options = []
        for a, b in itertools.combinations(sorted(by_task[task], key=lambda row: row.model), 2):
            if (a.model != b.model and a.score is not None and b.score is not None
                    and min(a.score, b.score) >= min_score and 0 < abs(a.score - b.score) <= max_diff):
                options.append(Pair("", task, a.model, b.model, a.score, b.score))
        if options:
            candidates[task] = options
    main = _balance(candidates, cap_per_model, seed, iterations, Counter())
    used = {pair.task_id for pair in main}
    counts = Counter(model for pair in main for model in (pair.model_a, pair.model_b))
    reserve = _balance({task: options for task, options in candidates.items() if task not in used},
                       reserve_cap, seed, iterations, counts)[:26]
    return [replace(pair, pair_id=f"c{number:03d}")
            for number, pair in enumerate(main + reserve, 1)]


def save_pairs(path: Path, pairs: Sequence[Pair], *, params: dict[str, Any],
               main_count: int = 150) -> None:
    """Salva coppie e parametri senza contenuti delle pagine."""
    if "seed" not in params or main_count < 0:
        raise WebTaskError("seme mancante o numero di principali non valido")
    _write_json(path, {"commit": RESPONSES_COMMIT, "seed": params["seed"], "params": params,
                       "main": [asdict(pair) for pair in pairs[:main_count]],
                       "reserve": [asdict(pair) for pair in pairs[main_count:]], "created": _now()})


def load_pairs(path: Path) -> tuple[list[Pair], list[Pair]]:
    """Rilegge principali e riserva, controllando identificativi e orientamento."""
    try:
        data = _read_json(path)
        main = [Pair(**row) for row in data["main"]]
        reserve = [Pair(**row) for row in data["reserve"]]
        ids = [pair.pair_id for pair in main + reserve]
        if len(set(ids)) != len(ids) or any(pair.model_a >= pair.model_b for pair in main + reserve):
            raise WebTaskError(f"{path}: coppie duplicate o orientamento non valido")
        return main, reserve
    except (KeyError, TypeError, ValueError) as error:
        raise WebTaskError(f"{path}: formato delle coppie non valido: {error}") from error


def _page_dir(out_root: Path, task_id: str, model: str) -> Path:
    for component in (task_id, model):
        if not isinstance(component, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", component):
            raise WebTaskError("identificativo di pagina non valido")
    return out_root / f"{task_id}-{model}"


def _read_outcome(page: Path) -> dict[str, Any]:
    data = _read_json(page / "esito.json")
    if (not isinstance(data, dict) or not isinstance(data.get("started"), bool)
            or not isinstance(data.get("failed"), bool) or not isinstance(data.get("widths"), dict)):
        raise WebTaskError(f"{page}: esito non valido")
    return data


def _screenshots(page: Path, outcome: dict[str, Any]) -> dict[str, Path]:
    images = {}
    for width in WIDTHS:
        row = outcome["widths"].get(str(width))
        name = row.get("screenshot") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name:
            raise WebTaskError(f"{page}: screenshot {width} mancante")
        path = page / name
        if not path.resolve().is_relative_to(page.resolve()) or not path.is_file():
            raise WebTaskError(f"{page}: screenshot {width} mancante o percorso non valido")
        images[str(width)] = path
    return images


def render_pairs(pairs: Sequence[Pair], responses: Sequence[Response], out_root: Path, *,
                 render: Callable[[Path, Path], RenderResult] = render_site,
                 workers: int = 3) -> RenderSummary:
    """Renderizza ogni pagina una volta; riprova i guasti una volta e poi alla ripresa."""
    if workers < 1:
        raise WebTaskError("workers deve essere almeno 1")
    keys = sorted({(pair.task_id, model) for pair in pairs for model in (pair.model_a, pair.model_b)})
    by_key = {(row.task_id, row.model): row for row in responses}
    jobs: list[tuple[str, str, str]] = []
    skipped = 0
    not_started: list[str] = []
    for task, model in keys:
        page = _page_dir(out_root, task, model)
        if (page / "esito.json").exists():
            previous = _read_outcome(page)
            if previous["failed"] is False:
                skipped += 1
                if not previous["started"]:
                    not_started.append(page.name)
                continue
        response = by_key.get((task, model))
        html = extract_html(response.text) if response is not None else None
        if html is None or not is_valid_page(html):
            raise WebTaskError(f"{page.name}: risposta HTML valida mancante")
        jobs.append((task, model, html))

    def work(job: tuple[str, str, str]) -> dict[str, Any]:
        task, model, html = job
        page = _page_dir(out_root, task, model)
        site, shots = page / "site", page / "shots"
        try:
            site.mkdir(parents=True, exist_ok=True)
            (site / "index.html").write_text(html, encoding="utf-8")
            (site / "start.sh").write_text(
                "exec python3 -m http.server 8080 --bind 0.0.0.0\n", encoding="utf-8")
            outcome: dict[str, Any] = {"task_id": task, "model": model, "started": False,
                                       "start_error": None, "failed": True, "error": None, "widths": {}}
            for attempt in range(2):
                try:
                    result = render(site, shots)
                except RenderError as error:
                    outcome["error"] = str(error)
                    if attempt == 0:
                        continue
                else:
                    outcome.update(started=result.started, start_error=result.start_error,
                                   failed=False, error=None)
                    outcome["widths"] = {
                        str(width): {"errors": row.errors,
                                     "screenshot": str(row.screenshot.resolve().relative_to(page.resolve()))
                                     if row.screenshot is not None else None}
                        for width, row in result.widths.items()}
                break
            _write_json(page / "esito.json", outcome)
            return outcome
        except (OSError, ValueError) as error:
            raise WebTaskError(f"{page}: rendering non registrato: {error}") from error

    outcomes = run_parallel(jobs, work, max_workers=workers)
    failed = []
    for outcome in outcomes:
        if outcome.error is not None:
            if isinstance(outcome.error, WebTaskError):
                raise outcome.error
            raise WebTaskError(f"rendering non riuscito: {outcome.error}") from outcome.error
        if outcome.result is not None:
            name = f"{outcome.job[0]}-{outcome.job[1]}"
            if outcome.result["failed"]:
                failed.append(name)
            elif not outcome.result["started"]:
                not_started.append(name)
    return RenderSummary(len(jobs), skipped, failed, sorted(not_started))


def _pair_problem(pair: Pair, out_root: Path) -> str | None:
    problems = []
    for model in (pair.model_a, pair.model_b):
        page = _page_dir(out_root, pair.task_id, model)
        outcome = _read_outcome(page)
        if outcome["failed"]:
            problems.append(f"{page.name} guasta: {outcome.get('error')}")
        elif not outcome["started"]:
            problems.append(f"{page.name} non partita")
        else:
            try:
                _screenshots(page, outcome)
            except WebTaskError as error:
                problems.append(str(error))
    return "; ".join(problems) if problems else None


def final_pairs(pairs_file: Path, out_root: Path, *, count: int = 150) -> tuple[list[Pair], list[str]]:
    """Conserva le principali usabili e aggiunge in coda i sostituti dalla riserva."""
    if count < 1:
        raise WebTaskError("il numero di coppie finali deve essere positivo")
    main, reserve = load_pairs(pairs_file)
    chosen = []
    notes = []
    removed_notes = []
    for pair in main:
        problem = _pair_problem(pair, out_root)
        if problem:
            removed_notes.append(len(notes))
            notes.append(f"{pair.pair_id} tolta: {problem}")
        else:
            chosen.append(pair)
    for pair in reserve:
        if len(chosen) >= count:
            break
        problem = _pair_problem(pair, out_root)
        if problem:
            notes.append(f"{pair.pair_id} riserva saltata: {problem}")
        else:
            chosen.append(pair)
            if removed_notes:
                note_index = removed_notes.pop(0)
                notes[note_index] += f"; sostituita da {pair.pair_id}"
            else:
                notes.append(f"{pair.pair_id} aggiunta dalla riserva")
    if len(chosen) < count:
        raise WebTaskError(f"coppie usabili insufficienti: {len(chosen)} su {count} richieste")
    return chosen[:count], notes


def build_vote_package(pairs: Sequence[Pair], tasks_text: dict[str, str], out_root: Path,
                       dest: Path, key_file: Path, *, seed: int = 20261024, repeats: int = 5,
                       pause_every: int = 20) -> Path:
    """Prepara dati e immagini anonimi; la chiave resta fuori dalla cartella pubblica."""
    if dest.exists() or key_file.exists():
        raise WebTaskError("il pacchetto o la chiave esistono gia': non si sovrascrivono")
    if key_file.resolve().is_relative_to(dest.resolve()):
        raise WebTaskError("la chiave deve restare fuori dal pacchetto")
    if not pairs or repeats < 0 or repeats > len(pairs) or pause_every < 1:
        raise WebTaskError("numero di coppie, ripetizioni o intervallo di pausa non valido")
    if repeats and len(pairs) < 20:
        raise WebTaskError("servono almeno 20 coppie per distanziare le ripetizioni")
    forbidden = {model for pair in pairs for model in (pair.model_a, pair.model_b)}
    forbidden.update(pair.pair_id for pair in pairs)
    if len({pair.pair_id for pair in pairs}) != len(pairs):
        raise WebTaskError("identificativi di coppia duplicati")
    screenshots: dict[tuple[str, str], dict[str, Path]] = {}
    for pair in pairs:
        task = tasks_text.get(pair.task_id)
        if not isinstance(task, str):
            raise WebTaskError(f"testo del compito {pair.task_id} mancante")
        if any(re.search(rf"\b{re.escape(name)}\b", task, re.I) for name in forbidden):
            raise WebTaskError(f"il compito {pair.task_id} contiene un indizio sul modello o sulla coppia")
        for model in (pair.model_a, pair.model_b):
            page = _page_dir(out_root, pair.task_id, model)
            outcome = _read_outcome(page)
            if outcome["failed"] or not outcome["started"]:
                raise WebTaskError(f"{page.name}: pagina non usabile")
            screenshots[(pair.task_id, model)] = _screenshots(page, outcome)
    rnd = random.Random(seed)
    shuffled = list(pairs)
    rnd.shuffle(shuffled)
    # L'indice originale collega ogni ripetizione senza esporre identificativi interni.
    entries: list[tuple[Pair, str, int | None]] = [
        (pair, rnd.choice((pair.model_a, pair.model_b)), None) for pair in shuffled]
    if repeats and repeats > len(entries) - 19:
        raise WebTaskError("troppe ripetizioni per garantire il distacco di 20 posizioni")
    originals = rnd.sample(shuffled[:len(entries) - 19], repeats)
    for pair in originals:
        position = next(i for i, entry in enumerate(entries) if entry[0] == pair and entry[2] is None)
        left = entries[position][1]
        right = pair.model_b if left == pair.model_a else pair.model_a
        insertion = rnd.randint(position + 20, len(entries))
        entries.insert(insertion, (pair, right, shuffled.index(pair)))
    original_items = {pair.pair_id: f"v{index:03d}" for index, (pair, _, repeat) in enumerate(entries, 1)
                      if repeat is None}
    public_items: list[dict[str, Any]] = []
    key_items = []
    copies: list[tuple[Path, str]] = []
    for index, (pair, left, repeat) in enumerate(entries, 1):
        item = f"v{index:03d}"
        right = pair.model_b if left == pair.model_a else pair.model_a
        images = {}
        for side, model in (("s", left), ("d", right)):
            images[side] = {}
            for width in WIDTHS:
                name = f"img/{item}-{side}-{width}.png"
                images[side][str(width)] = name
                copies.append((screenshots[(pair.task_id, model)][str(width)], name))
        public_items.append({"item": item, "task": tasks_text[pair.task_id], "images": images})
        key_items.append({"item": item, "pair_id": pair.pair_id, "left_model": left, "right_model": right,
                          "repeat_of": original_items[pair.pair_id] if repeat is not None else None})
    data = ("window.COPPIE = " + json.dumps(public_items, ensure_ascii=False) + ";\n"
            + f"window.PAUSA = {pause_every};\n")
    package_id = hashlib.sha256(data.encode("utf-8")).hexdigest()
    index_html = _VOTE_HTML.replace("__PACKAGE_ID__", package_id)
    if any(re.search(rf"\b{re.escape(name)}\b", index_html, re.I) for name in forbidden):
        raise WebTaskError("un identificativo coincide con il testo dell'interfaccia")
    temporary: Path | None = None
    key_temporary: Path | None = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".vote-package-", dir=dest.parent))
        (temporary / "img").mkdir()
        for source, name in copies:
            shutil.copyfile(source, temporary / name)
        (temporary / "coppie.js").write_text(data, encoding="utf-8")
        (temporary / "index.html").write_text(index_html, encoding="utf-8")
        with tempfile.NamedTemporaryFile(dir=key_file.parent, prefix=".vote-key-", delete=False) as stream:
            key_temporary = Path(stream.name)
        _write_json(key_temporary, {"package_id": package_id, "seed": seed, "items": key_items})
        temporary.rename(dest)
        try:
            key_temporary.replace(key_file)
        except OSError:
            shutil.rmtree(dest)
            raise
    except OSError as error:
        raise WebTaskError(f"creazione del pacchetto non riuscita: {error}") from error
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        if key_temporary is not None:
            key_temporary.unlink(missing_ok=True)
    return dest / "index.html"


def load_votes(votes_file: Path, key_file: Path, package_dir: Path) -> list[Vote]:
    """Controlla pacchetto, voci e valori e riporta il segno all'ordine della coppia."""
    data, key = _read_json(votes_file), _read_json(key_file)
    try:
        digest = _sha256(package_dir / "coppie.js")
        if key["package_id"] != digest or data["package_id"] != digest:
            raise WebTaskError("package_id diverso dalla chiave o dal pacchetto")
        voter = data["voter"]
        if not isinstance(voter, str) or not voter.strip() or not isinstance(data["votes"], list):
            raise WebTaskError("codice del votante o elenco dei voti non valido")
        by_item = {item["item"]: item for item in key["items"]}
        seen = set()
        votes = []
        for row in data["votes"]:
            item = row["item"]
            if item not in by_item or item in seen:
                raise WebTaskError(f"voce sconosciuta o doppia: {item}")
            seen.add(item)
            value, ms = row["value"], row["ms"]
            if type(value) is not int or value not in range(-2, 3):
                raise WebTaskError(f"voto fuori scala per {item}")
            if type(ms) is not int or ms < 0:
                raise WebTaskError(f"tempo del voto non valido per {item}")
            entry = by_item[item]
            sign = 1 if entry["right_model"] > entry["left_model"] else -1
            votes.append(Vote(voter, entry["pair_id"], value * sign, entry["repeat_of"] is not None, ms))
        return votes
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise WebTaskError(f"{votes_file}: formato dei voti non valido: {error}") from error


_VOTE_HTML = r'''<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Confronto di siti</title>
<style>
*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;background:#f3f5f8;color:#172233}
header{position:sticky;top:0;z-index:2;display:flex;gap:18px;align-items:center;padding:12px 24px;background:#fff;border-bottom:1px solid #ccd3df}
header strong{margin-right:auto}button,input{font:inherit;padding:10px 16px;border:1px solid #8b98ab;border-radius:6px;background:white;color:inherit;cursor:pointer}
button:focus-visible,input:focus-visible{outline:3px solid #225bd6;outline-offset:2px}button:disabled{opacity:.45;cursor:default}
main{max-width:1366px;margin:auto;padding:16px 24px 120px}details{padding:12px;background:white;border-radius:8px;margin-bottom:12px}summary{cursor:pointer;font-weight:600}
#task{white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow:auto;line-height:1.5}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}.site{min-width:0}h2{font-size:20px;margin:12px 0}
.tabs{display:flex;gap:8px;margin-bottom:10px}.tabs button[aria-pressed="true"]{background:#174dbc;color:white}
.frame{height:58vh;overflow:auto;background:#e2e6ec;border:1px solid #ccd3df;border-radius:6px}.frame img{display:block;width:100%;height:auto;cursor:zoom-in}
#rating{display:flex;gap:8px;justify-content:center;position:fixed;bottom:0;left:0;right:0;padding:16px;background:white;border-top:1px solid #ccd3df}
#rating button[aria-pressed="true"]{background:#174dbc;color:white}.center{max-width:600px;margin:60px auto;background:white;padding:30px;border-radius:12px}
#zoom{border:0;padding:20px;max-width:98vw;max-height:98vh}#zoom::backdrop{background:#000b}#zoom img{display:block;max-width:none;cursor:zoom-out}#zoom button{position:sticky;top:0}
[hidden]{display:none!important}#status{font-size:14px;color:#49576b}label{display:block;margin-bottom:12px}
</style></head><body>
<header><strong>Confronto di siti</strong><span id="progress">0 / 0</span><span id="status" role="status"></span>
<button id="back" disabled>Indietro</button><button id="export" disabled>Esporta i voti</button></header>
<main>
<form id="login" class="center"><h1>Il tuo codice anonimo</h1>
<p>Usa un codice, per esempio v3. Conserva lo stesso codice per riprendere i voti.</p>
<label>Codice anonimo <input id="code" required maxlength="64" autocomplete="off" pattern="[A-Za-z0-9_-]+"></label>
<button>Inizia o riprendi</button><p id="login-error" role="alert"></p></form>
<section id="comparison" hidden><details><summary>Testo del compito</summary><p id="task"></p></details>
<div class="columns"><section class="site"><h2>Sito A</h2><div class="tabs" data-side="s"></div>
<div class="frame"><img id="left" alt="Screenshot del sito A" tabindex="0"></div></section>
<section class="site"><h2>Sito B</h2><div class="tabs" data-side="d"></div>
<div class="frame"><img id="right" alt="Screenshot del sito B" tabindex="0"></div></section></div></section>
<section id="pause" class="center" hidden><h1>Pausa</h1><p>Puoi riposare ed esportare i voti gia' raccolti.</p><button id="continue">Continua</button></section>
<section id="done" class="center" hidden><h1>Voti completati</h1><p>Esporta il file dei voti con il pulsante in alto.</p></section>
</main><nav id="rating" aria-label="Preferenza" hidden></nav>
<dialog id="zoom"><button id="close-zoom">Chiudi</button><img alt="Screenshot ingrandito"></dialog>
<script src="coppie.js"></script>
<script>
"use strict";
const packageId = "__PACKAGE_ID__";
const items = window.COPPIE;
const el = id => document.getElementById(id);
let voter = "", votes = [], cursor = 0, width = "1440", paused = false, started = 0;
let storageWorks = true;
const storageKey = () => "voti-" + packageId + "-" + voter;
function save() {
  try { localStorage.setItem(storageKey(), JSON.stringify({votes, cursor, paused})); }
  catch (error) { storageWorks = false; }
  el("status").textContent = storageWorks ? "Salvataggio locale" : "Salvataggio locale non disponibile: esporta i voti";
}
function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey()) || "null");
    if (!saved) return;
    if (!Array.isArray(saved.votes) || saved.votes.length > items.length) throw Error("voti non validi");
    saved.votes.forEach((vote, index) => {
      if (vote.item !== items[index].item || !Number.isInteger(vote.value) || vote.value < -2 || vote.value > 2 || !Number.isInteger(vote.ms) || vote.ms < 0 || typeof vote.ts !== "string") throw Error("voto non valido");
    });
    votes = saved.votes;
    cursor = Number.isInteger(saved.cursor) ? Math.max(0, Math.min(saved.cursor, votes.length)) : votes.length;
    paused = Boolean(saved.paused) && cursor === votes.length && cursor < items.length;
  } catch (error) { storageWorks = false; }
}
function show() {
  const complete = cursor >= items.length;
  el("login").hidden = true;
  el("comparison").hidden = paused || complete;
  el("rating").hidden = paused || complete;
  el("pause").hidden = !paused;
  el("done").hidden = !complete;
  el("back").disabled = cursor === 0;
  el("export").disabled = !voter;
  el("progress").textContent = Math.min(cursor + 1, items.length) + " / " + items.length;
  if (!paused && !complete) {
    const item = items[cursor];
    el("task").textContent = item.task;
    el("left").src = item.images.s[width];
    el("right").src = item.images.d[width];
    document.querySelectorAll(".tabs button").forEach(button => button.setAttribute("aria-pressed", String(button.textContent === width)));
    document.querySelectorAll("#rating button").forEach(button => button.setAttribute("aria-pressed", String(votes[cursor]?.value === Number(button.dataset.value))));
  }
  started = performance.now();
  save();
}
["s", "d"].forEach(side => {
  const tabs = document.querySelector('.tabs[data-side="' + side + '"]');
  ["1440", "768", "375"].forEach(size => {
    const button = document.createElement("button");
    button.textContent = size;
    button.onclick = () => {
      width = size;
      el("left").src = items[cursor].images.s[width];
      el("right").src = items[cursor].images.d[width];
      document.querySelectorAll(".tabs button").forEach(tab => tab.setAttribute("aria-pressed", String(tab.textContent === width)));
    };
    tabs.append(button);
  });
});
function rate(value) {
  if (!voter || paused || cursor >= items.length || el("zoom").open) return;
  const vote = {item: items[cursor].item, value, ms: Math.max(0, Math.round(performance.now() - started)), ts: new Date().toISOString()};
  votes = votes.slice(0, cursor);
  votes.push(vote);
  cursor += 1;
  paused = cursor < items.length && cursor % window.PAUSA === 0;
  show();
}
["A molto meglio", "A meglio", "Pari", "B meglio", "B molto meglio"].forEach((label, index) => {
  const button = document.createElement("button");
  button.textContent = (index + 1) + " · " + label;
  button.dataset.value = String(index - 2);
  button.onclick = () => rate(index - 2);
  el("rating").append(button);
});
el("login").onsubmit = event => {
  event.preventDefault();
  const code = el("code").value.trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(code)) {
    el("login-error").textContent = "Usa solo lettere, numeri, trattino o trattino basso.";
    return;
  }
  voter = code;
  restore();
  show();
};
el("back").onclick = () => { if (cursor > 0) { cursor -= 1; paused = false; show(); } };
el("continue").onclick = () => { paused = false; show(); };
el("export").onclick = () => {
  const data = {voter, package_id: packageId, created: new Date().toISOString(), votes};
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = "voti-" + voter + ".json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
function openZoom(source) {
  el("zoom").querySelector("img").src = source.src;
  el("zoom").showModal();
}
[el("left"), el("right")].forEach(img => {
  img.onclick = () => openZoom(img);
  img.onkeydown = event => { if (event.key === "Enter") openZoom(img); };
});
el("close-zoom").onclick = () => el("zoom").close();
el("zoom").querySelector("img").onclick = () => el("zoom").close();
document.addEventListener("keydown", event => {
  if (!voter || event.target instanceof HTMLInputElement || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
  if (/^[1-5]$/.test(event.key)) { event.preventDefault(); rate(Number(event.key) - 3); }
});
el("progress").textContent = "0 / " + items.length;
</script></body></html>
'''
