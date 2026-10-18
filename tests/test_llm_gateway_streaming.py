"""Il gateway OpenAI in streaming: stessi turni e stessi conti, ma il guasto si vede prima.

Nota di design (tesi):
    Con `stream=True` il gateway consuma i chunk, li ricompone (`StreamAssembler`) e
    restituisce a `_to_turn` e al mapper una risposta con la forma di sempre: il
    resto del progetto non sa se la risposta e' arrivata intera o a pezzi.

    La differenza e' nel guasto. Un flusso troncato, un errore di rete a meta' o un
    errore che il fornitore scrive dentro il flusso (con HTTP gia' 200) sono guasti
    **transitori**: il turno non e' stato consegnato e l'agente non ha ancora agito,
    quindi ripetere la richiesta non ha effetti collaterali. Costa solo denaro, ed e'
    il motivo per cui ogni interruzione si registra (vedi M3.0b, passo 4).

    I flussi sono quelli catturati dalla sonda (`tests/fixtures/streaming/`).
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletionChunk

from llm_contracts import ToolCall, TurnOutcome
from llm_gateway import OpenAIChatGateway
from tests.test_llm_gateway import ContabileFinto, EventSink

FIXTURES = Path(__file__).parent / "fixtures" / "streaming"


def _chunks(nome):
    """I chunk di un flusso catturato, come oggetti dell'SDK (quelli che il client restituisce)."""
    risultato = []
    for riga in (FIXTURES / f"{nome}.jsonl").read_text().splitlines():
        linea = json.loads(riga)["line"]
        if linea.startswith("data:") and "[DONE]" not in linea:
            risultato.append(ChatCompletionChunk.model_validate(json.loads(linea[5:])))
    return risultato


class FlussoFinto:
    """Un flusso che restituisce i suoi chunk e poi, se richiesto, solleva un errore."""

    def __init__(self, chunks, errore=None):
        self.chunks, self.errore, self.chiuso = chunks, errore, False

    def __iter__(self):
        yield from self.chunks
        if self.errore is not None:
            raise self.errore

    def close(self):
        self.chiuso = True


class ClientInStreaming:
    """Restituisce un flusso per chiamata, nell'ordine dato, e ricorda i parametri."""

    def __init__(self, *flussi):
        self.flussi = list(flussi)
        self.richieste = []
        self.chat = NS(completions=NS(create=self._crea))

    def _crea(self, **kwargs):
        self.richieste.append(kwargs)
        return self.flussi.pop(0)


def _gateway(client, **kwargs):
    kwargs.setdefault("retry_max", 3)
    return OpenAIChatGateway(client, "m", ContabileFinto(), stream=True, **kwargs)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr("llm_gateway.time.sleep", lambda _s: None)


# -- La richiesta ------------------------------------------------------------

def test_con_lo_streaming_la_richiesta_lo_chiede():
    client = ClientInStreaming(FlussoFinto(_chunks("testo")))

    _gateway(client).complete([], [])

    assert client.richieste[0]["stream"] is True


def test_senza_lo_streaming_la_richiesta_non_cambia():
    client = ClientInStreaming()
    client.chat = NS(completions=NS(create=lambda **kw: client.richieste.append(kw) or NS(
        id="c", usage=None,
        choices=[NS(finish_reason="stop", message=NS(content="ok", tool_calls=None))])))

    OpenAIChatGateway(client, "m", ContabileFinto(), retry_max=1).complete([], [])

    assert "stream" not in client.richieste[0]


# -- Un flusso concluso ------------------------------------------------------

