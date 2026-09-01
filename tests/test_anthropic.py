"""Il secondo fornitore: mapper e gateway dell'API Messages.

Nota di design (tesi):
    Questo file e' la verifica sperimentale della promessa fatta a M2a — che
    aggiungere un provider significhi aggiungere un mapper e un gateway, non
    ramificare l'agente. Se un giorno servisse toccare `Agent` per far entrare
    un terzo fornitore, l'architettura avrebbe smesso di reggere e questi test
    sarebbero il posto da cui accorgersene.
"""

import json
from types import SimpleNamespace as NS

import pytest

from accounting import InMemoryAccountant, ModelRegistry
from accounting.mappers.anthropic import AnthropicMessagesUsageMapper as Mapper
from llm_contracts import AssistantTurn, ToolCall
from llm_gateway import AnthropicChatGateway


def _usage(input_tokens=150, output=120, cache_read=0, cache_write=0):
    return NS(
        input_tokens=input_tokens,
        output_tokens=output,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )


#: Sentinella: `None` e' un valore legittimo per `usage` (provider che non lo
#: dichiara), quindi non puo' fare anche da "usa il default".
_OMESSO = object()


def _response(usage=_OMESSO, blocchi=None, stop_reason="end_turn"):
    return NS(
        id="msg_1",
        stop_reason=stop_reason,
        usage=_usage() if usage is _OMESSO else usage,
        content=blocchi if blocchi is not None else [NS(type="text", text="ok")],
    )


class Client:
    """Client finto che registra la richiesta ricevuta."""

    def __init__(self, response=None):
        self.richieste = []
        self.response = response or _response()
        self.messages = NS(create=self.create)

    def create(self, **kwargs):
        self.richieste.append(kwargs)
        return self.response


class Accountant:
    def __init__(self):
        self.records = []

    def register(self, record):
        self.records.append(record)
        return 0.0

    @property
    def total_cost(self):
        return 0.0


# ── Mapper: la trappola all'opposto ───────────────────────────────────────

def test_i_token_da_cache_non_vengono_sottratti():
    """`input_tokens` sono gia' i soli non in cache: sottrarre e' l'errore.

    E' la trappola speculare a quella di OpenAI. Sbagliarla qui non gonfia il
    totale: lo **sgonfia**, cioe' sposta il risultato proprio nella direzione
    che farebbe sembrare la tesi piu' forte di quanto e'.
    """
    record = Mapper.to_record(
        _response(_usage(input_tokens=150, output=120, cache_read=200)),
        model="opus-5", latency_s=0.1,
    )

    assert record.quantities["input_tokens"] == 150      # non 150-200, non 350
    assert record.quantities["cached_input_tokens"] == 200
    assert record.quantities["output_tokens"] == 120


def test_la_scrittura_in_cache_e_una_voce_a_se():
    record = Mapper.to_record(
        _response(_usage(cache_write=400)), model="opus-5", latency_s=0.1)

    assert record.quantities["cache_write_tokens"] == 400


def test_usage_assente_e_dichiarato_non_misurato():
    record = Mapper.to_record(_response(usage=None), model="opus-5", latency_s=0.1)

    assert record.measurement_source == "missing"
    assert not record.is_priceable


def test_l_operazione_resta_confrontabile_con_l_altro_fornitore():
    """Stesso nome di operazione del mapper chat OpenAI, di proposito.

    Senza, `cost_by_operation` non permetterebbe di confrontare lo stesso
    lavoro su due percorsi — che e' l'esperimento della tassa
    dell'aggregatore. A distinguere chi ha risposto c'e' `api_provider`.
    """
    record = Mapper.to_record(_response(), model="opus-5", latency_s=0.1)

    assert record.operation == "chat_completion"
    assert record.api_provider == "anthropic"


def test_conta_gli_strumenti_richiesti_e_la_ragione_di_fine():
    blocchi = [
        NS(type="text", text="procedo"),
        NS(type="tool_use", id="t1", name="bash", input={"cmd": "ls"}),
        NS(type="tool_use", id="t2", name="read_file", input={"path": "a"}),
    ]
    record = Mapper.to_record(
        _response(blocchi=blocchi, stop_reason="tool_use"), model="opus-5", latency_s=0.1)

    assert record.n_tool_calls == 2
    assert record.finish_reason == "tool_use"


# ── Mapper contro il listino reale ────────────────────────────────────────

def test_il_listino_reale_prezza_le_quattro_unita():
    """`opus-5` deve dichiarare tutte le unita' che questo mapper puo' emettere.

    E' lo stesso controllo che a M2a scopri' il buco sui token da cache: la
    giuntura fra cio' che un mapper produce e cio' che il registro sa prezzare.
    """
    contabile = InMemoryAccountant(ModelRegistry.from_file("models.toml"))
    record = Mapper.to_record(
        _response(_usage(input_tokens=150, output=120, cache_read=200, cache_write=400)),
        model="opus-5", latency_s=0.1,
    )

    costo = contabile.register(record)

    # 150 pieni a $5 + 200 da cache a $0.50 + 400 scritti a $6.25 + 120 out a $25
    assert costo == pytest.approx(0.00075 + 0.0001 + 0.0025 + 0.003)


