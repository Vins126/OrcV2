"""Ricomposizione dei chunk di uno stream `chat.completions` in una risposta intera.

Nota di design (tesi):
    Con `stream=True` la risposta arriva a pezzi. Questo modulo li ricompone in un
    oggetto con **la stessa forma** della risposta non in streaming, cosi' il resto
    del gateway (`_to_turn`) e il mapper dell'usage restano invariati.

    Perche' un assemblatore nostro e non quello dell'SDK (decisione D26): quello
    dell'SDK solleva `LengthFinishReasonError` quando il fornitore chiude con
    `length`, solleva `AssertionError` su un flusso vuoto e **non segnala** un flusso
    troncato (restituisce `finish_reason=None` e argomenti tagliati a meta'). Qui
    `length` e' uno stato da riportare, e la troncatura e' un errore.

    Lavora su dizionari (il JSON dei chunk), non su oggetti dell'SDK: i test
    lo alimentano con i flussi veri catturati da un fornitore.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class StreamStats:
    """Cosa e' arrivato finora: serve a descrivere un'interruzione e a misurare gli stalli.

    Attributes:
        chunk_count: chunk ricevuti.
        reasoning_chars: caratteri di ragionamento ricevuti.
        content_chars: caratteri di testo della risposta ricevuti.
        tool_fragments: frammenti di tool call ricevuti.
        max_gap_s: intervallo piu' lungo fra due chunk consecutivi, in secondi.
    """

    chunk_count: int = 0
    reasoning_chars: int = 0
    content_chars: int = 0
    tool_fragments: int = 0
    max_gap_s: float = 0.0


class StreamInterrupted(RuntimeError):
    """Il flusso non e' arrivato a una conclusione valida.

    Attributes:
        reason: cosa e' mancato, in parole.
        generation_id: id della generazione, se almeno un chunk e' arrivato:
            serve a ritrovare il costo reale da `GET /generation`.
        stats: cosa era arrivato prima dell'interruzione.
        provider_error: l'errore dichiarato dal fornitore dentro il flusso, se c'e'.
        retryable: falso per un errore insolito durante la lettura (ne' rete ne' API,
            per esempio un evento malformato): il costo si rilegge comunque, ma un
            nuovo tentativo potrebbe fallire allo stesso modo spendendo ancora.
    """

    def __init__(self, reason: str, *, generation_id: str | None = None,
                 stats: StreamStats | None = None,
                 provider_error: Mapping[str, Any] | None = None,
                 retryable: bool = True):
        super().__init__(reason)
        self.reason = reason
        self.generation_id = generation_id
        self.stats = stats or StreamStats()
        self.provider_error = provider_error
        self.retryable = retryable


@dataclass(frozen=True)
class AssembledFunction:
    """Nome e argomenti (JSON grezzo) di una tool call."""

    name: str
    arguments: str


@dataclass(frozen=True)
class AssembledToolCall:
    """Una tool call completa, nella forma della risposta non in streaming."""

    id: str
    function: AssembledFunction
    type: str = "function"


@dataclass(frozen=True)
class AssembledMessage:
    """Il messaggio dell'assistente ricomposto."""

    content: str | None
    tool_calls: tuple[AssembledToolCall, ...] = ()


@dataclass(frozen=True)
class AssembledChoice:
    """L'unica scelta della risposta."""

    finish_reason: str
    message: AssembledMessage
    index: int = 0


@dataclass(frozen=True)
class AssembledResponse:
    """La risposta ricomposta, con gli stessi attributi di quella non in streaming.

    Attributes:
        usage: il dizionario di consumi cosi' come l'ha mandato il fornitore, o
            `None` se non e' arrivato (il mapper lo registra come non misurato).
        stats: cosa e' arrivato e quanto in fretta (chunk, intervallo massimo).
    """

    id: str | None
    model: str | None
    provider: str | None
    choices: tuple[AssembledChoice, ...]
    usage: Mapping[str, Any] | None = None
    stats: StreamStats | None = None


@dataclass
class _ToolCallInCorso:
    """Una tool call mentre i suoi frammenti arrivano."""

    id: str | None = None
    name: str | None = None
    arguments: list[str] = field(default_factory=list)


