"""Il decorator di ledger persiste senza alterare il calcolo del contabile."""

import json

import pytest

from accounting.errors import UnitNotFound, UnpricedUsage
from accounting.ledger import RunLedger
from accounting.ledger_accountant import LedgerAccountant
from accounting.memory import InMemoryAccountant
from accounting.record import UsageRecord


class RegistroFinto:
    def cost(self, _model, _unit, quantity):
        return quantity * 2


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_delega_calcolo_e_persiste_solo_dopo_successo(tmp_path):
    inner = InMemoryAccountant(RegistroFinto())
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    accountant = LedgerAccountant(inner, ledger)
    record = UsageRecord(model="m", quantities={"input_tokens": 3})

    cost = accountant.register(record)

    assert cost == 6
    assert record.cost == 6
    assert accountant.total_cost == 6
    assert accountant.call_count == 1
    assert _read_jsonl(ledger.run_dir / "usage.jsonl")[0]["record"]["cost"] == 6


def test_usage_non_prezzabile_diventa_evento_ma_non_consumo(tmp_path):
    inner = InMemoryAccountant(RegistroFinto())
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    accountant = LedgerAccountant(inner, ledger)
    record = UsageRecord(
        model="m",
        quantities={},
        operation="chat_completion",
        request_id="req_1",
        measurement_source="missing",
    )

    with pytest.raises(UnpricedUsage):
        accountant.register(record)

    assert inner.call_count == 0
    assert not (ledger.run_dir / "usage.jsonl").exists()
    assert _read_jsonl(ledger.run_dir / "events.jsonl") == [{
        "schema_version": 2,
        "event_type": "unpriced_usage",
        "run_id": "run-1",
        "sequence": 1,
        "details": {
            "model": "m",
            "operation": "chat_completion",
            "request_id": "req_1",
            "measurement_source": "missing",
            "reason": "UnpricedUsage",
            "quantities": {},
        },
    }]


def test_un_unita_senza_listino_diventa_evento_con_le_quantita(tmp_path):
    """Un buco nel listino non deve cancellare una spesa gia' sostenuta.

    La chiamata al provider e' avvenuta e e' stata pagata: se la prezzatura
    fallisce, l'evento deve conservare le **quantita' osservate**, cosi' che
    il costo resti ricalcolabile una volta corretto `models.toml`. Senza,
    quella spesa sparirebbe dal ledger e i totali della campagna
    sperimentale risulterebbero sottostimati.
    """
    class RegistroSenzaPrezzoCache:
        def cost(self, _model, unit, quantity):
            if unit == "cached_input_tokens":
                raise UnitNotFound("nessun prezzo per 'cached_input_tokens'")
            return quantity * 2

    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    accountant = LedgerAccountant(InMemoryAccountant(RegistroSenzaPrezzoCache()), ledger)
    record = UsageRecord(
        model="opus-5",
        quantities={"input_tokens": 150, "cached_input_tokens": 200},
        operation="chat_completion",
        request_id="req_1",
    )

    with pytest.raises(UnitNotFound):
        accountant.register(record)

    dettagli = _read_jsonl(ledger.run_dir / "events.jsonl")[0]["details"]
    assert dettagli["reason"] == "UnitNotFound"
    assert dettagli["quantities"] == {"input_tokens": 150, "cached_input_tokens": 200}
    assert not (ledger.run_dir / "usage.jsonl").exists()
