"""Contratto del ledger persistente di una singola esecuzione."""

import json

from accounting.ledger import RunLedger
from accounting.record import UsageRecord


def _leggi_jsonl(path):
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _record(**overrides):
    values = {
        "model": "modello-test",
        "api_provider": "api-test",
        "billing_provider": "billing-test",
        "operation": "chat_completion",
        "request_id": "req_123",
        "quantities": {"input_tokens": 100, "output_tokens": 20},
        "cost": 0.42,
        "latency_s": 0.25,
    }
    values.update(overrides)
    return UsageRecord(**values)


def test_crea_directory_con_identita_della_run_senza_salvare_il_task_in_chiaro(tmp_path):
    task = "Analizza il repository riservato del cliente ACME"

    ledger = RunLedger(
        root=tmp_path,
        task=task,
        run_id="run-test-001",
        agent_id="worker-1",
        role="developer",
    )

    assert ledger.run_id == "run-test-001"
    assert ledger.run_dir == tmp_path / "run-test-001"
    assert ledger.run_dir.is_dir()
    assert ledger.task_hash
    assert task not in ledger.task_hash


def test_appende_usage_record_in_jsonl_con_envelope_di_run(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")

    ledger.append_usage(_record())

    lines = _leggi_jsonl(ledger.run_dir / "usage.jsonl")
    assert len(lines) == 1
    entry = lines[0]
    timestamp = entry["record"].pop("timestamp")
    assert timestamp
    assert entry == {
        "schema_version": 4,
        "event_type": "usage",
        "run_id": "run-1",
        "sequence": 1,
        "record": {
            "model": "modello-test",
            "quantities": {"input_tokens": 100, "output_tokens": 20},
            "cost": 0.42,
            "api_provider": "api-test",
            "billing_provider": "billing-test",
            "operation": "chat_completion",
            "request_id": "req_123",
            "status": "succeeded",
            "dimensions": {},
            "measurement_source": "reported",
            "label": None,
            "finish_reason": None,
            "n_tool_calls": 0,
            "latency_s": 0.25,
            "attempt": 1,
            "reasoning_tokens": 0,
            "notes": None,
            "reported_cost": None,
            "served_by": None,
        },
    }


def test_appende_evento_non_prezzabile_separato_dai_consumi(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")

    ledger.append_event("unpriced_usage", {"model": "modello-test", "reason": "usage missing"})

    events = _leggi_jsonl(ledger.run_dir / "events.jsonl")
    assert events == [{
        "schema_version": 4,
        "event_type": "unpriced_usage",
        "run_id": "run-1",
        "sequence": 1,
        "details": {"model": "modello-test", "reason": "usage missing"},
    }]
    assert not (ledger.run_dir / "usage.jsonl").exists()


def test_close_scrive_summary_derivato_dai_record_e_dagli_eventi(tmp_path):
    ledger = RunLedger(
        root=tmp_path, task="task", run_id="run-1", agent_id="worker-1", role="developer",
    )
    ledger.append_usage(_record(cost=0.42, quantities={"input_tokens": 100}))
    ledger.append_usage(_record(cost=0.08, quantities={"output_tokens": 20}, operation="image_generation"))
    ledger.append_event("unpriced_usage", {"reason": "usage missing"})

    summary = ledger.close(status="completed", iterations=2)

    on_disk = json.loads((ledger.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary == on_disk
    assert on_disk["schema_version"] == 4
    assert on_disk["run_id"] == "run-1"
    assert on_disk["agent_id"] == "worker-1"
    assert on_disk["role"] == "developer"
    assert on_disk["status"] == "completed"
    assert on_disk["iterations"] == 2
    assert on_disk["usage_count"] == 2
    assert on_disk["unpriced_count"] == 1
    assert on_disk["total_cost"] == 0.5
    assert on_disk["cost_by_model"] == {"modello-test": 0.5}
    assert on_disk["cost_by_operation"] == {
        "chat_completion": 0.42,
        "image_generation": 0.08,
    }
    assert "started_at" in on_disk
    assert "finished_at" in on_disk
    assert on_disk["duration_s"] >= 0


# -- Registro dell'esito della run (M3.0b passo 6, D24) -------------------------

def test_la_versione_dello_schema_e_4():
    """Il riepilogo ha due campi nuovi: chi legge i file vecchi (versione 3) deve tollerarne l'assenza."""
    assert RunLedger.SCHEMA_VERSION == 4


def test_il_summary_porta_il_messaggio_finale_e_l_ultimo_motivo_di_arresto(tmp_path):
    """Senza, dopo una run fallita non si poteva leggere cosa avesse risposto l'agente."""
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    ledger.append_usage(_record(finish_reason="tool_calls"))
    ledger.append_usage(_record(finish_reason="stop"))

    summary = ledger.close(status="completed", iterations=2, final_message="Ho finito")

    on_disk = json.loads((ledger.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["last_finish_reason"] == on_disk["last_finish_reason"] == "stop"
    assert summary["final_message"] == on_disk["final_message"] == "Ho finito"


def test_l_ultimo_motivo_di_arresto_ignora_i_tentativi_interrotti(tmp_path):
    """Un tentativo interrotto non ha un motivo di arresto: l'ultimo che conta e' quello dell'ultima risposta."""
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    ledger.append_usage(_record(finish_reason="length"))
    ledger.append_usage(_record(status="interrupted", finish_reason=None))

    summary = ledger.close(status="output_truncated", iterations=1)

    assert summary["last_finish_reason"] == "length"


def test_senza_risposte_ne_messaggio_i_campi_sono_nulli_ma_presenti(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")

    summary = ledger.close(status="unexpected_error", iterations=0)

    assert summary["last_finish_reason"] is None
    assert summary["final_message"] is None


def test_l_ultimo_motivo_di_arresto_ignora_un_interrotto_anche_se_ha_un_motivo(tmp_path):
    """`/generation` puo' dare un motivo anche a un tentativo scartato: non e' una risposta arrivata."""
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")
    ledger.append_usage(_record(finish_reason="tool_calls"))
    ledger.append_usage(_record(status="interrupted", finish_reason="stop"))

    assert ledger.close(status="service_unavailable", iterations=2)["last_finish_reason"] == "tool_calls"


def test_se_ci_sono_solo_interrotti_il_motivo_e_nullo(tmp_path):
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")
    ledger.append_usage(_record(status="interrupted", finish_reason="stop"))

    assert ledger.close(status="service_unavailable", iterations=1)["last_finish_reason"] is None
