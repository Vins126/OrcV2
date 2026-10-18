"""L'esito del turno: il confine fra gateway e agente porta il motivo di arresto.

Nota di design (tesi):
    Prima di M3.0b l'agente considerava concluso ogni turno senza tool call. Ma
    «niente tool call» non significa «ho finito»: puo' voler dire che il modello
    e' stato fermato dal limite di token, che ha rifiutato, che il fornitore ha
    segnalato un errore, o che non ha scritto nulla. Il campione che lo ha
    mostrato e' una richiesta vera a `minimax-m3` con tetto di 8000 token: li ha
    spesi tutti in ragionamento (7999) e si e' chiusa con `finish_reason: length`,
    senza testo e senza tool call.

    Questi test fissano il contratto in tre punti: il gateway traduce il motivo
    di arresto del proprio fornitore, l'agente decide sull'esito e non sulla sola
    assenza di tool call, e ogni stato di run ha la sua etichetta nel report.
"""

import json
from types import SimpleNamespace as NS

import pytest

import config
from agent import Agent
from llm_contracts import AssistantTurn, ToolCall, TurnOutcome
from llm_gateway import AnthropicChatGateway, OpenAIChatGateway
from loop_detector import RilevatoreLoop
from run_reporter import RunReporter
from run_status import RunStatus


class GatewayFinto:
    """Restituisce sempre lo stesso turno."""

    def __init__(self, turno):
        self.turno = turno

    def complete(self, messages, tools):
        return self.turno


def _rilevatore():
    return RilevatoreLoop(config.ALERT_THRESHOLD, config.LOOP_THRESHOLD)


def _richiesta_tool():
    return ToolCall(id="1", name="bash", arguments='{"cmd": "ls"}')


# -- Il turno ----------------------------------------------------------------

def test_un_turno_costruito_a_mano_e_completo_per_default():
    """Chi costruisce un turno senza esito (i finti dei test) non si accorge del cambio."""
    assert AssistantTurn(content="ok").outcome is TurnOutcome.COMPLETE


# -- OpenAI: dal motivo di arresto all'esito ---------------------------------

def _risposta_openai(finish_reason, con_tool_call=False, content="ok"):
    tool_calls = (
        [NS(id="call_1", function=NS(name="bash", arguments="{}"))] if con_tool_call else None
    )
    return NS(choices=[NS(finish_reason=finish_reason,
                          message=NS(content=content, tool_calls=tool_calls))])


@pytest.mark.parametrize("finish_reason, con_tool_call, atteso", [
    ("stop", False, TurnOutcome.COMPLETE),
    ("stop", True, TurnOutcome.TOOL_REQUEST),       # alcuni fornitori dicono «stop» con tool call
    ("tool_calls", True, TurnOutcome.TOOL_REQUEST),
    ("length", False, TurnOutcome.TRUNCATED),
    ("length", True, TurnOutcome.TRUNCATED),        # una tool call tagliata non e' una richiesta
    ("content_filter", False, TurnOutcome.REFUSED),
    ("error", False, TurnOutcome.ERROR),
    ("tool_calls", False, TurnOutcome.ERROR),       # dice «tool» ma non ce n'e': incoerente
    (None, False, TurnOutcome.ERROR),               # motivo assente: non si presume «finito»
    ("motivo_mai_visto", False, TurnOutcome.ERROR),
])
def test_openai_traduce_il_motivo_di_arresto(finish_reason, con_tool_call, atteso):
    turno = OpenAIChatGateway._to_turn(_risposta_openai(finish_reason, con_tool_call))

    assert turno.outcome is atteso


# -- Anthropic: dal motivo di arresto all'esito ------------------------------

def _risposta_anthropic(stop_reason, con_tool_use=False):
    blocchi = [NS(type="text", text="ok")]
    if con_tool_use:
        blocchi.append(NS(type="tool_use", id="tu_1", name="bash", input={}))
    return NS(stop_reason=stop_reason, content=blocchi)