# ── Gateway: conversione della risposta ───────────────────────────────────

def test_i_blocchi_diventano_un_turno_del_progetto():
    blocchi = [
        NS(type="text", text="ci provo"),
        NS(type="tool_use", id="t1", name="bash", input={"b": 2, "a": 1}),
    ]
    gateway = AnthropicChatGateway(Client(_response(blocchi=blocchi)), "opus-5", Accountant())

    turno = gateway.complete([], [])

    assert isinstance(turno, AssistantTurn)
    assert turno.content == "ci provo"
    assert turno.tool_calls[0].name == "bash"


def test_gli_argomenti_sono_serializzati_in_forma_canonica():
    """Chiavi ordinate, altrimenti il rilevatore di loop diventa cieco.

    Qui gli argomenti arrivano come dizionario e il contratto li vuole come
    stringa. Se l'ordine delle chiavi variasse fra due chiamate identiche, le
    firme non coinciderebbero e una ripetizione non verrebbe riconosciuta.
    """
    blocchi = [NS(type="tool_use", id="t1", name="bash", input={"b": 2, "a": 1})]
    gateway = AnthropicChatGateway(Client(_response(blocchi=blocchi)), "opus-5", Accountant())

    turno = gateway.complete([], [])

    assert turno.tool_calls[0].arguments == '{"a": 1, "b": 2}'
    assert json.loads(turno.tool_calls[0].arguments) == {"a": 1, "b": 2}


# ── Gateway: conversione della conversazione ──────────────────────────────

def test_il_prompt_di_sistema_esce_dalla_conversazione():
    """In questa API il sistema e' un parametro, non un messaggio."""
    system, messaggi = AnthropicChatGateway._to_wire([
        {"role": "system", "content": "sei un agente"},
        {"role": "user", "content": "ciao"},
    ])

    assert system == "sei un agente"
    assert messaggi == [{"role": "user", "content": "ciao"}]


def test_le_osservazioni_dello_stesso_turno_finiscono_in_un_messaggio_solo():
    """Separarle insegnerebbe al modello a non chiedere piu' tool in parallelo.

    L'agente accoda un messaggio per ogni tool eseguito; questa API li vuole
    raggruppati. E' una perdita di efficienza che non darebbe alcun errore.
    """
    _, messaggi = AnthropicChatGateway._to_wire([
        {"role": "user", "content": "fai due cose"},
        AssistantTurn(tool_calls=(
            ToolCall(id="t1", name="bash", arguments="{}"),
            ToolCall(id="t2", name="bash", arguments="{}"),
        )),
        {"role": "tool", "tool_call_id": "t1", "content": "primo"},
        {"role": "tool", "tool_call_id": "t2", "content": "secondo"},
    ])

    assert len(messaggi) == 3                      # utente, assistente, osservazioni
    assert messaggi[2]["role"] == "user"
    assert [b["tool_use_id"] for b in messaggi[2]["content"]] == ["t1", "t2"]


def test_un_turno_torna_come_blocchi_di_contenuto():
    _, messaggi = AnthropicChatGateway._to_wire([
        AssistantTurn(content="ecco", tool_calls=(
            ToolCall(id="t1", name="bash", arguments='{"cmd": "ls"}'),
        )),
    ])

    assert messaggi[0] == {"role": "assistant", "content": [
        {"type": "text", "text": "ecco"},
        {"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "ls"}},
    ]}


def test_gli_schemi_dei_tool_vengono_tradotti():
    """`Tool.schema` produce la forma OpenAI: la traduzione vive nel gateway."""
    tradotti = AnthropicChatGateway._tools_to_wire([{
        "type": "function",
        "function": {
            "name": "bash",
            "description": "esegue comandi",
            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
        },
    }])

    assert tradotti == [{
        "name": "bash",
        "description": "esegue comandi",
        "input_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}},
    }]


# ── Gateway: la cache e' una variabile sperimentale ───────────────────────

def test_la_cache_e_dichiarata_di_default():
    client = Client()
    AnthropicChatGateway(client, "opus-5", Accountant()).complete([], [])

    assert client.richieste[0]["cache_control"] == {"type": "ephemeral"}


def test_la_cache_si_puo_disattivare_per_misurarne_l_effetto():
    """Serve a confrontare con e senza cache a parita' di tutto il resto.

    E' l'esperimento della tassa dell'aggregatore: senza questa manopola si
    potrebbe solo confrontare percorsi diversi, non isolare la causa.
    """
    client = Client()
    AnthropicChatGateway(client, "opus-5", Accountant(), use_cache=False).complete([], [])

    assert "cache_control" not in client.richieste[0]


def test_lo_sforzo_viaggia_nella_richiesta():
    """`effort` incide sui token di output, che sono oltre meta' della spesa."""
    client = Client()
    AnthropicChatGateway(client, "opus-5", Accountant(), effort="low").complete([], [])

    assert client.richieste[0]["output_config"] == {"effort": "low"}
