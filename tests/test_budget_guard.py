"""Test della policy di budget, senza rete o modelli reali."""

import pytest

from budget_guard import BudgetGuard, BudgetVerdict


def test_budget_disabilitato_non_limita_la_run():
    guard = BudgetGuard(None)

    assert guard.check(1000.0) is BudgetVerdict.OK
    assert guard.policy_details["enabled"] is False


def test_soglia_morbida_scocca_una_sola_volta():
    guard = BudgetGuard(10.0)

    assert guard.check(7.99) is BudgetVerdict.OK
    assert guard.check(8.0) is BudgetVerdict.SOFT_LIMIT_REACHED
    assert guard.check(9.0) is BudgetVerdict.OK


def test_tetto_duro_blocca_dalla_chiamata_successiva():
    guard = BudgetGuard(10.0)

    assert guard.check(10.0) is BudgetVerdict.HARD_LIMIT_REACHED
    assert guard.check(10.3) is BudgetVerdict.HARD_LIMIT_REACHED


@pytest.mark.parametrize("limit", [0, -1, float("inf")])
def test_rifiuta_tetti_non_validi(limit):
    with pytest.raises(ValueError):
        BudgetGuard(limit)
