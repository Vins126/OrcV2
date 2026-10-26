"""Accordi di R1.10 secondo la regola fissata in PROTOCOLLO, sezione 6."""

import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any, TypeVar

from calibration import Vote
from judge import Judgment
from task_model import CampaignError

DELTA_MARGIN = -0.10
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20261025

Measure = Callable[[Sequence[float], Sequence[float]], float]
Rating = TypeVar("Rating", bound=float)
METRICS = ("pi_hh", "pi_jh", "delta", "acc_hh", "acc_jh",
           "acc_hh_no_ties", "acc_jh_no_ties", "alpha_hh", "alpha_jh")


class AgreementError(CampaignError):
    """Dati degli accordi non validi o misura indefinita."""


def sign(x: float) -> int:
    """Riporta anche i mezzi punti alle tre categorie del protocollo."""
    return int(x > 0) - int(x < 0)


def _validate_lists(a: Sequence[Any], b: Sequence[Any]) -> None:
    if not a or len(a) != len(b):
        raise AgreementError("servono due liste non vuote della stessa lunghezza")
    if any(x is None or (isinstance(x, float) and not math.isfinite(x)) for x in (*a, *b)):
        raise AgreementError("valori mancanti o non finiti")


def scott_pi(a: Sequence[float], b: Sequence[float]) -> float:
    """Scott pi sui segni: usa le frequenze dei due votanti insieme."""
    _validate_lists(a, b)
    if any(x not in (-1, 0, 1) for x in (*a, *b)):
        raise AgreementError("Scott pi richiede categorie -1, 0, +1")
    counts = Counter((*a, *b))
    pe = sum((count / (2 * len(a))) ** 2 for count in counts.values())
    if pe == 1:
        raise AgreementError("Scott pi indefinito: pe uguale a 1")
    return (percent_agreement(a, b) - pe) / (1 - pe)


def percent_agreement(a: Sequence[float], b: Sequence[float]) -> float:
    """Quota di voci con lo stesso valore."""
    _validate_lists(a, b)
    return sum(x == y for x, y in zip(a, b)) / len(a)


def _alpha_counts(marginals: Sequence[int], cells: Sequence[tuple[int, int, int]]) -> float:
    """Alfa dalla matrice delle coincidenze, memorizzata per celle non ordinate.

    Ogni coppia contribuisce due coincidenze, anche sulla diagonale. I centri
    cumulativi sono raddoppiati: la loro distanza al quadrato e' quattro volte
    delta^2 ordinale. Il fattore quattro si cancella fra Do e De. Per De si
    usa l'identita' della somma delle distanze quadratiche pesate.
    """
    total = sum(marginals)
    prefix = 0
    centers = []
    for count in marginals:
        centers.append(2 * prefix + count)
        prefix += count
    expected = (total * sum(count * center * center for count, center in zip(marginals, centers))
                - sum(count * center for count, center in zip(marginals, centers)) ** 2)
    if expected == 0:
        raise AgreementError("alfa ordinale indefinito: De uguale a zero")
    observed = sum(count * (centers[left] - centers[right]) ** 2 for left, right, count in cells)
    return 1 - (total - 1) * observed / expected