def test_un_flusso_vero_diventa_un_turno_e_un_record_di_consumo():
    contabile = ContabileFinto()
    client = ClientInStreaming(FlussoFinto(_chunks("una_tool_call")))
    gateway = OpenAIChatGateway(client, "m", contabile, stream=True, retry_max=1)

    turno = gateway.complete([], [])

    assert turno.outcome is TurnOutcome.TOOL_REQUEST
    assert [(c.name, json.loads(c.arguments)["path"]) for c in turno.tool_calls] == [("write_file", "hello.py")]
    record = contabile.records[0]
    assert record.reported_cost == pytest.approx(0.00018678)
    assert record.finish_reason == "tool_calls"
    assert record.served_by == "Minimax"
    assert record.n_tool_calls == 1


def test_i_chunk_possono_arrivare_come_dizionari():
    chunks = [c.model_dump() for c in _chunks("testo")]

    turno = _gateway(ClientInStreaming(FlussoFinto(chunks))).complete([], [])

    assert turno.outcome is TurnOutcome.COMPLETE and turno.content


def test_il_flusso_si_chiude_quando_e_concluso():
    flusso = FlussoFinto(_chunks("testo"))

    _gateway(ClientInStreaming(flusso)).complete([], [])

    assert flusso.chiuso


# -- Un flusso che non arriva in fondo ---------------------------------------

def test_un_flusso_troncato_viene_ritentato_e_il_tentativo_buono_e_quello_contato():
    contabile = ContabileFinto()
    client = ClientInStreaming(FlussoFinto(_chunks("interrotta")),
                               FlussoFinto(_chunks("una_tool_call")))
    gateway = OpenAIChatGateway(client, "m", contabile, stream=True, retry_max=3)

    turno = gateway.complete([], [])

    assert len(client.richieste) == 2
    assert turno.tool_calls == (ToolCall(
        id=turno.tool_calls[0].id, name="write_file", arguments=turno.tool_calls[0].arguments),)
    assert [r.attempt for r in contabile.records] == [2]


def test_un_flusso_sempre_troncato_finisce_come_irraggiungibile_e_si_registra():
    events = EventSink()
    flussi = [FlussoFinto(_chunks("interrotta")) for _ in range(2)]
    gateway = _gateway(ClientInStreaming(*flussi), retry_max=2, event_sink=events)

    with pytest.raises(RuntimeError, match="LLM irraggiungibile"):
        gateway.complete([], [])

    # Ogni tentativo interrotto lascia il suo evento (M3.0b passo 4); l'errore
    # finale e' l'ultimo, e non ce n'e' un secondo.
    tipi = [tipo for tipo, _ in events.events]
    assert tipi.count("stream_interrupted") == 2
    assert tipi.count("provider_error") == 1 and tipi[-1] == "provider_error"
    assert events.events[-1][1]["error_type"] == "StreamInterrupted"
    assert events.events[-1][1]["attempts"] == 2


def test_un_errore_di_rete_a_meta_flusso_viene_ritentato():
    rotto = FlussoFinto(_chunks("interrotta")[:5], errore=httpx.ReadError("connessione chiusa"))
    client = ClientInStreaming(rotto, FlussoFinto(_chunks("testo")))

    turno = _gateway(client).complete([], [])

    assert len(client.richieste) == 2 and turno.content


def test_un_errore_del_fornitore_dentro_il_flusso_viene_ritentato():
    """Il fornitore ha gia' risposto 200: l'errore arriva come evento e l'SDK lo solleva."""
    errore = openai.APIError("upstream", request=httpx.Request("POST", "https://x.test"),
                             body={"code": 502, "message": "upstream"})
    client = ClientInStreaming(FlussoFinto(_chunks("interrotta")[:5], errore=errore),
                               FlussoFinto(_chunks("testo")))

    turno = _gateway(client).complete([], [])

    assert len(client.richieste) == 2 and turno.content


def test_il_flusso_si_chiude_anche_quando_solleva():
    rotto = FlussoFinto(_chunks("interrotta")[:5], errore=httpx.ReadError("x"))

    with pytest.raises(RuntimeError):
        _gateway(ClientInStreaming(rotto), retry_max=1).complete([], [])

    assert rotto.chiuso
