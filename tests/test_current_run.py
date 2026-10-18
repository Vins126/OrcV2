"""Scelta (iii): un solo punto di collegamento fra l'agente e l'incarico in corso.

Prima, a ogni incarico, si ricollegavano a mano contabile e gateway (due righe da non
dimenticare); con l'esecutore Docker sarebbero state tre. Ora gateway, contabile e
strumenti ricevono una volta sola, alla costruzione, lo stesso `CurrentRun`, e a ogni
incarico si ricollega solo lui.
"""

import json

import pytest

import campaign
from accounting.current_run import CurrentRun
from accounting.errors import NoActiveRun
from accounting.ledger import RunLedger
from accounting.record import UsageRecord
from tests.test_agent_factory import ClientOpenAIFinto, ReporterMuto


def _eventi(ledger):
    percorso = ledger.run_dir / "events.jsonl"
    if not percorso.exists():
        return []
    return [json.loads(r) for r in percorso.read_text().splitlines()]


# -- l'oggetto da solo -------------------------------------------------------

def test_inoltra_eventi_e_consumi_al_ledger_collegato(tmp_path):
    corrente = CurrentRun()
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")
    corrente.attach(ledger)

    corrente.append_event("prova", {"x": 1})
    corrente.append_usage(UsageRecord(model="m", quantities={"input_tokens": 1}, cost=0.1))

    assert [e["event_type"] for e in _eventi(ledger)] == ["prova"]
    assert (ledger.run_dir / "usage.jsonl").exists()
    assert corrente.ledger is ledger


def test_senza_incarico_scrivere_e_un_errore_parlante():
    """Un evento o un consumo fuori da un incarico andrebbe perso: meglio fermarsi subito."""
    corrente = CurrentRun()

    with pytest.raises(NoActiveRun):
        corrente.append_event("prova", {})
    with pytest.raises(NoActiveRun):
        corrente.append_usage(UsageRecord(model="m", quantities={"input_tokens": 1}))


def test_ricollegare_sposta_le_scritture_sul_nuovo_ledger(tmp_path):
    corrente = CurrentRun()
    primo = RunLedger(root=tmp_path, task="a", run_id="a")
    secondo = RunLedger(root=tmp_path, task="b", run_id="b")

    corrente.attach(primo)
    corrente.append_event("uno", {})
    corrente.attach(secondo)
    corrente.append_event("due", {})

    assert [e["event_type"] for e in _eventi(primo)] == ["uno"]
    assert [e["event_type"] for e in _eventi(secondo)] == ["due"]


# -- nella fabbrica ----------------------------------------------------------

@pytest.fixture
def fabbrica_che_annota(tmp_path, monkeypatch):
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "chiave-fittizia")
    from accounting import ModelRegistry
    from agent_factory import AgentFactory
    ricevuti = []

    def strumenti(percorso, *, event_sink):
        ricevuti.append(event_sink)
        return []

    fabbrica = AgentFactory(ModelRegistry.from_file("models.toml"), runs_root=tmp_path / "runs",
                            workspaces_root=tmp_path / "ws", tools_builder=strumenti,
                            reporter=ReporterMuto())
    return fabbrica, ricevuti


def test_gateway_contabile_e_strumenti_ricevono_lo_stesso_punto_di_collegamento(fabbrica_che_annota):
    fabbrica, ricevuti = fabbrica_che_annota

    agente = fabbrica.build("worker")

    assert len(ricevuti) == 1
    corrente = ricevuti[0]
    assert isinstance(corrente, CurrentRun)
    assert agente.current_run is corrente
    assert agente.gateway.event_sink is corrente
    assert agente.accountant.ledger is corrente


def test_a_ogni_incarico_i_consumi_finiscono_nel_ledger_di_quell_incarico(fabbrica_che_annota):
    fabbrica, _ = fabbrica_che_annota
    agente = fabbrica.build("worker")
    agente.gateway.client = ClientOpenAIFinto()

    agente.assign("primo")
    agente.assign("secondo")

    for ledger in agente.ledgers:
        assert json.loads((ledger.run_dir / "summary.json").read_text())["usage_count"] == 1
    # il gateway non viene piu' ricollegato a mano: punta sempre al collegamento unico
    assert agente.gateway.event_sink is agente.current_run