@pytest.mark.parametrize("stop_reason, con_tool_use, atteso", [
    ("end_turn", False, TurnOutcome.COMPLETE),
    ("stop_sequence", False, TurnOutcome.COMPLETE),
    ("tool_use", True, TurnOutcome.TOOL_REQUEST),
    ("max_tokens", False, TurnOutcome.TRUNCATED),
    ("max_tokens", True, TurnOutcome.TRUNCATED),
    ("model_context_window_exceeded", False, TurnOutcome.TRUNCATED),
    ("refusal", False, TurnOutcome.REFUSED),
    ("pause_turn", False, TurnOutcome.ERROR),       # serve a strumenti lato server: non li usiamo
    (None, False, TurnOutcome.ERROR),
])
def test_anthropic_traduce_il_motivo_di_arresto(stop_reason, con_tool_use, atteso):
    turno = AnthropicChatGateway._to_turn(_risposta_anthropic(stop_reason, con_tool_use))

    assert turno.outcome is atteso


# -- L'agente decide sull'esito ----------------------------------------------

@pytest.mark.parametrize("esito, stato_atteso", [
    (TurnOutcome.TRUNCATED, RunStatus.OUTPUT_TRUNCATED),
    (TurnOutcome.REFUSED, RunStatus.REFUSED),
    (TurnOutcome.ERROR, RunStatus.PROVIDER_ERROR),
])
def test_un_esito_anomalo_non_e_un_completamento(esito, stato_atteso):
    agent = Agent(GatewayFinto(AssistantTurn(content="Ho fin", outcome=esito)), [])

    stato, messaggio = agent._esegui_iterazione([], _rilevatore(), 1)

    assert stato == stato_atteso
    assert isinstance(messaggio, str) and messaggio


def test_le_tool_call_di_un_turno_troncato_non_si_eseguono():
    """Una tool call tagliata a meta' potrebbe scrivere un file a meta'."""
    turno = AssistantTurn(tool_calls=(_richiesta_tool(),), outcome=TurnOutcome.TRUNCATED)
    messaggi: list = []

    stato, _ = Agent(GatewayFinto(turno), [])._esegui_iterazione(messaggi, _rilevatore(), 1)

    assert stato == RunStatus.OUTPUT_TRUNCATED
    assert not any(isinstance(m, dict) and m.get("role") == "tool" for m in messaggi)


@pytest.mark.parametrize("esito", [TurnOutcome.TRUNCATED, TurnOutcome.REFUSED, TurnOutcome.ERROR])
def test_un_turno_anomalo_non_entra_nella_storia(esito):
    """Un turno tagliato nella storia inquinerebbe l'incarico successivo dello stesso agente."""
    messaggi: list = []
    agent = Agent(GatewayFinto(AssistantTurn(content="Ho fin", outcome=esito)), [])

    agent._esegui_iterazione(messaggi, _rilevatore(), 1)

    assert messaggi == []


@pytest.mark.parametrize("testo", [None, "", "   \n"])
def test_una_risposta_vuota_non_e_un_completamento(testo):
    """Un modello che chiude senza dire nulla non ha «finito»: ha fallito in silenzio."""
    messaggi: list = []
    agent = Agent(GatewayFinto(AssistantTurn(content=testo)), [])

    stato, _ = agent._esegui_iterazione(messaggi, _rilevatore(), 1)

    assert stato == RunStatus.EMPTY_RESPONSE
    # Un turno vuoto rimandato al fornitore e' rifiutato da alcuni di loro.
    assert messaggi == []


def test_la_run_riporta_lo_stato_del_turno_anomalo():
    turno = AssistantTurn(content="Ho fin", outcome=TurnOutcome.TRUNCATED)

    risultato = Agent(GatewayFinto(turno), []).run("task")

    assert risultato.status == "output_truncated"
    assert risultato.iterations == 1


# -- Gli stati ---------------------------------------------------------------

def test_gli_stati_conservano_le_stringhe_gia_scritte_in_runs():
    """Il dataset in `runs/` ha gia' queste stringhe: l'enumerazione non le cambia."""
    assert RunStatus.COMPLETED == "completed"
    assert RunStatus.MAX_ITERATIONS == "max_iterations"
    assert RunStatus.UNEXPECTED_ERROR == "unexpected_error"
    assert json.dumps({"status": RunStatus.COMPLETED}) == '{"status": "completed"}'


def test_ogni_stato_ha_la_sua_etichetta_nel_report():
    mancanti = [s.value for s in RunStatus if s.value not in RunReporter._STATUS_LABELS]

    assert mancanti == []
