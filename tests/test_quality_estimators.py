"""Gli stimatori: cosa leggono, cosa restituiscono, come sbagliano.

Nota di design (tesi):
    Un solo vincolo vale per tutti: lo stimatore vede **istruzioni e codice** e nient'altro
    (decisione D20). Nessun identificativo dell'esempio, nessun tipo di guasto, nessuna
    etichetta, nessun test. Una fuga di informazione qui renderebbe inutile ogni misura:
    per questo i test controllano le richieste vere inviate, non solo i risultati.
"""

import json
from types import SimpleNamespace as NS
from typing import Any, cast

import httpx
import pytest

from budget_guard import BudgetExceeded
from llm_contracts import AssistantTurn
from quality.dataset import Example
from quality.estimators import D1Estimator, Estimate, FrontierJudge, HeuristicEstimator, render_state

MODELLO = "EXERCISE:\n{instructions}\n\nSOLUTION:\n{solution}"
DOMANDA = "Is the solution correct for every valid input?"
CODICE = "def misura(a, b):\n    return a + b"


def _esempio(**kw):
    valori: dict[str, Any] = dict(example_id="mutante:r1:0", task_id="due-secchi", origin="mutante",
                  instructions="Measure exactly N litres.", solution=CODICE, label=0,
                  base_run_id="r1", operator="arithmetic", line=2)
    valori.update(kw)
    return Example(**valori)


# -- Cosa vede lo stimatore --------------------------------------------------------

def test_lo_stato_contiene_solo_istruzioni_e_codice():
    stato = render_state(MODELLO, _esempio())

    assert stato == f"EXERCISE:\nMeasure exactly N litres.\n\nSOLUTION:\n{CODICE}"


def test_nessuna_informazione_sull_esempio_arriva_allo_stato():
    stato = render_state(MODELLO, _esempio())

    for segreto in ("mutante", "arithmetic", "r1", "due-secchi", "label"):
        assert segreto not in stato


def test_un_modello_con_segnaposto_sconosciuti_e_un_errore():
    with pytest.raises(ValueError, match="segnaposto"):
        render_state("{instructions} {label}", _esempio())


# -- Euristica ---------------------------------------------------------------------

@pytest.mark.parametrize("codice, atteso", [
    ("def f():\n    pass", 0.05),
    ("def f():\n    raise NotImplementedError", 0.05),
    ("def f(a):\n    return a + 1", 0.5),
])
def test_l_euristica_riconosce_il_codice_non_fatto_e_per_il_resto_non_ha_opinione(codice, atteso):
    e = HeuristicEstimator().estimate(_esempio(solution=codice))

    assert (e.probability, e.error, e.cost_usd) == (atteso, None, 0.0)


# -- d1 -----------------------------------------------------------------------------

