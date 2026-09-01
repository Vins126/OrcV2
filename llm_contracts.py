"""Contratti minimi tra il ciclo ReAct e l'infrastruttura LLM.

Questo modulo non importa SDK, configurazione o accounting: l'`Agent` puo'
quindi essere importato e testato senza configurare un provider reale.

Nota di design (tesi):
    Fino a M2s.1 il contratto fra gateway e agente era **implicito**: l'agente
    leggeva `msg.tool_calls[i].function.name`, cioe' la forma del messaggio
    dell'SDK OpenAI. Funzionava finche' il provider era uno solo, e nascondeva
    una dipendenza che il resto dell'architettura si era data cura di
    eliminare.

    Con un secondo fornitore la finzione cade: Anthropic restituisce blocchi
    `tool_use`, non `tool_calls`. Il contratto va quindi dichiarato — e la
    conversione diventa responsabilita' del gateway, che e' l'unico oggetto a
    conoscere il proprio provider. L'agente lavora su tipi del progetto e non
    sa piu' chi gli abbia risposto.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    """Una richiesta di strumento, nella forma del progetto.

    Attributes:
        id: identificatore assegnato dal provider. Serve ad associare
            l'osservazione prodotta dal tool alla richiesta che l'ha generata:
            senza, il modello non saprebbe quale risultato appartiene a quale
            chiamata quando ne richiede piu' d'una nello stesso turno.
        name: nome del tool richiesto.
        arguments: argomenti **come stringa JSON grezza**, non come dizionario.
            Si conservano nella forma prodotta dal modello per due ragioni: il
            rilevatore di loop confronta le firme testuali, e un JSON
            malformato dev'essere un'osservazione di errore per il modello, non
            un'eccezione che interrompe il ciclo.
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AssistantTurn:
    """Cio' che il modello ha prodotto in un turno.

    E' l'unica cosa che il gateway restituisce all'agente: niente oggetti
    dell'SDK, niente `usage`, niente costi. Il gateway ha gia' misurato e
    contabilizzato prima di arrivare qui.

    Attributes:
        content: testo della risposta, se il modello ha risposto a parole.
        tool_calls: strumenti richiesti. Vuoto significa che il modello
            considera il compito concluso: e' la condizione di terminazione
            del ciclo ReAct.
    """

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ChatGateway(Protocol):
    """Servizio capace di produrre il prossimo turno del modello."""

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> AssistantTurn:
        """Restituisce il turno prodotto dal modello, o solleva un errore terminale."""
        ...
