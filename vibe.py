"""Prova del giudice sui voti pubblici di Vibe Design Arena (R1.12, PROTOCOLLO.md §6).

Il giudice e' quello di R1.9, invariato: stesso modello, schema, tentativi e
lettura del voto. Cambiano solo il prompt (nessun compito, la domanda posta ai
votanti del dataset) e le immagini: uno screenshot 1440x900 per sito.
"""

import json
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agreement import DELTA_MARGIN, _percentile
from judge import PROMPT_DIR, VOTE_SCHEMA, JudgeError, Judgment, Runner, _attempts, load_judgments, parse_vote

VIBE_PAIRS = 150
VIBE_SEED = 20261029
ACCURACY_FLOOR = 0.5


@dataclass(frozen=True)
class VibePair:
    """Una coppia del dataset con i totali dei voti umani."""

    app_a: str
    app_b: str
    votes_a: int
    votes_b: int

    @property
    def item(self) -> str:
        return f"{self.app_a}|{self.app_b}"


def load_pairs(path: Path) -> list[VibePair]:
    """Legge `coppie.json` controllando nomi, voti e coppie doppie."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise JudgeError(f"{path}: serve un elenco di coppie")
        pairs = []
        seen = set()
        for row in rows:
            pair = VibePair(row["app_a"], row["app_b"], row["votes_a"], row["votes_b"])
            if (not all(isinstance(name, str) and name for name in (pair.app_a, pair.app_b))
                    or pair.app_a == pair.app_b
                    or not all(type(votes) is int and votes >= 0 for votes in (pair.votes_a, pair.votes_b))
                    or pair.votes_a + pair.votes_b == 0):
                raise JudgeError(f"{path}: coppia non valida: {row}")
            winner = row.get("winner")
            if winner is not None and pair.votes_a != pair.votes_b and winner != (
                    "app_a" if pair.votes_a > pair.votes_b else "app_b"):
                raise JudgeError(f"{path}: vincitore incoerente con i voti: {pair.item}")
            key = frozenset((pair.app_a, pair.app_b))
            if key in seen:
                raise JudgeError(f"{path}: coppia doppia: {pair.item}")
            seen.add(key)
            pairs.append(pair)
        return pairs
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise JudgeError(f"{path}: formato delle coppie non valido: {error}") from error


def sample_pairs(pairs: Sequence[VibePair], n: int = VIBE_PAIRS, seed: int = VIBE_SEED) -> list[VibePair]:
    """Estrae n coppie senza parita'; l'ordine del file non cambia l'estrazione."""
    eligible = sorted((pair for pair in pairs if pair.votes_a != pair.votes_b), key=lambda pair: pair.item)
    if len(eligible) < n:
        raise JudgeError(f"servono {n} coppie senza parita', disponibili {len(eligible)}")
    return random.Random(seed).sample(eligible, n)


