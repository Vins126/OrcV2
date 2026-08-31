"""Il report di fine run legge fatti dal ledger, non ricalcola il costo."""

from run_reporter import RunReporter


def _summary(**overrides):
    values = {
        "run_id": "run-1",
        "status": "completed",
        "iterations": 2,
        "duration_s": 1.25,
        "usage_count": 2,
        "total_cost": 0.006,
        "quantities_by_unit": {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 30,
        },
        "unpriced_count": 0,
    }
    values.update(overrides)
    return values


def test_render_mostra_costo_token_durata_esito_e_riferimento_al_ledger():
    report = RunReporter().render(_summary(), [], "runs/run-1")

    assert "esito: completato" in report
    assert "durata: 1.250s" in report
    assert "costo totale: $0.00600000" in report
    assert "costo per iterazione: $0.00300000" in report
    assert "token: input=100, cached=20, output=30" in report
    assert "ledger: runs/run-1" in report


def test_render_budget_documenta_lo_sforamento():
    events = [{
        "event_type": "budget_exhausted",
        "details": {
            "hard_limit_usd": 0.01,
            "total_cost_usd": 0.012,
            "overrun_usd": 0.002,
        },
    }]

    report = RunReporter().render(
        _summary(status="budget_exhausted", iterations=3), events, "runs/run-1",
    )

    assert "esito: budget esaurito" in report
    assert "budget: cap=$0.01000000, speso=$0.01200000, sforamento=$0.00200000" in report


def test_emit_stampa_il_report_leggibile_una_sola_volta(capsys):
    RunReporter().emit(_summary(), [], "runs/run-1")

    assert capsys.readouterr().out.count("REPORT RUN") == 1