class StreamAssembler:
    """Riceve i chunk uno alla volta e restituisce la risposta intera a flusso concluso."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        """Args:
            clock: orologio per misurare l'intervallo fra chunk; iniettato perche'
                i test non devono aspettare tempi veri.
        """
        self._clock = clock
        self._stats = StreamStats()
        self._ultimo_istante: float | None = None
        self._id: str | None = None
        self._model: str | None = None
        self._provider: str | None = None
        self._testo: list[str] = []
        self._chiamate: dict[int, _ToolCallInCorso] = {}
        self._finish_reason: str | None = None
        self._usage: Mapping[str, Any] | None = None
        self._errore: Mapping[str, Any] | None = None

    @property
    def stats(self) -> StreamStats:
        """Cosa e' arrivato finora."""
        return self._stats

    @property
    def generation_id(self) -> str | None:
        """L'id della generazione, noto dal primo chunk: serve a ritrovarne il costo."""
        return self._id

    def feed(self, chunk: Mapping[str, Any]) -> None:
        """Aggiunge un chunk (il JSON di un evento `data:`).

        Raises:
            StreamInterrupted: se un frammento di tool call non dice a quale
                chiamata appartiene.
        """
        adesso = self._clock()
        if self._ultimo_istante is not None:
            self._stats.max_gap_s = max(self._stats.max_gap_s, adesso - self._ultimo_istante)
        self._ultimo_istante = adesso
        self._stats.chunk_count += 1

        self._id = self._id or chunk.get("id")
        self._model = self._model or chunk.get("model")
        self._provider = self._provider or chunk.get("provider")
        if chunk.get("error"):
            self._errore = chunk["error"]
        if chunk.get("usage"):
            # Puo' stare in un chunk senza `choices` (OpenAI) o in una `choice`
            # vuota (OpenRouter): in ogni caso e' l'ultima parola sui consumi.
            self._usage = chunk["usage"]

        for scelta in chunk.get("choices") or ():
            if scelta.get("index", 0) != 0:
                continue
            self._leggi_delta(scelta.get("delta") or {})
            motivo = scelta.get("finish_reason")
            # Il primo `finish_reason` e' quello terminale: il chunk di usage di
            # OpenRouter lo ripete, ed e' un fotogramma di contabilita'.
            if motivo and self._finish_reason is None:
                self._finish_reason = motivo

    def _leggi_delta(self, delta: Mapping[str, Any]) -> None:
        if delta.get("content"):
            self._testo.append(delta["content"])
            self._stats.content_chars += len(delta["content"])
        if delta.get("reasoning"):
            self._stats.reasoning_chars += len(delta["reasoning"])
        for frammento in delta.get("tool_calls") or ():
            self._stats.tool_fragments += 1
            indice = frammento.get("index")
            if indice is None:
                # Senza index non si sa a quale chiamata appartiene: indovinare
                # fonderebbe chiamate diverse in una sola.
                raise StreamInterrupted(
                    "frammento di tool call senza index", generation_id=self._id,
                    stats=self._stats)
            chiamata = self._chiamate.setdefault(indice, _ToolCallInCorso())
            if frammento.get("id") and chiamata.id is None:
                chiamata.id = frammento["id"]
            funzione = frammento.get("function") or {}
            if funzione.get("name") and chiamata.name is None:
                chiamata.name = funzione["name"]
            if funzione.get("arguments"):
                chiamata.arguments.append(funzione["arguments"])

    def result(self) -> AssembledResponse:
        """Restituisce la risposta intera, o solleva `StreamInterrupted`.

        Un flusso e' concluso solo se ha un `finish_reason` e nessun errore del
        fornitore: senza, quello che e' arrivato e' un pezzo, non una risposta, e
        le tool call potrebbero essere tagliate a meta'.

        Raises:
            StreamInterrupted: flusso vuoto, errore dichiarato dal fornitore,
                `finish_reason` assente, o tool call senza id o nome in un flusso
                che dichiara di aver concluso.
        """
        def interrotto(motivo: str) -> StreamInterrupted:
            return StreamInterrupted(
                motivo, generation_id=self._id, stats=self._stats,
                provider_error=self._errore)

        if self._errore:
            raise interrotto("evento di errore del fornitore dentro il flusso")
        if self._stats.chunk_count == 0:
            raise interrotto("flusso vuoto")
        if self._finish_reason is None:
            raise interrotto("flusso chiuso senza finish_reason")

        in_ordine = [self._chiamate[i] for i in sorted(self._chiamate)]
        complete = [c for c in in_ordine if c.id and c.name]
        if len(complete) != len(in_ordine) and self._finish_reason in ("stop", "tool_calls"):
            raise interrotto("tool call senza id o nome")
        # Con `length` (o un altro motivo anomalo) le chiamate incomplete si
        # scartano: il taglio e' gia' dichiarato e l'agente non eseguira' nulla.

        messaggio = AssembledMessage(
            content="".join(self._testo) or None,
            tool_calls=tuple(
                AssembledToolCall(
                    id=str(c.id),
                    function=AssembledFunction(
                        name=str(c.name),
                        # Come nella risposta intera: nessun argomento e' `{}`.
                        arguments="".join(c.arguments) or "{}"))
                for c in complete),
        )
        return AssembledResponse(
            id=self._id, model=self._model, provider=self._provider,
            choices=(AssembledChoice(finish_reason=self._finish_reason, message=messaggio),),
            usage=self._usage, stats=replace(self._stats),
        )