def freeze_selection(pairs: Sequence[VibePair], path: Path, *, create: bool = True) -> None:
    """Scrive l'elenco estratto la prima volta; dopo, l'estrazione deve coincidere."""
    items = [pair.item for pair in pairs]
    try:
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != items:
                raise JudgeError(f"{path}: l'estrazione non coincide con l'elenco registrato")
            return
        if not create:
            raise JudgeError(f"{path}: elenco delle coppie estratte mancante")
        path.write_text(json.dumps(items, indent=1) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        raise JudgeError(f"{path}: elenco delle coppie estratte non leggibile: {error}") from error


def check_screenshots(pairs: Sequence[VibePair], screenshot_dir: Path) -> dict[str, Path]:
    """Controlla tutte le immagini prima di spendere una chiamata."""
    images = {}
    for pair in pairs:
        for app in (pair.app_a, pair.app_b):
            path = screenshot_dir / f"{app}.png"
            if not path.is_file():
                raise JudgeError(f"{pair.item}: screenshot mancante: {path}")
            images[app] = path
    return images


def vote_prompt() -> str:
    """Legge il prompt del voto: qui non ci sono segnaposti da compilare."""
    try:
        prompt = (PROMPT_DIR / "voto_vibe.txt").read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise JudgeError(f"voto_vibe.txt: lettura del prompt non riuscita: {error}") from error
    if "<<" in prompt:
        raise JudgeError("voto_vibe.txt: segnaposto non risolto nel prompt")
    return prompt


def judge_vibe(pairs: Sequence[VibePair], screenshot_dir: Path, out_file: Path, *,
               runner: Runner, meta: dict[str, Any], limit: int | None = None) -> list[Judgment]:
    """Vota le prime `limit` coppie nei due ordini e salva subito; riprende solo con metadati identici."""
    if limit is not None and limit < 1:
        raise JudgeError("il limite deve essere almeno 1")
    prompt = vote_prompt()
    images = check_screenshots(pairs, screenshot_dir)
    existing = {row.item: row for row in load_judgments(out_file)} if out_file.exists() else {}
    items = {pair.item for pair in pairs}
    for item, judgment in existing.items():
        if judgment.meta != meta:
            raise JudgeError(f"{out_file}: metadati diversi per il giudizio {item}")
        if item not in items:
            raise JudgeError(f"{out_file}: giudizio non appartenente alle coppie estratte: {item}")
    try:
        json.dumps(meta, allow_nan=False)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        judgments = []
        with out_file.open("a", encoding="utf-8") as stream:
            # La ripresa si confronta con tutte le coppie estratte, il limite sceglie solo quali giudicare.
            for pair in pairs[:limit]:
                if pair.item in existing:
                    judgments.append(existing[pair.item])
                    continue
                first, second = images[pair.app_a], images[pair.app_b]
                forward, forward_attempts, forward_out = _attempts(prompt, [first, second], VOTE_SCHEMA,
                                                                   parse_vote, runner)
                backward, backward_attempts, backward_out = _attempts(prompt, [second, first], VOTE_SCHEMA,
                                                                      parse_vote, runner)
                outputs = forward_out + backward_out
                usage: dict[str, int] = {}
                for output in outputs:
                    for name, count in output.usage.items():
                        usage[name] = usage.get(name, 0) + count
                # Positivo = preferisce app_b, come nel giudice di R1.9 (lato destro).
                value = (forward - backward) / 2 if forward is not None and backward is not None else None
                judgment = Judgment(
                    item=pair.item, pair_id=pair.item, value=value, forward=forward, backward=backward,
                    attempts=forward_attempts + backward_attempts,
                    seconds=sum(output.seconds for output in outputs), usage=usage,
                    date=datetime.now(timezone.utc).isoformat(), meta=meta,
                    timeouts=sum(output.timed_out for output in outputs),
                )
                stream.write(json.dumps(asdict(judgment), ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                judgments.append(judgment)
        return judgments
    except (OSError, ValueError, TypeError) as error:
        raise JudgeError(f"{out_file}: elaborazione dei giudizi non riuscita: {error}") from error


def accept_vibe(accuracy_low: float, delta_low: float) -> bool:
    """Applica le due soglie strette preregistrate, ai limiti inferiori."""
    return accuracy_low > ACCURACY_FLOOR and delta_low > DELTA_MARGIN


def _interval(values: list[float], point: float) -> dict[str, float | None]:
    values.sort()
    return {"low": _percentile(values, 0.025), "point": point, "high": _percentile(values, 0.975)}


def vibe_report(pairs: Sequence[VibePair], judgments: Sequence[Judgment], *,
                samples: int, seed: int) -> dict[str, Any]:
    """Accordo con la maggioranza, riferimento m/n e Δ, con bootstrap sullo stesso ripescaggio."""
    by_item: dict[str, Judgment] = {}
    for judgment in judgments:
        if judgment.item in by_item:
            raise JudgeError(f"giudizio duplicato sulla coppia {judgment.item}")
        by_item[judgment.item] = judgment
    if set(by_item) != {pair.item for pair in pairs} or len(pairs) != len(by_item):
        raise JudgeError("coppie estratte e giudicate diverse: lotto incompleto")
    if not pairs:
        raise JudgeError("nessuna coppia da valutare")
    if samples < 1:
        raise JudgeError("serve almeno un ripescaggio")
    agree: list[float] = []
    reference: list[float] = []
    for pair in pairs:
        value = by_item[pair.item].value
        # Pareggio del giudice e non valutabile contano come disaccordo.
        agree.append(float(value is not None and value != 0 and (value > 0) == (pair.votes_b > pair.votes_a)))
        reference.append(max(pair.votes_a, pair.votes_b) / (pair.votes_a + pair.votes_b))
    n = len(pairs)
    rng = random.Random(seed)
    boot_acc, boot_ref, boot_delta = [], [], []
    for _ in range(samples):
        picks = [rng.randrange(n) for _ in range(n)]
        accuracy = sum(agree[i] for i in picks) / n
        ref = sum(reference[i] for i in picks) / n
        boot_acc.append(accuracy)
        boot_ref.append(ref)
        boot_delta.append(accuracy - ref)
    accuracy_point, reference_point = sum(agree) / n, sum(reference) / n
    report: dict[str, Any] = {
        "pairs": n,
        "accuracy": _interval(boot_acc, accuracy_point),
        "reference": _interval(boot_ref, reference_point),
        "delta": _interval(boot_delta, accuracy_point - reference_point),
        "judge_ties": sum(by_item[pair.item].value == 0 for pair in pairs),
        "unratable": sum(by_item[pair.item].value is None for pair in pairs),
        "samples": samples,
        "seed": seed,
    }
    report["accepted"] = accept_vibe(report["accuracy"]["low"], report["delta"]["low"])
    return report
