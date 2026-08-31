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

Copertura attuale (limite noto):
    Sono verificate le condizioni di uscita del ciclo — conclusione, limite di
    iterazioni, budget esaurito, servizio irraggiungibile, guasto inatteso.
    Non sono coperti: l'esecuzione reale dei tool, il retry con backoff (che
    ora vive nel gateway), l'interruzione per loop persistente e la sandbox
    Docker.
"""

from types import SimpleNamespace

import pytest

import config
from agent import Agent, AgentFailure, RunResult
from budget_guard import BudgetExceeded
from loop_detector import RilevatoreLoop


class FakeGateway:
    """Finge il confine LLM: Agent riceve soltanto il messaggio finale."""
    def __init__(self, message):
        self.message = message
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return self.message


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
    risposta = SimpleNamespace(tool_calls=None, content="Ho finito")
    agent = Agent(FakeGateway(risposta), [])

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
    chiamata = SimpleNamespace(id="1", function=SimpleNamespace(name="bash", arguments="{}"))
    risposta = SimpleNamespace(tool_calls=[chiamata], content=None)
    agent = Agent(FakeGateway(risposta), [])

    outcome = agent._esegui_iterazione([], _rilevatore(), 1)

    assert outcome == (None, None)


def test_run_restituisce_esito_e_numero_di_iterazioni():
    risposta = SimpleNamespace(tool_calls=None, content="Ho finito")
    agent = Agent(FakeGateway(risposta), [])

    result = agent.run("task")

    assert result == RunResult(status="completed", iterations=1, final_message="Ho finito")


def test_run_dichiara_il_limite_di_iterazioni():
    chiamata = SimpleNamespace(id="1", function=SimpleNamespace(name="bash", arguments="{}"))
    risposta = SimpleNamespace(tool_calls=[chiamata], content=None)
    agent = Agent(FakeGateway(risposta), [])

    result = agent.run("task", max_iterations=1)

    assert result == RunResult(
        status="max_iterations", iterations=1,
        final_message="Limite di 1 iterazioni raggiunto.",
    )


def test_agente_distingue_il_budget_esaurito_da_un_servizio_irraggiungibile():
    class GatewayConBudgetEsaurito:
        def complete(self, _messages, _tools):
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

        def complete(self, _messages, _tools):
            self.chiamate += 1
            if self.chiamate == 3:
                raise ZeroDivisionError("difetto di programmazione")
            chiamata = SimpleNamespace(
                id="1", function=SimpleNamespace(name="bash", arguments="{}"))
            return SimpleNamespace(tool_calls=[chiamata], content=None)

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
        def complete(self, _messages, _tools):
            raise RuntimeError("LLM irraggiungibile")

    result = Agent(GatewaySenzaServizio(), []).run("task", max_iterations=3)

    assert result.status == "service_unavailable"
    assert result.iterations == 1