def krippendorff_alpha_ordinal(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Alfa ordinale di Krippendorff (2011) per due votanti, senza valori mancanti."""
    _validate_lists(a, b)
    try:
        categories = sorted(set((*a, *b)))
        indices = {value: i for i, value in enumerate(categories)}
        counts = Counter((indices[x], indices[y]) for x, y in zip(a, b))
    except (TypeError, ValueError) as error:
        raise AgreementError("categorie non ordinabili o non valide") from error
    marginals = [0] * len(categories)
    for (left, right), count in counts.items():
        marginals[left] += count
        marginals[right] += count
    return _alpha_counts(marginals, [(left, right, count) for (left, right), count in counts.items()])


def ratings_from(votes: Sequence[Vote], judgments: Sequence[Judgment]
                 ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Esclude ripetizioni e non valutabili, controllando duplicati e lotti incompleti."""
    humans: dict[str, dict[str, float]] = {}
    for vote in votes:
        if vote.repeat:
            continue
        values = humans.setdefault(vote.voter, {})
        if vote.pair_id in values:
            raise AgreementError(f"due primi voti di {vote.voter} sulla coppia {vote.pair_id}")
        if not math.isfinite(vote.value):
            raise AgreementError("voto umano non finito")
        values[vote.pair_id] = float(vote.value)
    by_pair: dict[str, float | None] = {}
    for judgment in judgments:
        if judgment.pair_id in by_pair:
            raise AgreementError(f"giudizio duplicato sulla coppia {judgment.pair_id}")
        if judgment.value is not None and not math.isfinite(judgment.value):
            raise AgreementError("voto del giudice non finito")
        by_pair[judgment.pair_id] = judgment.value
    voted = {pair for values in humans.values() for pair in values}
    if voted != set(by_pair):
        raise AgreementError("coppie votate e giudicate diverse: lotto incompleto")
    judge = {pair: float(value) for pair, value in by_pair.items() if value is not None}
    return {voter: {pair: value for pair, value in values.items() if pair in judge}
            for voter, values in humans.items()}, judge


def pairwise_mean(ratings: dict[str, dict[str, Rating]], measure: Measure, *, items: Sequence[str]) -> float:
    """Media fra coppie di votanti sulle voci comuni, rispettando ordine e ripescaggi."""
    results = []
    for a, b in combinations(ratings.values(), 2):
        common = [item for item in items if item in a and item in b]
        if not common:
            continue
        try:
            results.append(measure([a[item] for item in common], [b[item] for item in common]))
        except AgreementError:
            continue
    if not results:
        raise AgreementError("nessuna coppia di votanti con misura definita")
    return sum(results) / len(results)


def accept(hh_low: float, jh_low: float, delta_low: float) -> bool:
    """Applica le tre soglie strette preregistrate, ai limiti inferiori."""
    return hh_low > 0 and jh_low > 0 and delta_low > DELTA_MARGIN


@dataclass(frozen=True)
class _PairCounts:
    """Indici comuni raggruppati per voti: si costruiscono una sola volta."""

    categories: int
    groups: tuple[tuple[int, int, int, int, tuple[int, ...]], ...]

    @classmethod
    def build(cls, a: dict[str, float], b: dict[str, float], items: Sequence[str]) -> "_PairCounts":
        categories = sorted(set(a.values()) | set(b.values()))
        indices = {value: i for i, value in enumerate(categories)}
        groups: dict[tuple[int, int, int, int], list[int]] = {}
        for i, item in enumerate(items):
            if item in a and item in b:
                x, y = a[item], b[item]
                key = (indices[x], indices[y], sign(x), sign(y))
                groups.setdefault(key, []).append(i)
        return cls(len(categories), tuple((*key, tuple(group)) for key, group in groups.items()))

    def evaluate(self, weights: Sequence[int]) -> tuple[float | None, ...]:
        """Calcola pi, accordo, accordo senza pari e alfa sullo stesso ripescaggio."""
        total = equal = no_ties = equal_no_ties = 0
        signs = [0, 0, 0]
        marginals = [0] * self.categories
        cells = []
        for left, right, x, y, indices in self.groups:
            count = sum(weights[i] for i in indices)
            if not count:
                continue
            total += count
            equal += count * (x == y)
            signs[x + 1] += count
            signs[y + 1] += count
            if x and y:
                no_ties += count
                equal_no_ties += count * (x == y)
            marginals[left] += count
            marginals[right] += count
            cells.append((left, right, count))
        if not total:
            return (None,) * 4
        pe = sum(count * count for count in signs) / (4 * total * total)
        accuracy = equal / total
        pi = (accuracy - pe) / (1 - pe) if pe != 1 else None
        try:
            alpha = _alpha_counts(marginals, cells)
        except AgreementError:
            alpha = None
        return pi, accuracy, equal_no_ties / no_ties if no_ties else None, alpha


def _means(pairs: Sequence[_PairCounts], weights: Sequence[int]) -> list[float | None]:
    totals = [0.0] * 4
    counts = [0] * 4
    for pair in pairs:
        for i, value in enumerate(pair.evaluate(weights)):
            if value is not None:
                totals[i] += value
                counts[i] += 1
    return [total / count if count else None for total, count in zip(totals, counts)]


def _estimates(hh: Sequence[_PairCounts], jh: Sequence[_PairCounts], weights: Sequence[int]
               ) -> dict[str, float | None]:
    human, judge = _means(hh, weights), _means(jh, weights)
    delta = judge[0] - human[0] if judge[0] is not None and human[0] is not None else None
    return dict(zip(METRICS, (human[0], judge[0], delta, human[1], judge[1],
                              human[2], judge[2], human[3], judge[3])))


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def agreement_report(votes: Sequence[Vote], judgments: Sequence[Judgment], *,
                     samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Rapporto con bootstrap sulle coppie e percentili interpolati al 2,5 e 97,5.

    Una misura indefinita vale None (null nel JSON). Ogni ripescaggio saltato
    si conta separatamente per metrica; una soglia indefinita non accetta il giudice.
    """
    if type(samples) is not int or samples < 1:
        raise AgreementError("samples deve essere un intero positivo")
    humans, judge = ratings_from(votes, judgments)
    humans = {voter: values for voter, values in sorted(humans.items()) if values}
    if len(humans) < 2:
        raise AgreementError("servono almeno due votanti umani con coppie valutabili")
    items = sorted(judge)
    hh = [_PairCounts.build(a, b, items) for a, b in combinations(humans.values(), 2)]
    jh = [_PairCounts.build(judge, values, items) for values in humans.values()]
    point = _estimates(hh, jh, [1] * len(items))
    distributions: dict[str, list[float]] = {name: [] for name in METRICS}
    rng = random.Random(seed)
    for _ in range(samples):
        weights = [0] * len(items)
        for _ in items:
            weights[rng.randrange(len(items))] += 1
        for name, value in _estimates(hh, jh, weights).items():
            if value is not None:
                distributions[name].append(value)
    report: dict[str, Any] = {}
    for name, values in distributions.items():
        values.sort()
        report[name] = {"low": _percentile(values, 0.025), "point": point[name],
                        "high": _percentile(values, 0.975)}
    lows = [report[name]["low"] for name in ("pi_hh", "pi_jh", "delta")]
    report.update(pairs=len(items), voters=len(humans),
                  unratable=sum(judgment.value is None for judgment in judgments),
                  accepted=all(value is not None for value in lows) and accept(*lows),
                  samples=samples, seed=seed,
                  skipped={name: samples - len(values) for name, values in distributions.items()})
    return report
