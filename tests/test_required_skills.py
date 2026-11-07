"""Test delle skill obbligatorie (P44-D1, P45-D1, 7 nov 2026).

Ogni agente della campagna ha un elenco di skill che deve caricare con `load_skill`:
il prompt di sistema lo dice (regola), e l'agente rifiuta ogni altro strumento e la
risposta finale finche' l'elenco non e' completo (blocco). Senza elenco l'agente si
comporta come prima: lo usano `main.py` e i test esistenti.
"""

import json

import pytest

from agent import SYSTEM_PROMPT, Agent
from agent_factory import AgentFactory
from llm_contracts import AssistantTurn, ToolCall
from accounting import ModelRegistry
from run_status import RunStatus
from tools import SKILLS_MANIFEST
from tools.load_skill import (
    REQUIRED_SKILLS_PLANNER,
    REQUIRED_SKILLS_SINGLE,
    REQUIRED_SKILLS_WORKER,
    SkillCatalogError,
    load_catalog,
)

DESIGN = ("frontend-design", "design-taste-frontend")


class LoadSkillFinto:
    """Imita `LoadSkillTool`: nome, catalogo e un esito per nome."""

    name = "load_skill"
    schema: dict = {}

    def __init__(self, nomi=("frontend-design", "design-taste-frontend", "webapp-testing",
                             "verification-before-completion"), falliscono=()):
        self.catalog = {nome: object() for nome in nomi}
        self.falliscono = set(falliscono)
        self.chiamate = []

    def execute(self, args):
        self.chiamate.append(args.get("name"))
        if args.get("name") in self.falliscono:
            return {"error": "impossibile caricare la skill"}
        return {"folder": f"/opt/skills/{args['name']}", "content": "istruzioni"}


class ToolFinto:
    schema: dict = {}

    def __init__(self, nome="write_file"):
        self.name = nome
        self.chiamate = 0

    def execute(self, args):
        self.chiamate += 1
        return {"status": "ok"}


class GatewayCopione:
    """Restituisce i turni nell'ordine dato e conserva le conversazioni ricevute."""

    def __init__(self, *turni):
        self.turni = list(turni)
        self.ricevuti = []

    def complete(self, messages, tools):
        self.ricevuti.append(list(messages))
        return self.turni.pop(0)


class Registro:
    def __init__(self):
        self.eventi = []

    def append_event(self, event_type, details):
        self.eventi.append((event_type, details))


def _carica(*nomi, ident="c"):
    return AssistantTurn(tool_calls=tuple(
        ToolCall(id=f"{ident}{i}", name="load_skill", arguments=json.dumps({"name": nome}))
        for i, nome in enumerate(nomi)))


def _scrivi(ident="w"):
    return AssistantTurn(tool_calls=(ToolCall(id=ident, name="write_file", arguments="{}"),))


def _fine(testo="fatto"):
    return AssistantTurn(content=testo)


def _risposte_tool(messaggi):
    return [m["content"] for m in messaggi if isinstance(m, dict) and m.get("role") == "tool"]


# -- Elenchi della campagna -----------------------------------------------------

def test_elenchi_fissati_dalla_decisione_p45_d1():
    assert REQUIRED_SKILLS_SINGLE == ("frontend-design", "design-taste-frontend",
                                      "webapp-testing", "verification-before-completion")
    assert REQUIRED_SKILLS_PLANNER == DESIGN
    assert REQUIRED_SKILLS_WORKER == ("frontend-design", "webapp-testing",
                                      "verification-before-completion")


def test_ogni_skill_obbligatoria_e_nel_catalogo_della_campagna():
    catalogo = {voce.name for voce in load_catalog(SKILLS_MANIFEST)}
    for elenco in (REQUIRED_SKILLS_SINGLE, REQUIRED_SKILLS_PLANNER, REQUIRED_SKILLS_WORKER):
        assert set(elenco) <= catalogo


def test_il_braccio_singolo_ha_le_stesse_skill_che_c_divide_fra_planner_e_worker():
    assert set(REQUIRED_SKILLS_SINGLE) == set(REQUIRED_SKILLS_PLANNER) | set(REQUIRED_SKILLS_WORKER)


# -- Regola nel prompt ----------------------------------------------------------

def test_la_regola_nomina_le_skill_nel_prompt_di_sistema():
    gateway = GatewayCopione(_carica(*DESIGN), _fine())
    Agent(gateway, [LoadSkillFinto()], required_skills=DESIGN).run("task", max_iterations=3)

    sistema = gateway.ricevuti[0][0]["content"]
    assert sistema.startswith(SYSTEM_PROMPT)
    assert "load_skill" in sistema.removeprefix(SYSTEM_PROMPT)
    for nome in DESIGN:
        assert nome in sistema.removeprefix(SYSTEM_PROMPT)


def test_senza_elenco_il_prompt_di_sistema_resta_quello_di_prima():
    gateway = GatewayCopione(_fine())
    Agent(gateway, []).run("task", max_iterations=2)

    assert gateway.ricevuti[0][0]["content"] == SYSTEM_PROMPT


# -- Blocco sugli strumenti -----------------------------------------------------

