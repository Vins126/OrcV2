"""Statistica dell'analisi della campagna MVP (PROTOCOLLO §10).

Nota di design (tesi):
    I valori di riferimento della t di Student vengono dalle tavole standard
    (t_{0,975; 4} = 2,7764; t_{0,975; 9} = 2,2622), cosi' il calcolo senza
    librerie esterne si controlla contro numeri noti. Il bootstrap esatto non
    dipende dal seme: lo verifica un test.
"""

import math

import pytest

from analisi.statistica import (
    bootstrap,
    bootstrap_mean,
    bootstrap_ratio,
    betainc,
    paired_t,
    t_quantile,
    t_two_sided_p,
)


@pytest.mark.parametrize("df, expected", [(4, 2.7764), (9, 2.2622), (30, 2.0423)])
def test_t_quantile_matches_tables(df: int, expected: float) -> None:
    assert t_quantile(0.975, df) == pytest.approx(expected, abs=1e-4)


def test_t_p_value_at_critical_value_is_five_percent() -> None:
    assert t_two_sided_p(2.7764451, 4) == pytest.approx(0.05, abs=1e-6)
    assert t_two_sided_p(0.0, 4) == pytest.approx(1.0)


def test_betainc_known_values() -> None:
    assert betainc(1, 1, 0.3) == pytest.approx(0.3)
    assert betainc(2, 3, 0.4) == pytest.approx(0.5248, abs=1e-4)
    assert betainc(2, 3, 0) == 0.0 and betainc(2, 3, 1) == 1.0


def test_paired_t_interval_and_zero_spread() -> None:
    mean, p, (low, high) = paired_t([1.0, 2.0, 3.0, 4.0, 5.0])
    half = 2.7764451 * math.sqrt(2.5) / math.sqrt(5)
    assert mean == 3.0 and low == pytest.approx(3 - half) and high == pytest.approx(3 + half)
    assert p is not None and 0 < p < 0.05
    assert paired_t([2.0, 2.0, 2.0]) == (2.0, None, (2.0, 2.0))
    with pytest.raises(ValueError):
        paired_t([1.0])


def test_exact_bootstrap_ignores_seed_and_counts_all_resamples() -> None:
    values = [0.0, 10.0, 20.0, -5.0, 3.0]
    assert bootstrap_mean(values, seed=1) == bootstrap_mean(values, seed=2)
    seen = []
    bootstrap(3, lambda index: seen.append(tuple(index)) or 0.0)
    assert len(seen) == 27 and len(set(seen)) == 27


def test_exact_bootstrap_bounds_contain_mean_and_stay_in_range() -> None:
    values = [0.0, 10.0, 20.0, -5.0, 3.0]
    low, high = bootstrap_mean(values)
    assert min(values) <= low <= sum(values) / 5 <= high <= max(values)


def test_seeded_bootstrap_above_exact_limit_is_reproducible() -> None:
    values = [float(i % 7) for i in range(12)]
    assert bootstrap_mean(values, samples=500) == bootstrap_mean(values, samples=500)
    assert bootstrap_mean(values, samples=500, seed=1) != bootstrap_mean(values, samples=500, seed=99)


def test_ratio_of_sums() -> None:
    low, high = bootstrap_ratio([1.0, 1.0], [2.0, 2.0])
    assert low == high == 0.5
    with pytest.raises(ValueError):
        bootstrap_ratio([1.0], [1.0, 2.0])
