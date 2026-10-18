"""Un tentativo interrotto costa, e il budget lo deve sapere.

Nota di design (tesi):
    Il gateway registrava soltanto le risposte arrivate: un flusso caduto a meta'
    non lasciava traccia nei conti, anche se il fornitore aveva gia' fatturato
    quanto generato. Con piu' tentativi la spesa vera poteva superare di molto il
    tetto: tetto 0,10 dollari, speso 0,09, un primo tentativo interrotto dopo 0,06
    e un secondo da 0,06, il ledger vede 0,15 e la spesa e' 0,21.

    Due misure, entrambe provate qui:
      1. il budget si controlla **a ogni tentativo**, non una volta sola;
      2. un tentativo interrotto diventa un record di consumo con il costo letto
         da `GET /generation`, e un evento con l'id della generazione.
    La prenotazione del caso peggiore e' rimandata a M3.4 (richiede un
    `max_tokens` per modello), decisione D25.
"""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import httpx
import pytest
from openai.types.chat import ChatCompletionChunk

from budget_guard import BudgetExceeded, BudgetGuard
from generation_lookup import OpenRouterGenerationLookup
from llm_contracts import GenerationCost
from llm_gateway import OpenAIChatGateway
from tests.test_llm_gateway import ContabileFinto, EventSink

FIXTURES = Path(__file__).parent / "fixtures" / "streaming"
ID_INTERROTTA = "gen-1791982251-p32DgDkO5xwptbSqqqJM"


def _chunks(nome):
    risultato = []
    for riga in (FIXTURES / f"{nome}.jsonl").read_text().splitlines():
        linea = json.loads(riga)["line"]
        if linea.startswith("data:") and "[DONE]" not in linea:
            risultato.append(ChatCompletionChunk.model_validate(json.loads(linea[5:])))
    return risultato


class Flusso:
    def __init__(self, chunks, errore=None):
        self.chunks, self.errore = chunks, errore

    def __iter__(self):
        yield from self.chunks
        if self.errore is not None:
            raise self.errore

    def close(self):
        pass


class Client:
    def __init__(self, *flussi):
        self.flussi, self.chiamate = list(flussi), 0
        self.chat = NS(completions=NS(create=self._crea))

    def _crea(self, **_kwargs):
        self.chiamate += 1
        return self.flussi.pop(0)


class ContabileSomma(ContabileFinto):
    """Somma davvero i costi registrati: serve a vedere il budget salire."""

    def register(self, record):
        record.cost = record.reported_cost or 0.0
        self.records.append(record)
        return record.cost

    @property
    def total_cost(self):
        return sum(r.cost for r in self.records)


class Lookup:
    """Lookup finto: ricorda gli id chiesti e risponde con un costo fisso (o `None`)."""

    def __init__(self, costo: float | None = 0.002, errore=None):
        self.costo, self.errore, self.chiesti = costo, errore, []

    def __call__(self, generation_id):
        self.chiesti.append(generation_id)
        if self.errore:
            raise self.errore
        if self.costo is None:
            return None
        return GenerationCost(generation_id, self.costo, prompt_tokens=500,
                              completion_tokens=1900, reasoning_tokens=1900)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr("llm_gateway.time.sleep", lambda _s: None)


def _gateway(client, contabile=None, **kwargs):
    kwargs.setdefault("retry_max", 3)
    return OpenAIChatGateway(client, "m", contabile or ContabileSomma(), stream=True, **kwargs)


# -- Il budget a ogni tentativo ------------------------------------------------

def test_dopo_un_tentativo_interrotto_che_ha_esaurito_il_budget_non_parte_il_successivo():
    contabile, events = ContabileSomma(), EventSink()
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("testo")))
    gateway = _gateway(client, contabile, generation_lookup=Lookup(costo=0.002),
                       budget_guard=BudgetGuard(0.001), event_sink=events)

    with pytest.raises(BudgetExceeded):
        gateway.complete([], [])

    assert client.chiamate == 1                           # il secondo non e' partito
    assert "budget_exhausted" in [tipo for tipo, _ in events.events]


def test_il_budget_si_controlla_anche_prima_del_primo_tentativo():
    client = Client(Flusso(_chunks("testo")))
    contabile = ContabileSomma()
    contabile.records.append(NS(cost=0.01, reported_cost=0.01))
    gateway = _gateway(client, contabile, budget_guard=BudgetGuard(0.01))

    with pytest.raises(BudgetExceeded):
        gateway.complete([], [])

    assert client.chiamate == 0