def test_un_altro_strumento_e_rifiutato_finche_mancano_skill():
    scrittura = ToolFinto()
    gateway = GatewayCopione(_scrivi(), _carica(*DESIGN), _fine())
    agente = Agent(gateway, [LoadSkillFinto(), scrittura], required_skills=DESIGN)

    agente.run("task", max_iterations=5)

    assert scrittura.chiamate == 0
    rifiuto = json.loads(_risposte_tool(agente.messages)[0])
    for nome in DESIGN:
        assert nome in rifiuto["error"]
    assert "load_skill" in rifiuto["error"]


def test_caricate_tutte_le_skill_gli_strumenti_funzionano():
    scrittura = ToolFinto()
    gateway = GatewayCopione(_carica(*DESIGN), _scrivi(), _fine())
    Agent(gateway, [LoadSkillFinto(), scrittura], required_skills=DESIGN).run("task", max_iterations=5)

    assert scrittura.chiamate == 1


def test_una_skill_caricata_a_meta_non_basta():
    scrittura = ToolFinto()
    gateway = GatewayCopione(_carica(DESIGN[0]), _scrivi(), _carica(DESIGN[1]), _scrivi("w2"), _fine())
    agente = Agent(gateway, [LoadSkillFinto(), scrittura], required_skills=DESIGN)

    agente.run("task", max_iterations=6)

    assert scrittura.chiamate == 1
    rifiuto = json.loads(_risposte_tool(agente.messages)[1])["error"]
    assert DESIGN[1] in rifiuto and DESIGN[0] not in rifiuto


def test_un_caricamento_fallito_non_conta():
    scrittura = ToolFinto()
    caricatore = LoadSkillFinto(falliscono={DESIGN[1]})
    gateway = GatewayCopione(_carica(*DESIGN), _scrivi(), _fine(), _fine())
    agente = Agent(gateway, [caricatore, scrittura], required_skills=DESIGN)

    esito = agente.run("task", max_iterations=4)

    assert scrittura.chiamate == 0
    assert esito.status == RunStatus.MAX_ITERATIONS


def test_il_caricamento_di_skill_facoltative_e_sempre_ammesso():
    caricatore = LoadSkillFinto(nomi=(*DESIGN, "ui-ux-pro-max"))
    gateway = GatewayCopione(_carica("ui-ux-pro-max"), _carica(*DESIGN, ident="d"), _fine())
    agente = Agent(gateway, [caricatore], required_skills=DESIGN)

    esito = agente.run("task", max_iterations=4)

    assert caricatore.chiamate == ["ui-ux-pro-max", *DESIGN]
    assert esito.status == RunStatus.COMPLETED


# -- Blocco sulla risposta finale -----------------------------------------------

def test_la_risposta_finale_e_respinta_finche_mancano_skill():
    registro = Registro()
    gateway = GatewayCopione(_fine("ho finito"), _carica(*DESIGN), _fine("ora ho finito"))
    agente = Agent(gateway, [LoadSkillFinto()], event_sink=registro, required_skills=DESIGN)

    esito = agente.run("task", max_iterations=5)

    assert esito.status == RunStatus.COMPLETED
    assert esito.final_message == "ora ho finito"
    assert esito.iterations == 3
    # Il richiamo e' l'ultimo messaggio che il modello legge prima del secondo turno.
    richiamo = gateway.ricevuti[1][-1]
    assert richiamo["role"] == "user"
    for nome in DESIGN:
        assert nome in richiamo["content"]
    blocchi = [d for t, d in registro.eventi if t == "skill_gate"]
    assert blocchi == [{"missing": list(DESIGN), "at": "final_reply"}]


def test_chi_non_carica_mai_le_skill_non_chiude_come_completato():
    gateway = GatewayCopione(_fine(), _fine(), _fine())
    esito = Agent(gateway, [LoadSkillFinto()], required_skills=DESIGN).run("task", max_iterations=3)

    assert esito.status == RunStatus.MAX_ITERATIONS


def test_le_skill_caricate_valgono_anche_per_l_incarico_successivo():
    scrittura = ToolFinto()
    gateway = GatewayCopione(_carica(*DESIGN), _fine(), _scrivi(), _fine())
    agente = Agent(gateway, [LoadSkillFinto(), scrittura], required_skills=DESIGN)

    agente.run("primo", max_iterations=3)
    secondo = agente.run("secondo", max_iterations=3)

    assert scrittura.chiamate == 1
    assert secondo.status == RunStatus.COMPLETED


# -- Configurazione errata ------------------------------------------------------

def test_una_skill_obbligatoria_fuori_catalogo_e_un_errore_di_configurazione():
    with pytest.raises(SkillCatalogError, match="inesistente"):
        Agent(GatewayCopione(), [LoadSkillFinto()], required_skills=("inesistente",))


def test_skill_obbligatorie_senza_load_skill_sono_un_errore_di_configurazione():
    with pytest.raises(SkillCatalogError):
        Agent(GatewayCopione(), [ToolFinto()], required_skills=DESIGN)


# -- Fabbrica -------------------------------------------------------------------

def test_la_fabbrica_passa_l_elenco_all_agente(tmp_path, monkeypatch):
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "chiave-fittizia")
    fabbrica = AgentFactory(
        ModelRegistry.from_file("models.toml"), runs_root=tmp_path / "runs",
        workspaces_root=tmp_path / "ws", tools_builder=lambda percorso, **_: [LoadSkillFinto()])

    con = fabbrica.build("planner", required_skills=DESIGN)
    senza = fabbrica.build("planner")

    assert con.agent.required_skills == DESIGN
    assert senza.agent.required_skills == ()
