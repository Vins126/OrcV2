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

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
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


class TurnOutcome(Enum):
    """Come si e' chiuso un turno del modello, uguale per ogni fornitore.

    Nota di design (tesi):
        Ogni fornitore dichiara il motivo di arresto a modo suo (`finish_reason`
        di OpenAI, `stop_reason` di Anthropic). Prima di M3.0b il gateway lo
        scartava e l'agente leggeva l'assenza di tool call come «compito
        concluso»: una risposta tagliata dal limite di token, un rifiuto o un
        errore del fornitore passavano per completamenti. Il gateway, che e'
        l'unico a conoscere il proprio fornitore, traduce il motivo in questo
        vocabolario del progetto, e l'agente decide su quello.
    """

    COMPLETE = "complete"            # il modello ha concluso a parole
    TOOL_REQUEST = "tool_request"    # il modello chiede uno o piu' strumenti
    TRUNCATED = "truncated"          # fermato dal limite di token: turno incompleto
    REFUSED = "refused"              # rifiuto o filtro dei contenuti
    ERROR = "error"                  # errore dichiarato, o motivo sconosciuto


@dataclass(frozen=True)
class AssistantTurn:
    """Cio' che il modello ha prodotto in un turno.

    E' l'unica cosa che il gateway restituisce all'agente: niente oggetti
    dell'SDK, niente `usage`, niente costi. Il gateway ha gia' misurato e
    contabilizzato prima di arrivare qui.

    Attributes:
        content: testo della risposta, se il modello ha risposto a parole.
        tool_calls: strumenti richiesti. Vuoto significa che il modello
            considera il compito concluso: ma solo se l'esito e' normale. Con un
            esito anomalo (`TRUNCATED`, `REFUSED`, `ERROR`) le tool call, se
            presenti, non vanno eseguite: potrebbero essere tagliate a meta'.
        outcome: come si e' chiuso il turno. Il default `COMPLETE` mantiene
            valido chi costruisce un turno a mano (i finti dei test); i gateway
            lo impostano sempre dal motivo di arresto del fornitore.
    """

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    outcome: TurnOutcome = TurnOutcome.COMPLETE


@dataclass(frozen=True)
class GenerationCost:
    """Cio' che il fornitore dichiara di una generazione, riletto a posteriori.

    Serve a dare un costo a un tentativo interrotto: il flusso e' caduto prima
    del chunk con l'`usage`, ma il fornitore ha comunque fatturato quanto
    generato fino a quel punto.

    Attributes:
        generation_id: identificativo della generazione presso il fornitore.
        total_cost: costo in dollari dichiarato dal fornitore.
        prompt_tokens: token di input.
        completion_tokens: token di output (il ragionamento e' gia' incluso).
        reasoning_tokens: token di ragionamento, solo per analisi.
        finish_reason: motivo di arresto dichiarato, o `None` se interrotta.
    """

    generation_id: str
    total_cost: float
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int = 0
    finish_reason: str | None = None


#: Chi sa rileggere il costo di una generazione dato il suo id. Non solleva mai:
#: se non lo trova (o non puo' chiederlo) restituisce `None`.
GenerationLookup = Callable[[str], GenerationCost | None]


class ChatGateway(Protocol):
    """Servizio capace di produrre il prossimo turno del modello."""

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> AssistantTurn:
        """Restituisce il turno prodotto dal modello, o solleva un errore terminale."""
        ...