# -- Il tentativo interrotto diventa un record ------------------------------------

def test_un_tentativo_interrotto_entra_nei_conti_con_il_costo_riletto():
    contabile = ContabileSomma()
    lookup = Lookup(costo=0.0023796)
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("una_tool_call")))
    gateway = _gateway(client, contabile, generation_lookup=lookup)

    gateway.complete([], [])

    assert lookup.chiesti == [ID_INTERROTTA]
    interrotto, riuscito = contabile.records
    assert (interrotto.status, interrotto.request_id, interrotto.attempt) == ("interrupted", ID_INTERROTTA, 1)
    assert interrotto.reported_cost == pytest.approx(0.0023796)
    assert interrotto.quantities == {"input_tokens": 500, "output_tokens": 1900}
    assert interrotto.reasoning_tokens == 1900
    assert riuscito.attempt == 2 and riuscito.status == "succeeded"
    assert contabile.total_cost == pytest.approx(0.0023796 + 0.00018678)


def test_l_interruzione_lascia_un_evento_con_l_id_e_cio_che_era_arrivato():
    events = EventSink()
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=Lookup(), event_sink=events).complete([], [])

    tipo, dettagli = events.events[0]
    assert tipo == "stream_interrupted"
    assert dettagli["generation_id"] == ID_INTERROTTA
    assert dettagli["attempt"] == 1
    assert dettagli["chunks"] == 40 and dettagli["reasoning_chars"] > 7000
    assert dettagli["max_gap_s"] >= 0
    assert "finish_reason" in dettagli["reason"]


def test_l_evento_non_contiene_il_testo_dell_errore_del_fornitore():
    """Per i dati diagnostici vale la stessa regola degli altri eventi: mai il testo remoto."""
    import openai
    errore = openai.APIError("segreto", request=httpx.Request("POST", "https://x.test"),
                             body={"code": 502, "message": "testo remoto riservato"})
    events = EventSink()
    client = Client(Flusso(_chunks("interrotta")[:5], errore=errore), Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=Lookup(), event_sink=events).complete([], [])

    dettagli = events.events[0][1]
    assert dettagli["provider_error_code"] == 502
    assert "riservato" not in json.dumps(events.events)


def test_una_connessione_caduta_a_meta_flusso_ha_l_id_e_si_riconcilia():
    lookup = Lookup()
    client = Client(Flusso(_chunks("interrotta")[:5], errore=httpx.ReadError("caduta")),
                    Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=lookup).complete([], [])

    assert lookup.chiesti == [ID_INTERROTTA]


def test_se_il_costo_non_si_trova_resta_un_evento_e_i_tentativi_proseguono():
    contabile, events = ContabileSomma(), EventSink()
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("testo")))

    _gateway(client, contabile, generation_lookup=Lookup(costo=None), event_sink=events).complete([], [])

    assert [tipo for tipo, _ in events.events] == ["stream_interrupted", "interrupted_cost_unknown"]
    assert events.events[1][1]["generation_id"] == ID_INTERROTTA
    assert [r.status for r in contabile.records] == ["succeeded"]


def test_un_lookup_che_solleva_non_ferma_la_run():
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("testo")))

    turno = _gateway(client, generation_lookup=Lookup(errore=RuntimeError("giu'"))).complete([], [])

    assert turno.content


def test_senza_lookup_l_evento_c_e_ma_i_conti_non_cambiano():
    contabile, events = ContabileSomma(), EventSink()
    client = Client(Flusso(_chunks("interrotta")), Flusso(_chunks("testo")))

    _gateway(client, contabile, event_sink=events).complete([], [])

    assert [tipo for tipo, _ in events.events] == ["stream_interrupted", "interrupted_cost_unknown"]
    assert len(contabile.records) == 1


def test_senza_chunk_e_senza_header_non_c_e_un_id_da_riconciliare():
    """Senza nessuna fonte per l'id non si puo' chiedere il costo: resta l'evento `stream_interrupted`."""
    lookup = Lookup()
    client = Client(Flusso([]), Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=lookup).complete([], [])

    assert lookup.chiesti == []


