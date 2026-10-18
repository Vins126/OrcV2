"""Test del ciclo decisionale dell'agente.

Verificano la logica di controllo di `_esegui_iterazione`: dato ciò che il
modello risponde, l'agente decide correttamente se proseguire o fermarsi.

Nota di design (tesi):
    I test non toccano la rete. Il client reale è sostituito da un finto oggetto
    che restituisce una risposta preconfezionata, il che rende la suite
    deterministica, istantanea e a costo zero — proprietà indispensabile in un
    progetto dove ogni chiamata vera consuma token a pagamento. È l'iniezione
    delle dipendenze nel costruttore di `Agent` a rendere possibile questa
    sostituzione.

    Dal contratto esplicito (M2s.2) i finti restituiscono `AssistantTurn`, non
    piu' una imitazione della risposta OpenAI. E' la prova che l'agente non
    conosce piu' alcun SDK: se un giorno lo riconoscesse di nuovo, questi test
    smetterebbero di compilare la finzione.

Copertura attuale (limite noto):
    Sono verificate le condizioni di uscita del ciclo — conclusione, limite di
    iterazioni, budget esaurito, servizio irraggiungibile, guasto inatteso.
    Non sono coperti: l'esecuzione reale dei tool, il retry con backoff (che
    ora vive nel gateway), l'interruzione per loop persistente e la sandbox
    Docker.
"""

import json

import pytest

import config
from agent import Agent, AgentFailure, RunResult
from budget_guard import BudgetExceeded
from llm_contracts import AssistantTurn, ToolCall
from loop_detector import RilevatoreLoop
from run_status import RunStatus


class FakeGateway:
    """Finge il confine LLM: Agent riceve soltanto il messaggio finale."""
    def __init__(self, message):
        self.message = message
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return self.message


def _turno_con_tool(name="bash", arguments="{}"):
    """Turno in cui il modello chiede uno strumento."""
    return AssistantTurn(tool_calls=(ToolCall(id="1", name=name, arguments=arguments),))


def _rilevatore():
    """Crea un rilevatore di loop con le soglie reali di configurazione.

    Returns:
        Un `RilevatoreLoop` nuovo, con soglie tali da non intervenire durante un
        test di una sola iterazione.
    """
    return RilevatoreLoop(config.ALERT_THRESHOLD, config.LOOP_THRESHOLD)


def test_agente_finisce_senza_tool():
    """Una risposta a parole chiude il task.

    È la condizione di terminazione naturale del ciclo ReAct: assenza di
    `tool_calls` significa che il modello considera il compito concluso.
    """
    # L'LLM risponde a parole (niente tool_calls) -> il task è concluso
    agent = Agent(FakeGateway(AssistantTurn(content="Ho finito")), [])

    outcome = agent._esegui_iterazione([], _rilevatore(), 1)

    assert outcome == ("completed", "Ho finito")


def test_agente_continua_con_tool():
    """Una richiesta di tool mantiene vivo il ciclo.

    Il tool richiesto (`bash`) non è registrato, perché l'agente è costruito con
    lista vuota: l'esecuzione fallisce e produce un'osservazione di errore, ma il
    ciclo prosegue. È la verifica implicita del principio per cui gli errori non
    interrompono il task, ma vi rientrano come informazione.
    """
    # L'LLM chiede un tool -> il task deve continuare
    agent = Agent(FakeGateway(_turno_con_tool()), [])

    outcome = agent._esegui_iterazione([], _rilevatore(), 1)

    assert outcome == (None, None)


def test_run_restituisce_esito_e_numero_di_iterazioni():
    agent = Agent(FakeGateway(AssistantTurn(content="Ho finito")), [])

    result = agent.run("task")

    assert result == RunResult(status=RunStatus.COMPLETED, iterations=1, final_message="Ho finito")


def test_run_dichiara_il_limite_di_iterazioni():
    agent = Agent(FakeGateway(_turno_con_tool()), [])

    result = agent.run("task", max_iterations=1)

    assert result == RunResult(
        status=RunStatus.MAX_ITERATIONS, iterations=1,
        final_message="Limite di 1 iterazioni raggiunto.",
    )


