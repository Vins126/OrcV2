"""La rilettura del costo di una generazione interrotta."""

import json

import httpx

from generation_lookup import OpenRouterGenerationLookup
from llm_contracts import GenerationCost

#: Risposta vera di `GET /generation` per il caso `interrotta` della sonda (campi usati).
RISPOSTA_VERA = {"data": {
    "id": "gen-1791982251-p32DgDkO5xwptbSqqqJM", "total_cost": 0.0023796,
    "tokens_prompt": 507, "tokens_completion": 1942, "native_tokens_completion": 1942,
    "native_tokens_reasoning": 1942, "finish_reason": None, "cancelled": False, "streamed": True,
}}


def _lookup(risposte, **kwargs):
    """Un lookup con un client che risponde in sequenza; restituisce anche cosa ha visto."""
    visti, attese = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        visti.append(request)
        stato, corpo = risposte.pop(0) if len(risposte) > 1 else risposte[0]
        return httpx.Response(stato, json=corpo)

    lookup = OpenRouterGenerationLookup(
        "chiave-finta", "https://openrouter.test/api/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=attese.append, **kwargs)
    return lookup, visti, attese


def test_legge_il_costo_di_una_generazione_interrotta():
    lookup, visti, _ = _lookup([(200, RISPOSTA_VERA)])

    costo = lookup("gen-1791982251-p32DgDkO5xwptbSqqqJM")

    assert costo == GenerationCost(
        generation_id="gen-1791982251-p32DgDkO5xwptbSqqqJM", total_cost=0.0023796,
        prompt_tokens=507, completion_tokens=1942, reasoning_tokens=1942, finish_reason=None)
    assert visti[0].url.path == "/api/v1/generation"
    assert visti[0].url.params["id"] == "gen-1791982251-p32DgDkO5xwptbSqqqJM"
    assert visti[0].headers["Authorization"] == "Bearer chiave-finta"


def test_se_i_dati_non_sono_ancora_pronti_riprova_dopo_un_intervallo():
    lookup, visti, attese = _lookup([(404, {"error": {"message": "not found"}}), (200, RISPOSTA_VERA)],
                                    interval_s=5.0)

    costo = lookup("gen-x")

    assert costo is not None and costo.total_cost == 0.0023796
    assert len(visti) == 2 and attese == [5.0]


def test_se_non_arrivano_mai_si_arrende_dopo_il_numero_di_tentativi():
    lookup, visti, attese = _lookup([(404, {"error": {}})], attempts=3)

    assert lookup("gen-x") is None
    assert len(visti) == 3 and len(attese) == 2        # niente attesa dopo l'ultimo


def test_un_errore_di_autenticazione_non_si_ritenta():
    lookup, visti, _ = _lookup([(401, {"error": {}})], attempts=4)

    assert lookup("gen-x") is None
    assert len(visti) == 1


def test_una_risposta_senza_costo_valido_non_diventa_un_costo():
    for corpo in ({"data": {}}, {"data": {"total_cost": "boh"}}, {"data": {"total_cost": -1}}, {"niente": 1}):
        lookup, _, _ = _lookup([(200, corpo)], attempts=1)

        assert lookup("gen-x") is None


def test_un_guasto_di_rete_non_solleva():
    def handler(request):
        raise httpx.ConnectError("giu'")
    lookup = OpenRouterGenerationLookup(
        "k", "https://openrouter.test/api/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _s: None, attempts=2)

    assert lookup("gen-x") is None