class FlussoConHeader(Flusso):
    """Come lo stream dell'SDK: espone la risposta HTTP, con l'header `X-Generation-Id`.

    Prova dal vivo del 18 ott 2026: l'header c'e' sempre, coincide con l'id del primo
    chunk, e una generazione chiusa prima del primo chunk puo' essere fatturata (MiniMax m3).
    """

    def __init__(self, chunks, errore=None, id_header="gen-dall-header"):
        super().__init__(chunks, errore)
        self.response = httpx.Response(200, headers={"X-Generation-Id": id_header})


def test_un_flusso_chiuso_prima_del_primo_chunk_si_riconcilia_con_l_id_dell_header():
    contabile, lookup = ContabileSomma(), Lookup(costo=0.0004)
    client = Client(FlussoConHeader([]), Flusso(_chunks("testo")))

    _gateway(client, contabile, generation_lookup=lookup).complete([], [])

    assert lookup.chiesti == ["gen-dall-header"]
    assert [r.status for r in contabile.records][0] == "interrupted"
    assert contabile.records[0].reported_cost == pytest.approx(0.0004)


def test_una_connessione_caduta_prima_del_primo_chunk_si_riconcilia_con_l_id_dell_header():
    lookup = Lookup()
    client = Client(FlussoConHeader([], errore=httpx.ReadError("caduta")), Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=lookup).complete([], [])

    assert lookup.chiesti == ["gen-dall-header"]


def test_se_e_arrivato_un_chunk_vale_il_suo_id():
    """Coincidono nella prova dal vivo; se mai divergessero, l'id del chunk e' quello gia' usato finora."""
    lookup = Lookup()
    primi = _chunks("testo")[:1]
    client = Client(FlussoConHeader(primi, errore=httpx.ReadError("caduta"), id_header="altro"),
                    Flusso(_chunks("testo")))

    _gateway(client, generation_lookup=lookup).complete([], [])

    assert lookup.chiesti == [primi[0].id]


def test_un_fornitore_che_non_fattura_non_cambia_i_conti():
    """Opus, chiuso subito, risponde $0: il record c'e' ma il totale non sale."""
    contabile = ContabileSomma()
    client = Client(FlussoConHeader([]), Flusso(_chunks("testo")))

    _gateway(client, contabile, generation_lookup=Lookup(costo=0.0)).complete([], [])

    assert contabile.records[0].reported_cost == 0.0


def test_la_fabbrica_collega_la_rilettura_del_costo_al_gateway_di_openrouter(monkeypatch, tmp_path):
    from accounting import ModelRegistry
    from agent_factory import AgentFactory
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "chiave-fittizia")
    fabbrica = AgentFactory(ModelRegistry.from_file("models.toml"), runs_root=tmp_path / "r",
                            workspaces_root=tmp_path / "w", tools_builder=lambda p, **_: [])

    gateway = fabbrica.build("worker").gateway

    assert isinstance(gateway.generation_lookup, OpenRouterGenerationLookup)


# -- rilievi della revisione del 17 ott -------------------------------------

def test_un_errore_insolito_durante_il_flusso_riconcilia_il_costo_e_non_ritenta():
    """Ne' rete ne' API (per esempio un evento malformato): il costo va nei conti, e non si ripete
    una chiamata che potrebbe fallire allo stesso modo spendendo ancora."""
    contabile, events, lookup = ContabileSomma(), EventSink(), Lookup(costo=0.003)
    primi = _chunks("testo")[:1]
    client = Client(Flusso(primi, errore=ValueError("evento SSE malformato")), Flusso(_chunks("testo")))
    gateway = _gateway(client, contabile, generation_lookup=lookup, event_sink=events)

    with pytest.raises(RuntimeError):
        gateway.complete([], [])

    assert client.chiamate == 1                               # nessun nuovo tentativo
    assert lookup.chiesti == [primi[0].id]                     # costo riletto
    assert contabile.total_cost == pytest.approx(0.003)
    assert "stream_interrupted" in [tipo for tipo, _ in events.events]


def test_token_negativi_da_generation_non_rompono_la_run():
    """Un dato impossibile vale come costo non leggibile: evento, non un errore che esce dal gateway."""
    risposta = httpx.Response(200, json={"data": {"total_cost": 0.001, "tokens_prompt": -5,
                                                   "tokens_completion": 10}})
    client = httpx.Client(transport=httpx.MockTransport(lambda richiesta: risposta))
    lookup = OpenRouterGenerationLookup("k", "https://x/api/v1", client=client, sleep=lambda s: None)

    assert lookup("gen-1") is None