def test_agente_distingue_il_budget_esaurito_da_un_servizio_irraggiungibile():
    class GatewayConBudgetEsaurito:
        def complete(self, messages, tools):
            raise BudgetExceeded("budget esaurito")

    outcome = Agent(GatewayConBudgetEsaurito(), [])._esegui_iterazione([], _rilevatore(), 1)

    assert outcome[0] == "budget_exhausted"


def test_un_errore_inatteso_conserva_le_iterazioni_gia_svolte():
    """Un guasto non azzera il conteggio del lavoro gia' fatto.

    Senza questo, una run caduta alla terza iterazione verrebbe archiviata
    come "0 iterazioni": il report mostrerebbe un costo per iterazione nullo
    pur in presenza di spesa registrata, e il dato finirebbe cosi' nel
    dataset del flywheel.
    """
    class GatewayCheSiRompeAllaTerza:
        def __init__(self):
            self.chiamate = 0

        def complete(self, messages, tools):
            self.chiamate += 1
            if self.chiamate == 3:
                raise ZeroDivisionError("difetto di programmazione")
            return _turno_con_tool()

    agent = Agent(GatewayCheSiRompeAllaTerza(), [])

    with pytest.raises(AgentFailure) as errore:
        agent.run("task", max_iterations=10)

    assert errore.value.iterations == 3
    assert errore.value.cause_type == "ZeroDivisionError"
    assert isinstance(errore.value.__cause__, ZeroDivisionError)


def test_gli_esiti_previsti_non_diventano_guasti():
    """Budget e servizio irraggiungibile restano esiti, non eccezioni.

    Sono terminazioni volute: se finissero in `AgentFailure` il ledger le
    archivierebbe come difetti del programma invece che come informazione
    sperimentale.
    """
    class GatewaySenzaServizio:
        def complete(self, messages, tools):
            raise RuntimeError("LLM irraggiungibile")

    result = Agent(GatewaySenzaServizio(), []).run("task", max_iterations=3)

    assert result.status == "service_unavailable"
    assert result.iterations == 1


# ── Persistenza: l'agente ricorda gli incarichi precedenti ────────────────

class GatewayRegistratore:
    """Gateway che risponde a parole e conserva una COPIA di cio' che riceve.

    Serve la copia: `Agent` modifica la conversazione sul posto, quindi una
    semplice referenza mostrerebbe, dopo, uno stato diverso da quello visto
    dal gateway al momento della chiamata.
    """

    def __init__(self):
        self.viste = []

    def complete(self, messages, tools):
        self.viste.append(list(messages))
        return AssistantTurn(content=f"risposta {len(self.viste)}")


def test_la_conversazione_non_riparte_da_zero_a_ogni_incarico():
    """Il secondo task si accoda a cio' che l'agente ha gia' detto e fatto."""
    gateway = GatewayRegistratore()
    agent = Agent(gateway, [])

    agent.run("primo task")
    agent.run("secondo task")

    ruoli_e_testi = [(m["role"] if isinstance(m, dict) else "assistant",
                      m["content"] if isinstance(m, dict) else m.content)
                     for m in gateway.viste[1]]
    assert ruoli_e_testi[1:] == [
        ("user", "primo task"),
        ("assistant", "risposta 1"),
        ("user", "secondo task"),
    ]


def test_il_prompt_di_sistema_compare_una_volta_sola():
    gateway = GatewayRegistratore()
    agent = Agent(gateway, [])

    agent.run("primo")
    agent.run("secondo")
    agent.run("terzo")

    sistema = [m for m in agent.messages if isinstance(m, dict) and m["role"] == "system"]
    assert len(sistema) == 1


def test_la_risposta_finale_entra_nella_storia():
    """Senza, l'agente non ricorderebbe cosa ha concluso per l'incarico."""
    agent = Agent(GatewayRegistratore(), [])

    agent.run("task")

    assert agent.messages[-1].content == "risposta 1"


def test_un_agente_nuovo_non_ha_storia():
    assert Agent(GatewayRegistratore(), []).messages == []