# -- gli strumenti di default lo portano all'esecutore -----------------------

def test_gli_strumenti_di_default_passano_il_collegamento_all_esecutore(tmp_path, monkeypatch):
    visti = {}

    class EsecutoreFinto:
        def __init__(self, workspace, **kwargs):
            visti.update(kwargs)

    monkeypatch.setattr("tools.DockerExecutor", EsecutoreFinto)
    corrente = CurrentRun()
    from tools import build_default_tools

    build_default_tools(str(tmp_path / "ws"), event_sink=corrente)

    assert visti["event_sink"] is corrente


def test_il_costruttore_della_campagna_passa_rete_e_collegamento(tmp_path, monkeypatch):
    visti = {}

    class EsecutoreFinto:
        def __init__(self, workspace, **kwargs):
            visti.update(kwargs)

    monkeypatch.setattr("tools.DockerExecutor", EsecutoreFinto)
    corrente = CurrentRun()

    campaign.tools_builder_for("bridge")(str(tmp_path / "ws"), event_sink=corrente)

    assert visti["event_sink"] is corrente and visti["network"] == "bridge"


# -- rilievi della revisione del 17 ott -------------------------------------

class RegistroFinto:
    def cost(self, _model, _unit, quantity, route=None):
        return quantity * 0.001


def test_senza_incarico_un_consumo_non_viene_neanche_contato():
    """Prima si contava e poi si scopriva che non c'era dove scriverlo: spesa nel totale ma in nessun ledger."""
    from accounting.ledger_accountant import LedgerAccountant
    from accounting.memory import InMemoryAccountant
    interno = InMemoryAccountant(RegistroFinto())
    contabile = LedgerAccountant(interno, CurrentRun())

    with pytest.raises(NoActiveRun):
        contabile.register(UsageRecord(model="m", quantities={"input_tokens": 10}))
    with pytest.raises(NoActiveRun):                      # anche un consumo non prezzabile
        contabile.register(UsageRecord(model="m", quantities={}, measurement_source="missing"))

    assert (interno.total_cost, interno.call_count) == (0, 0)


def test_staccare_lascia_senza_incarico(tmp_path):
    corrente = CurrentRun(RunLedger(root=tmp_path, task="t", run_id="r"))

    corrente.detach()

    assert corrente.ledger is None
    with pytest.raises(NoActiveRun):
        corrente.append_event("tardivo", {})


class ClientCheAnnota(ClientOpenAIFinto):
    """Mentre risponde, annota un evento come farebbe l'esecutore: deve finire nel ledger in corso."""

    def __init__(self, corrente):
        super().__init__()
        self.corrente = corrente

    def _crea(self, **kwargs):
        self.corrente.append_event("sandbox_wait", {"wait_s": 0.5})
        return super()._crea(**kwargs)


def test_durante_l_incarico_gli_eventi_vanno_nel_suo_ledger_e_dopo_non_si_scrive_piu(fabbrica_che_annota):
    fabbrica, ricevuti = fabbrica_che_annota
    agente = fabbrica.build("worker")
    agente.gateway.client = ClientCheAnnota(ricevuti[0])

    agente.assign("primo")
    agente.assign("secondo")

    for ledger in agente.ledgers:
        assert [e["event_type"] for e in _eventi(ledger)].count("sandbox_wait") == 1
    assert agente.current_run.ledger is None             # fra un incarico e l'altro: nessuno
    with pytest.raises(NoActiveRun):                     # un evento in ritardo non finisce in un ledger chiuso
        agente.current_run.append_event("tardivo", {})


def test_anche_un_incarico_finito_male_si_stacca(fabbrica_che_annota):
    fabbrica, _ = fabbrica_che_annota
    agente = fabbrica.build("worker")

    class Rotto:
        def __init__(self):
            from types import SimpleNamespace as NS
            self.chat = NS(completions=NS(create=self._crea))

        def _crea(self, **kwargs):
            raise KeyboardInterrupt

    agente.gateway.client = Rotto()
    with pytest.raises(KeyboardInterrupt):
        agente.assign("primo")

    assert agente.current_run.ledger is None
