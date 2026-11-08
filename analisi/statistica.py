"""Intervalli per pochi compiti: bootstrap esatto o con seme, test t appaiato (PROTOCOLLO §10).

Con 8 compiti o meno il bootstrap si fa esatto: si elencano tutti gli n^n ricampionamenti
(3125 con 5 compiti), quindi il risultato non dipende da un seme. Oltre, si estraggono
`N_BOOT` ricampionamenti con il seme del protocollo.
"""

import itertools
import math
import random
import statistics
from collections.abc import Callable, Sequence

SEED = 20261021
N_BOOT = 10_000
EXACT_MAX_N = 8

Stat = Callable[[Sequence[int]], float]


def bootstrap(n: int, stat: Stat, *, seed: int = SEED, samples: int = N_BOOT) -> tuple[float, float]:
    """Percentili 2,5 e 97,5 di `stat` sugli indici ricampionati di n unita'."""
    if n < 1:
        raise ValueError("servono almeno un'unita'")
    if n <= EXACT_MAX_N:
        values = sorted(stat(index) for index in itertools.product(range(n), repeat=n))
    else:
        rng = random.Random(seed)
        values = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(samples))
    total = len(values)
    return values[int(0.025 * total)], values[int(0.975 * total) - 1]


def bootstrap_mean(values: Sequence[float], **kwargs: int) -> tuple[float, float]:
    """Intervallo della media."""
    return bootstrap(len(values), lambda index: statistics.mean(values[i] for i in index), **kwargs)


def bootstrap_ratio(top: Sequence[float], bottom: Sequence[float], **kwargs: int) -> tuple[float, float]:
    """Intervallo del rapporto fra somme (costo di un braccio su quello di B)."""
    if len(top) != len(bottom):
        raise ValueError("le due serie devono avere la stessa lunghezza")
    return bootstrap(len(top), lambda index: sum(top[i] for i in index) / sum(bottom[i] for i in index), **kwargs)


def _betacf(a: float, b: float, x: float) -> float:
    # Frazione continua di Lentz per la beta incompleta (Numerical Recipes, betacf).
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c if abs(c) > tiny else tiny
        step = d * c
        h *= step
        if abs(step - 1) < 1e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Funzione beta incompleta regolarizzata I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t: float, df: int) -> float:
    """Valore p bilaterale della t di Student."""
    return betainc(df / 2, 0.5, df / (df + t * t))


def t_quantile(p: float, df: int) -> float:
    """Quantile della t di Student per bisezione (p in (0,5; 1))."""
    target = 2 * (1 - p)
    low, high = 0.0, 1000.0
    for _ in range(200):
        mid = (low + high) / 2
        if t_two_sided_p(mid, df) > target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def paired_t(diffs: Sequence[float]) -> tuple[float, float | None, tuple[float, float]]:
    """Media delle differenze, p bilaterale (None se lo scarto e' zero) e intervallo al 95%."""
    n = len(diffs)
    if n < 2:
        raise ValueError("servono almeno due differenze")
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return mean, None, (mean, mean)
    t = mean / (sd / math.sqrt(n))
    half = t_quantile(0.975, n - 1) * sd / math.sqrt(n)
    return mean, t_two_sided_p(t, n - 1), (mean - half, mean + half)