def test_il_rilevatore_di_loop_riparte_a_ogni_incarico():
    """Il suo stato e' dell'esecuzione corrente, non della vita dell'agente.

    Se sopravvivesse, le ripetizioni di un incarico si sommerebbero a quelle
    del successivo e fermerebbero un agente che sta facendo cose diverse.
    """
    chiamata = ToolCall(id="1", name="bash", arguments="{}")

    class Gateway:
        def __init__(self):
            self.n = 0

        def complete(self, messages, tools):
            self.n += 1
            return AssistantTurn(tool_calls=(chiamata,))

    agent = Agent(Gateway(), [])

    primo = agent.run("primo", max_iterations=config.LOOP_THRESHOLD - 1)
    secondo = agent.run("secondo", max_iterations=config.LOOP_THRESHOLD - 1)

    assert primo.status == secondo.status == "max_iterations"


# ── Storia persistente dopo un incarico finito male ───────────────────────

class _ToolFinto:
    """Tool che restituisce cio' che gli si dice, per provocare guasti mirati."""
    schema: dict = {}

    def __init__(self, nome, esito):
        self.name, self.esito = nome, esito

    def execute(self, args):
        return self.esito


class _GatewayRegistratore:
    """Risponde a parole e conserva una copia della conversazione ricevuta."""

    def __init__(self):
        self.viste = []

    def complete(self, messages, tools):
        self.viste.append(list(messages))
        return AssistantTurn(content="fatto")


def _ruoli(messaggi):
    return [m["role"] if isinstance(m, dict) else "assistant" for m in messaggi]


def test_un_guasto_a_meta_dei_tool_non_lascia_richieste_senza_risposta():
    """Se `json.dumps` fallisce sul secondo tool, resta una richiesta orfana.

    Il fornitore rifiuta una conversazione in cui un `tool_call` non ha
    risposta: senza riparazione, ogni incarico successivo fallirebbe.
    """
    class GatewayDueTool:
        def complete(self, messages, tools):
            return AssistantTurn(tool_calls=(
                ToolCall(id="a", name="ok", arguments="{}"),
                ToolCall(id="b", name="rotto", arguments="{}"),
            ))

    agent = Agent(GatewayDueTool(), [
        _ToolFinto("ok", {"fatto": True}),
        _ToolFinto("rotto", object()),     # non serializzabile in JSON
    ])
    with pytest.raises(AgentFailure):
        agent.run("primo", max_iterations=3)
    assert _ruoli(agent.messages) == ["system", "user", "assistant", "tool"]

    gateway = _GatewayRegistratore()
    agent.llm = gateway
    agent.run("secondo")

    inviata = gateway.viste[0]
    risposte = {m["tool_call_id"]: m for m in inviata
                if isinstance(m, dict) and m["role"] == "tool"}
    assert set(risposte) == {"a", "b"}
    assert json.loads(risposte["a"]["content"]) == {"fatto": True}
    assert "interrotta" in json.loads(risposte["b"]["content"])["error"]
    assert _ruoli(inviata)[-2:] == ["tool", "user"]


def test_dopo_uno_stop_alla_prima_iterazione_non_ci_sono_due_utenti_di_fila():
    """Budget esaurito prima della prima risposta: la storia finisce con l'utente."""
    class GatewayAlLimite:
        def complete(self, messages, tools):
            raise BudgetExceeded("tetto")

    agent = Agent(GatewayAlLimite(), [])
    assert agent.run("primo").status == "budget_exhausted"

    gateway = _GatewayRegistratore()
    agent.llm = gateway
    agent.run("secondo")

    ruoli = _ruoli(gateway.viste[0])
    assert ruoli == ["system", "user", "assistant", "user"]
    assert all(a != b for a, b in zip(ruoli, ruoli[1:]))


def test_una_storia_coerente_non_viene_toccata():
    """Dopo un incarico concluso la riparazione non aggiunge nulla."""
    gateway = _GatewayRegistratore()
    agent = Agent(gateway, [])
    agent.run("primo")
    agent.run("secondo")

    assert _ruoli(gateway.viste[1]) == ["system", "user", "assistant", "user"]
