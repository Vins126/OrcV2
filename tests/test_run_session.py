"""La sessione chiude il ledger con l'esito strutturato dell'agente."""

import json

import pytest

from accounting.ledger import RunLedger
from agent import AgentFailure, RunResult
from run_session import RunSession


class AgentFinto:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def run(self, task, max_iterations=None):
        self.calls.append((task, max_iterations))
        if self.error:
            raise self.error
        return self.result


class ReporterFinto:
    def __init__(self):
        self.calls = []

    def emit(self, summary, events, ledger_path, agent_message=None):
        self.calls.append((summary, events, ledger_path, agent_message))


def test_chiude_il_ledger_con_l_esito_dell_agente(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    agent = AgentFinto(RunResult(status="completed", iterations=2))

    reporter = ReporterFinto()
    result = RunSession(agent, ledger, reporter).run("task", max_iterations=5)

    summary = json.loads((ledger.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert result == RunResult(status="completed", iterations=2)
    assert agent.calls == [("task", 5)]
    assert summary["status"] == "completed"
    assert summary["iterations"] == 2
    assert reporter.calls[0][0] == summary
    assert reporter.calls[0][1] == []


def test_registra_errore_inatteso_e_chiude_il_ledger(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    agent = AgentFinto(error=ValueError("errore non previsto"))

    reporter = ReporterFinto()
    with pytest.raises(ValueError, match="errore non previsto"):
        RunSession(agent, ledger, reporter).run("task")

    events = [json.loads(line) for line in (ledger.run_dir / "events.jsonl").read_text().splitlines()]
    summary = json.loads((ledger.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert events[0]["event_type"] == "unexpected_error"
    assert events[0]["details"] == {"error_type": "ValueError"}
    assert summary["status"] == "unexpected_error"
    assert summary["iterations"] == 0
    assert reporter.calls[0][0] == summary


def test_registra_terminazione_non_completata_come_evento(tmp_path):
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    agent = AgentFinto(RunResult(status="max_iterations", iterations=30))

    RunSession(agent, ledger).run("task")

    events = [json.loads(line) for line in (ledger.run_dir / "events.jsonl").read_text().splitlines()]
    assert events == [{
        "schema_version": 2,
        "event_type": "run_terminated",
        "run_id": "run-1",
        "sequence": 1,
        "details": {"status": "max_iterations", "iterations": 30},
    }]


def test_un_guasto_dell_agente_conserva_le_iterazioni_nel_summary(tmp_path):
    """Il ledger registra le iterazioni davvero svolte, non zero.

    E' l'altra meta' del test corrispondente in `test_agent.py`: li' si
    verifica che l'agente **produca** il conteggio, qui che la sessione lo
    **usi** invece di scrivere il valore di comodo.
    """
    ledger = RunLedger(root=tmp_path, task="task", run_id="run-1")
    guasto = AgentFailure(3, ZeroDivisionError("difetto di programmazione"))
    agent = AgentFinto(error=guasto)

    with pytest.raises(AgentFailure):
        RunSession(agent, ledger, ReporterFinto()).run("task")

    events = [json.loads(line)
              for line in (ledger.run_dir / "events.jsonl").read_text().splitlines()]
    summary = json.loads((ledger.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "unexpected_error"
    assert summary["iterations"] == 3
    # Nel ledger va la causa reale, non l'involucro che la trasporta.
    assert events[0]["details"] == {"error_type": "ZeroDivisionError", "iterations": 3}