def _d1(risposta, richieste, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        richieste.append(request)
        r = risposta.pop(0) if len(risposta) > 1 else risposta[0]
        if isinstance(r, Exception):
            raise r
        return r

    kw.setdefault("url", "https://d1.test/systemone")
    return D1Estimator("d1-test", state_template=MODELLO, question=DOMANDA,
                       client=httpx.Client(transport=httpx.MockTransport(handler)),
                       sleep=lambda _s: None, **kw)


def _ok(p=0.8, **usage):
    return httpx.Response(200, json={"model": "d1", "answers": {"corretta": {"type": "noul", "noul": p}},
                                     "usage": {"input_tokens": 120, "output_tokens": 0, **usage}})


def test_d1_legge_la_probabilita_il_costo_e_i_token():
    richieste = []

    e = _d1([_ok(0.8123, cost=2.5e-06)], richieste, api_key="k", model="d1").estimate(_esempio())

    assert (e.probability, e.cost_usd, e.input_tokens, e.error) == (0.8123, 2.5e-06, 120, None)
    assert e.latency_s >= 0


def test_la_richiesta_ha_la_forma_dell_api_e_non_porta_informazioni_sull_esempio():
    richieste = []

    _d1([_ok()], richieste, api_key="chiave-segreta", model="d1").estimate(_esempio())

    (richiesta,) = richieste
    corpo = json.loads(richiesta.content)
    assert corpo["model"] == "d1"
    assert corpo["state"] == render_state(MODELLO, _esempio())
    assert corpo["questions"] == {"corretta": {"type": "noul", "instructions": DOMANDA}}
    assert richiesta.headers["Authorization"] == "Bearer chiave-segreta"
    testo = richiesta.content.decode()
    for segreto in ("mutante", "arithmetic", "due-secchi", "r1"):
        assert segreto not in testo


def test_il_locale_non_ha_ne_chiave_ne_modello():
    richieste = []

    _d1([_ok()], richieste).estimate(_esempio())

    assert "Authorization" not in richieste[0].headers
    assert "model" not in json.loads(richieste[0].content)


def test_i_criteri_viaggiano_con_le_chiavi_true_e_false():
    richieste = []

    _d1([_ok()], richieste, criteria=("correct and complete", "has a bug")).estimate(_esempio())

    domanda = json.loads(richieste[0].content)["questions"]["corretta"]
    assert domanda["criteria"] == {"true": "correct and complete", "false": "has a bug"}


@pytest.mark.parametrize("risposta", [
    httpx.Response(200, json={"answers": {}}),
    httpx.Response(200, json={"answers": {"corretta": {"noul": 1.5}}}),
    httpx.Response(200, json={"answers": {"corretta": {"noul": "boh"}}}),
    httpx.Response(200, content=b"non e' json"),
])
def test_una_risposta_non_valida_e_un_errore_e_non_una_probabilita(risposta):
    e = _d1([risposta], []).estimate(_esempio())

    assert e.probability is None and e.error


def test_su_429_e_5xx_si_ritenta_e_poi_si_riesce():
    richieste = []

    e = _d1([httpx.Response(429), httpx.Response(503), _ok(0.6)], richieste).estimate(_esempio())

    assert e.probability == 0.6 and len(richieste) == 3


def test_se_i_tentativi_finiscono_si_riporta_l_errore_con_il_codice():
    e = _d1([httpx.Response(500)], [], attempts=2).estimate(_esempio())

    assert e.probability is None and "500" in (e.error or "")


def test_un_errore_di_richiesta_non_si_ritenta():
    richieste = []

    e = _d1([httpx.Response(400, json={"error": "bad"})], richieste).estimate(_esempio())

    assert e.probability is None and "400" in (e.error or "") and len(richieste) == 1


def test_un_guasto_di_rete_e_un_errore_non_un_crollo():
    e = _d1([httpx.ConnectError("giu'")], [], attempts=1).estimate(_esempio())

    assert e.probability is None and "ConnectError" in (e.error or "")


# -- Giudice frontier ----------------------------------------------------------------

class GatewayFinto:
    contabile: Any = None

    def __init__(self, risposte):
        self.risposte, self.visti = list(risposte), []

    def complete(self, messages, tools):
        self.visti.append(messages)
        r = self.risposte.pop(0)
        if isinstance(r, BaseException):
            raise r
        self.contabile.total_cost += 0.007
        return AssistantTurn(content=r)


def _giudice(risposte):
    gateway = GatewayFinto(risposte)
    contabile = NS(total_cost=0.0)
    gateway.contabile = contabile
    return FrontierJudge("frontier", make_gateway=lambda: cast(Any, (gateway, contabile)),
                         system_prompt="Sei un revisore.", user_template=MODELLO), gateway


@pytest.mark.parametrize("testo, atteso", [
    ('{"probability": 85}', 0.85),
    ('```json\n{"probability": 7.5}\n```', 0.075),
    ('Ecco: {"probability": 100}', 1.0),
    ('{"probability": 0}', 0.0),
])
def test_il_frontier_restituisce_una_probabilita_da_0_a_100(testo, atteso):
    giudice, _ = _giudice([testo])

    e = giudice.estimate(_esempio())

    assert e.probability == pytest.approx(atteso) and e.error is None
    assert e.cost_usd == pytest.approx(0.007)


def test_il_messaggio_al_frontier_porta_solo_istruzioni_e_codice():
    giudice, gateway = _giudice(['{"probability": 50}'])

    giudice.estimate(_esempio())

    (messaggi,) = gateway.visti
    testo = json.dumps(messaggi)
    assert "Measure exactly N litres." in testo and "return a + b" in testo
    for segreto in ("mutante", "arithmetic", "due-secchi", "r1"):
        assert segreto not in testo


@pytest.mark.parametrize("testo", ["non so", '{"probability": 150}', '{"probability": -5}',
                                    '{"probability": "alta"}', ""])
def test_una_risposta_senza_probabilita_valida_e_un_errore(testo):
    giudice, _ = _giudice([testo])

    e = giudice.estimate(_esempio())

    assert e.probability is None and e.error


def test_un_gateway_che_non_risponde_e_un_errore_ma_il_tetto_di_spesa_ferma_tutto():
    giudice, _ = _giudice([RuntimeError("LLM irraggiungibile")])
    assert giudice.estimate(_esempio()).error

    giudice, _ = _giudice([BudgetExceeded("budget esaurito")])
    with pytest.raises(BudgetExceeded):
        giudice.estimate(_esempio())


def test_estimate_e_un_valore_immutabile_con_i_campi_promessi():
    e = Estimate(probability=0.3)

    assert (e.cost_usd, e.error, e.raw) == (0.0, None, None)


def test_l_errore_del_giudice_riporta_il_tipo_e_il_codice_della_causa_ma_mai_il_testo_remoto():
    """`LLM irraggiungibile` da solo non dice se e' un 503, un 429 o un guasto di rete."""
    class Http503(Exception):
        status_code = 503

    try:
        try:
            raise Http503("testo remoto riservato con dettagli")
        except Http503 as causa:
            raise RuntimeError("LLM irraggiungibile") from causa
    except RuntimeError as errore:
        giudice, _ = _giudice([errore])

    e = giudice.estimate(_esempio())

    assert e.probability is None
    assert "RuntimeError" in (e.error or "") and "Http503" in (e.error or "") and "503" in (e.error or "")
    assert "riservato" not in (e.error or "")


def test_un_402_del_fornitore_e_un_ordine_di_fermarsi_non_un_giudizio_fallito():
    """Senza credito ogni richiesta fallisce: insistere per centinaia di giudizi non serve a niente."""
    class Http402(Exception):
        status_code = 402

    try:
        try:
            raise Http402("credito")
        except Http402 as causa:
            raise RuntimeError("LLM irraggiungibile") from causa
    except RuntimeError as errore:
        giudice, _ = _giudice([errore])

    with pytest.raises(BudgetExceeded, match="credito"):
        giudice.estimate(_esempio())
