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
    Sono verificate le due condizioni di uscita principali, con lista di tool
    vuota. Non sono coperti: l'esecuzione reale dei tool, il retry con backoff,
    l'interruzione per loop persistente e la sandbox Docker.
"""

from types import SimpleNamespace

import config
from agent import Agent
from loop_detector import RilevatoreLoop


class FakeClient:
    """Finge client.chat.completions.create restituendo sempre un messaggio preconfezionato."""
    def __init__(self, message):
        """Costruisce la catena di attributi attesa dall'agente.

        Riproduce con `SimpleNamespace` la struttura annidata
        `client.chat.completions.create(...) -> .choices[0].message`, ignorando
        gli argomenti ricevuti: al test interessa solo cosa l'agente fa della
        risposta, non come la richiede.

        Args:
            message: messaggio che ogni chiamata dovrà restituire.
        """
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=message)]
                )
            )
        )


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
    agent = Agent(FakeClient(risposta), "modello-finto", [])

    continua = agent._esegui_iterazione([], _rilevatore(), 1)

    assert continua is False


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
    agent = Agent(FakeClient(risposta), "modello-finto", [])

    continua = agent._esegui_iterazione([], _rilevatore(), 1)

    assert continua is True
