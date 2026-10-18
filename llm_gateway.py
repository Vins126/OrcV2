"""Confine fra il ciclo dell'agente e un provider LLM.

L'agente chiede un turno; il gateway sa come invocare il provider, misurare la
latenza e registrare il consumo. Separare queste responsabilita' evita che il
ciclo ReAct dipenda da SDK, listini o formati di usage.

Nota di design (tesi):
    Con due fornitori la parte comune si vede: budget, retry, cronometro,
    mapping e contabilita' sono identici; cambia solo *come si chiama* il
    provider e *come si traduce* cio' che risponde. Quella parte comune vive in
    `ChatGatewayBase` — non per eleganza, ma perche' duplicarla significherebbe
    dover applicare due volte ogni correzione futura sul percorso che maneggia
    denaro.
"""

import json
import logging
import socket
import time
from collections.abc import Mapping
from typing import Any, Protocol

import anthropic
import httpx
import openai

import config
from accounting.base import Accountant
from accounting.errors import InvalidUsage, RegistryError
from accounting.mappers.anthropic import AnthropicMessagesUsageMapper
from accounting.mappers.base import non_zero
from accounting.mappers.openai import OpenAIChatCompletionsUsageMapper
from accounting.record import UsageRecord
from budget_guard import BudgetExceeded, BudgetGuard, BudgetVerdict
from llm_contracts import AssistantTurn, ChatGateway, GenerationLookup, ToolCall, TurnOutcome
from stall_watchdog import StallWatchdog
from stream_assembler import StreamAssembler, StreamInterrupted

log = logging.getLogger(__name__)


def _outcome_openai(finish_reason: Any, has_tool_calls: bool) -> TurnOutcome:
    """Traduce il `finish_reason` di `chat.completions` nell'esito del progetto.

    Un motivo assente o sconosciuto e' `ERROR`: non si presume che il modello
    abbia finito. `stop` con tool call vale come richiesta di strumenti, perche'
    alcuni fornitori usano `stop` anche in quel caso; `tool_calls` senza tool
    call e' incoerente.
    """
    if finish_reason == "length":
        return TurnOutcome.TRUNCATED
    if finish_reason == "content_filter":
        return TurnOutcome.REFUSED
    if finish_reason == "stop":
        return TurnOutcome.TOOL_REQUEST if has_tool_calls else TurnOutcome.COMPLETE
    if finish_reason == "tool_calls":
        return TurnOutcome.TOOL_REQUEST if has_tool_calls else TurnOutcome.ERROR
    return TurnOutcome.ERROR


def _outcome_anthropic(stop_reason: Any, has_tool_calls: bool) -> TurnOutcome:
    """Traduce lo `stop_reason` dell'API Messages nell'esito del progetto.

    `pause_turn` e' `ERROR`: serve a riprendere un turno con strumenti lato
    server, che non usiamo.
    """
    if stop_reason in ("max_tokens", "model_context_window_exceeded"):
        return TurnOutcome.TRUNCATED
    if stop_reason == "refusal":
        return TurnOutcome.REFUSED
    if stop_reason == "tool_use":
        return TurnOutcome.TOOL_REQUEST if has_tool_calls else TurnOutcome.ERROR
    if stop_reason in ("end_turn", "stop_sequence"):
        return TurnOutcome.TOOL_REQUEST if has_tool_calls else TurnOutcome.COMPLETE
    return TurnOutcome.ERROR


class RunEventSink(Protocol):
    """Destinazione opzionale di eventi tecnici, senza dipendere dal ledger."""

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Registra un fatto della run che non e' un usage record."""


class ChatGatewayBase:
    """Parte comune a ogni gateway di chat: soldi, tempo, resilienza.

    Le sottoclassi implementano due soli metodi — come si invoca il provider e
    come si traduce la sua risposta — piu' la conversione della conversazione
    nel formato che il provider si aspetta.

    Il blocco di retry protegge esclusivamente la chiamata remota: ripetere una
    risposta gia' ricevuta per un problema locale creerebbe una seconda spesa.
    Dopo la risposta i due tipi di errore si comportano in modo opposto — un
    fallimento di **prezzatura** viene annotato e la run prosegue, perche' la
    spesa e' gia' stata sostenuta e va conservata; un errore di **codice**
    emerge subito, perche' e' un difetto da correggere.
    """

    #: Mapper usato quando il chiamante non ne impone uno.
    MAPPER: Any = None
    #: Valori di `api_provider` / `billing_provider` quando non specificati.
    DEFAULT_API_PROVIDER: str = "sconosciuto"
    DEFAULT_BILLING_PROVIDER: str | None = None
    #: Eccezioni dell'SDK che indicano un guasto transitorio.
    RETRYABLE: tuple[type[BaseException], ...] = ()

    def __init__(self, client: Any, model: str, accountant: Accountant,
                 mapper: Any = None,
                 retry_max: int = config.RETRY_MAX,
                 retry_delay: float = config.RETRY_DELAY,
                 api_provider: str | None = None,
                 billing_provider: str | None = None,
                 event_sink: RunEventSink | None = None,
                 budget_guard: BudgetGuard | None = None,
                 api_model: str | None = None,
                 generation_lookup: GenerationLookup | None = None):
        """Registra le dipendenze del gateway.

        Args:
            client: client dell'SDK, gia' costruito con le sue credenziali.
            model: nome del modello, come compare nel registro.
            accountant: chi prezza e archivia i consumi.
            mapper: traduttore usage -> `UsageRecord`; `None` usa quello della
                sottoclasse.
            retry_max: tentativi massimi sulla sola chiamata di rete.
            retry_delay: base dell'attesa esponenziale fra i tentativi.
            api_provider: chi viene chiamato direttamente; `None` usa il
                default della sottoclasse.
            billing_provider: chi fattura; `None` usa il default della
                sottoclasse.
            event_sink: dove annotare i fatti che non sono consumi.
            budget_guard: tetto di spesa della run, se previsto.
            api_model: nome con cui il fornitore conosce il modello, da
                `ModelRegistry.api_model_for`; `None` usa `model`. Va nella
                richiesta, mentre record e ledger continuano a usare `model`:
                la contabilita' non deve cambiare se il fornitore rinomina.
            generation_lookup: come rileggere il costo di una generazione dato il
                suo id; serve a dare un costo a un tentativo interrotto. `None`
                lascia l'interruzione senza costo (solo un evento).
        """
        if retry_max < 1:
            raise ValueError(
                "retry_max deve essere almeno 1: con zero tentativi non ci sarebbe "
                "nessuna chiamata da fare"
            )
        self.client = client
        self.model = model
        self.api_model = api_model or model
        self.accountant = accountant
        self.mapper = mapper or self.MAPPER
        self.retry_max = retry_max
        self.retry_delay = retry_delay
        self.api_provider = api_provider or self.DEFAULT_API_PROVIDER
        self.billing_provider = (
            billing_provider if billing_provider is not None
            else self.DEFAULT_BILLING_PROVIDER
        )
        self.event_sink = event_sink
        self.budget_guard = budget_guard
        self.generation_lookup = generation_lookup

    # -- Il contratto ------------------------------------------------------

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> AssistantTurn:
        """Restituisce il turno prodotto dal modello, gia' contabilizzato."""
        for attempt in range(1, self.retry_max + 1):
            # Il budget si controlla a ogni tentativo, non una volta sola: un
            # tentativo interrotto puo' aver gia' speso (vedi `_registra_interruzione`).
            self._check_budget_before_request()
            try:
                started = time.perf_counter()
                response = self._invoke(messages, tools)
                latency_s = time.perf_counter() - started
                break
            except Exception as error:
                if isinstance(error, StreamInterrupted):
                    self._registra_interruzione(error, attempt)
                if attempt == self.retry_max or not self._is_retryable(error):
                    self._record_provider_error(error, attempt)
                    log.error("LLM non disponibile dopo %d tentativi", attempt)
                    raise RuntimeError("LLM irraggiungibile") from error
                wait_s = self.retry_delay ** (attempt - 1)
                log.warning("Tentativo %d/%d fallito: %s. Riprovo tra %s secondi",
                            attempt, self.retry_max, error, wait_s)
                time.sleep(wait_s)
        else:
            # Irraggiungibile: `retry_max >= 1` e' garantito dal costruttore, e ogni
            # tentativo o esce con `break` o solleva. Resta come invariante scritta,
            # perche' senza il ciclo potrebbe non assegnare mai `response`.
            raise RuntimeError("nessun tentativo eseguito")

        # Da qui in poi non c'e' piu' rete: qualunque errore e' locale e non
        # deve produrre un retry della chiamata gia' fatturata.
        turn = self._to_turn(response)
        record = self.mapper.to_record(
            response, model=self.model, latency_s=latency_s, attempt=attempt,
            api_provider=self.api_provider, billing_provider=self.billing_provider,
        )
        self._annota_record(record, response)
        try:
            self.accountant.register(record)
        except RegistryError as error:
            # Il provider ha gia' risposto: l'agent puo' usare il turno, mentre
            # LedgerAccountant conserva l'anomalia come evento con le quantita'
            # osservate. Vale per ogni causa di mancata prezzatura, non solo
            # per l'usage assente.
            log.warning("Usage non prezzabile per richiesta %s (%s: %s)",
                        record.request_id, type(error).__name__, error)
        return turn

    # -- Da implementare nelle sottoclassi ---------------------------------

    def _annota_record(self, record: UsageRecord, response: Any) -> None:
        """Gancio per aggiungere al record misure proprie del fornitore; di default nessuna."""

    def _invoke(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        """Esegue la chiamata remota e restituisce la risposta grezza."""
        raise NotImplementedError

    @staticmethod
    def _to_turn(response: Any) -> AssistantTurn:
        """Converte la risposta del provider nel tipo del progetto.

        E' statico perche' la conversione dipende solo dal payload: le
        sottoclassi non hanno bisogno dello stato del gateway per tradurlo, e
        dichiararlo qui permette di verificarle come funzioni pure.
        """
        raise NotImplementedError

    # -- Comune ------------------------------------------------------------

    def _is_retryable(self, error: Exception) -> bool:
        """Ritenta soltanto guasti transitori, mai errori di richiesta o codice.

        Un 400 (modello assente, payload invalido) non migliora con un retry e
        ritarderebbe inutilmente la diagnosi. Connessione, timeout, rate limit e
        5xx sono invece tipicamente temporanei.
        """
        if isinstance(error, StreamInterrupted) and not error.retryable:
            return False
        if self.RETRYABLE and isinstance(error, self.RETRYABLE):
            return True
        status_code = getattr(error, "status_code", None)
        return isinstance(status_code, int) and (
            status_code in {408, 409, 429} or status_code >= 500
        )

    def _registra_interruzione(self, errore: StreamInterrupted, tentativo: int) -> None:
        """Lascia traccia di un flusso interrotto e, se possibile, ne registra il costo.

        Il fornitore fattura quanto ha generato fino all'interruzione, ma il
        ledger registra solo le risposte arrivate: senza questo la spesa
        resterebbe invisibile e il budget non la vedrebbe. L'evento porta
        l'id della generazione (per riconciliare a mano con il pannello) e cio'
        che era arrivato; mai il testo dell'errore remoto.
        """
        if self.event_sink is not None:
            s = errore.stats
            dettagli: dict[str, Any] = {
                "model": self.model,
                "api_provider": self.api_provider,
                "billing_provider": self.billing_provider,
                "attempt": tentativo,
                "reason": errore.reason,
                "generation_id": errore.generation_id,
                "chunks": s.chunk_count,
                "reasoning_chars": s.reasoning_chars,
                "content_chars": s.content_chars,
                "tool_fragments": s.tool_fragments,
                "max_gap_s": round(s.max_gap_s, 3),
            }
            codice = (errore.provider_error or {}).get("code")
            if isinstance(codice, int):
                dettagli["provider_error_code"] = codice
            self.event_sink.append_event("stream_interrupted", dettagli)
        if errore.generation_id is None:
            # Ne' un chunk ne' l'header: non c'e' modo di chiedere il costo. Resta
            # l'evento sopra, con quanto era arrivato.
            return
        self._riconcilia(errore.generation_id, tentativo)

    def _riconcilia(self, generation_id: str, tentativo: int) -> None:
        """Rilegge il costo di un tentativo interrotto e lo porta nei conti."""
        costo = None
        if self.generation_lookup is not None:
            try:
                costo = self.generation_lookup(generation_id)
            except Exception as errore:  # il costo e' un miglioramento dei conti, non una condizione
                log.warning("Rilettura del costo fallita per %s: %s", generation_id, errore)
        if costo is None:
            if self.event_sink is not None:
                self.event_sink.append_event("interrupted_cost_unknown", {
                    "model": self.model, "attempt": tentativo, "generation_id": generation_id})
            return
        try:
            # Dentro il `try`: un record non valido (per esempio `InvalidUsage`) non deve
            # uscire da qui, che gira gia' dentro la gestione di un errore di `complete`.
            record = UsageRecord(
                model=self.model,
                quantities=non_zero(input_tokens=costo.prompt_tokens,
                                    output_tokens=costo.completion_tokens),
                api_provider=self.api_provider, billing_provider=self.billing_provider,
                operation="chat_completion", request_id=generation_id, status="interrupted",
                measurement_source="reported", finish_reason=costo.finish_reason,
                attempt=tentativo, reasoning_tokens=costo.reasoning_tokens,
                reported_cost=costo.total_cost,
                notes="costo riletto da GET /generation dopo un'interruzione",
            )
            self.accountant.register(record)
        except (RegistryError, InvalidUsage) as errore:
            log.warning("Tentativo interrotto non prezzabile (%s): %s", type(errore).__name__, errore)

    def _check_budget_before_request(self) -> None:
        """Ferma prima della rete quando il costo gia' osservato e' al tetto."""
        if self.budget_guard is None:
            return

        total_cost = self.accountant.total_cost
        verdict = self.budget_guard.check(total_cost)
        if verdict is BudgetVerdict.SOFT_LIMIT_REACHED:
            log.warning("Soglia morbida budget raggiunta: $%.6f", total_cost)
            self._append_budget_event("budget_soft_limit_reached", total_cost)
        elif verdict is BudgetVerdict.HARD_LIMIT_REACHED:
            log.warning("Tetto budget raggiunto: $%.6f", total_cost)
            self._append_budget_event("budget_exhausted", total_cost)
            raise BudgetExceeded("budget della run esaurito")

    def _append_budget_event(self, event_type: str, total_cost: float) -> None:
        """Registra la policy e il costo osservato senza salvare prompt o segreti."""
        if self.event_sink is None or self.budget_guard is None:
            return
        details = {
            **self.budget_guard.policy_details,
            "total_cost_usd": total_cost,
            "overrun_usd": max(0.0, total_cost - (self.budget_guard.hard_limit_usd or 0.0)),
        }
        self.event_sink.append_event(event_type, details)

    def _record_provider_error(self, error: Exception, attempts: int) -> None:
        """Persiste dati diagnostici sicuri, mai il testo dell'errore remoto."""
        if self.event_sink is None:
            return

        status_code = getattr(error, "status_code", None)
        if not isinstance(status_code, int):
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)

        details: dict[str, Any] = {
            "model": self.model,
            "api_provider": self.api_provider,
            "billing_provider": self.billing_provider,
            "error_type": type(error).__name__,
            "attempts": attempts,
        }
        if isinstance(status_code, int):
            details["http_status"] = status_code
        self.event_sink.append_event("provider_error", details)


class OpenAIChatGateway(ChatGatewayBase):
    """Gateway per `client.chat.completions`, compatibile OpenAI."""

    MAPPER = OpenAIChatCompletionsUsageMapper
    DEFAULT_API_PROVIDER = "openai"
    DEFAULT_BILLING_PROVIDER = "openai"
    # Con lo streaming un guasto puo' arrivare a meta' della risposta: un flusso
    # troncato o con un evento di errore (`StreamInterrupted`), o una connessione
    # che cade durante la lettura (`httpx.TransportError`). Sono transitori: il
    # turno non e' stato consegnato, quindi ripeterlo non ha effetti collaterali.
    RETRYABLE = (openai.APIConnectionError, openai.APITimeoutError,
                 StreamInterrupted, httpx.TransportError)

    def __init__(self, *args: Any, extra_body: dict[str, Any] | None = None,
                 stream: bool = False, stall_timeout_s: float | None = None,
                 **kwargs: Any):
        """Args aggiuntivi rispetto alla base.

        Args:
            extra_body: campi in piu' da aggiungere al corpo della richiesta, se
                dato. Serve a OpenRouter per fissare il fornitore che deve
                servire il modello (`{"provider": {"order": [...],
                "allow_fallbacks": False}}`). `None` lascia la richiesta
                com'e'.
            stream: se vero la risposta si legge a pezzi (`stream=True`) e si
                ricompone prima di restituirla. Il resto del progetto non lo
                vede; cambia il modo in cui un guasto a meta' si manifesta.
            stall_timeout_s: con lo streaming, secondi senza un chunk interpretato
                dopo i quali il flusso si considera bloccato e si interrompe;
                `None` non controlla. I commenti keep-alive non contano.
        """
        super().__init__(*args, **kwargs)
        self.extra_body = extra_body
        self.stream = stream
        self.stall_timeout_s = stall_timeout_s

    def _invoke(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        """Esegue la chiamata remota e restituisce la risposta grezza."""
        extra = {} if self.extra_body is None else {"extra_body": self.extra_body}
        richiesta: dict[str, Any] = dict(
            model=self.api_model,
            messages=self._to_wire(messages),
            tools=tools,
            **extra,
        )
        if not self.stream:
            return self.client.chat.completions.create(**richiesta)
        return self._consuma(self.client.chat.completions.create(stream=True, **richiesta))

    def _consuma(self, flusso: Any) -> Any:
        """Legge tutti i chunk e restituisce la risposta ricomposta.

        Il flusso si chiude sempre, anche su un errore: una connessione lasciata
        aperta continuerebbe a far generare (e pagare) il modello. Se c'e' una
        soglia di stallo, un controllo su un thread interrompe la connessione
        quando per troppo tempo non arriva un chunk interpretato.

        Raises:
            StreamInterrupted: il flusso non e' arrivato a una conclusione valida,
                e' rimasto muto oltre la soglia, o il fornitore ha scritto un
                errore dentro il flusso.
        """
        assemblatore = StreamAssembler()
        id_header = self._id_dall_header(flusso)
        guardiano: StallWatchdog | None = None
        if self.stall_timeout_s:
            guardiano = StallWatchdog(
                self.stall_timeout_s, lambda: self._interrompi_connessione(flusso))
            guardiano.start()

        def id_generazione() -> str | None:
            # L'id del primo chunk, se e' arrivato; altrimenti quello dell'header. Senza,
            # un flusso chiuso prima del primo chunk sembrava "nessuna generazione da
            # pagare", ma il fornitore puo' averla fatturata (prova dal vivo, 18 ott 2026).
            return assemblatore.generation_id or id_header

        def stallo() -> StreamInterrupted:
            return StreamInterrupted(
                f"stallo: nessun chunk interpretato da {self.stall_timeout_s} s",
                generation_id=id_generazione(), stats=assemblatore.stats)

        try:
            for chunk in flusso:
                if guardiano is not None:
                    guardiano.touch()
                assemblatore.feed(chunk if isinstance(chunk, Mapping) else chunk.model_dump())
        except StreamInterrupted as errore:
            errore.generation_id = errore.generation_id or id_header
            raise
        except Exception as errore:
            # Dopo l'interruzione voluta la lettura fallisce in modi diversi a
            # seconda del trasporto: la causa e' lo stallo, qualunque sia l'eccezione.
            if guardiano is not None and guardiano.fired:
                raise stallo() from errore
            if isinstance(errore, httpx.TransportError):
                raise StreamInterrupted(
                    "connessione caduta durante il flusso",
                    generation_id=id_generazione(), stats=assemblatore.stats) from errore
            if isinstance(errore, openai.APIError):
                # Lo stato HTTP e' noto all'apertura del flusso: un `APIError` che
                # arriva durante la lettura e' un errore scritto dentro il flusso
                # (HTTP gia' 200), e l'SDK lo solleva.
                corpo = errore.body if isinstance(errore.body, Mapping) else None
                raise StreamInterrupted(
                    "errore del fornitore dentro il flusso",
                    generation_id=id_generazione(), stats=assemblatore.stats,
                    provider_error=corpo) from errore
            # Ne' rete ne' API (per esempio un evento malformato o un difetto nostro):
            # la generazione e' gia' stata fatturata, quindi il costo va riletto, ma
            # senza ritentare. L'errore originale resta nella catena (`from`).
            raise StreamInterrupted(
                f"errore inatteso durante la lettura del flusso ({type(errore).__name__})",
                generation_id=id_generazione(), stats=assemblatore.stats,
                retryable=False) from errore
        finally:
            if guardiano is not None:
                guardiano.stop()
            chiudi = getattr(flusso, "close", None)
            if callable(chiudi):
                chiudi()
        try:
            return assemblatore.result()
        except StreamInterrupted as errore:
            # Dopo lo `shutdown` la lettura puo' finire senza errore: il flusso
            # incompleto e' comunque uno stallo, non una chiusura qualunque.
            if guardiano is not None and guardiano.fired:
                raise stallo() from errore
            errore.generation_id = errore.generation_id or id_header
            raise

    @staticmethod
    def _id_dall_header(flusso: Any) -> str | None:
        """L'id della generazione dall'header `X-Generation-Id`, se il flusso lo espone.

        Lo stream dell'SDK OpenAI tiene la risposta HTTP in `response`. L'header
        arriva prima di qualsiasi chunk e coincide con l'id del primo (verificato
        dal vivo su MiniMax m3 e Opus 5.5). Un flusso che non lo espone (un finto,
        un altro trasporto) da' `None`, come prima.
        """
        risposta = getattr(flusso, "response", None)
        intestazioni = getattr(risposta, "headers", None)
        if intestazioni is None:
            return None
        valore = intestazioni.get("x-generation-id")
        return valore if isinstance(valore, str) and valore else None

    @staticmethod
    def _interrompi_connessione(flusso: Any) -> None:
        """Rompe la connessione di un flusso da un altro thread, sbloccando chi legge.

        `close()` da un altro thread NON sblocca la lettura (il thread resta fermo
        fino al timeout di rete: verificato con un server locale, anche su TLS).
        Sblocca `shutdown` del socket sottostante. Per un flusso che non espone la
        connessione (i finti dei test) si ripiega su `close()`.
        """
        try:
            rete = flusso.response.extensions["network_stream"]
            rete.get_extra_info("socket").shutdown(socket.SHUT_RDWR)
            return
        except Exception:  # struttura diversa da quella attesa: ripiego
            pass
        chiudi = getattr(flusso, "close", None)
        if callable(chiudi):
            chiudi()

    def _annota_record(self, record: UsageRecord, response: Any) -> None:
        """Aggiunge al record le misure del flusso, per tarare le soglie di stallo."""
        stats = getattr(response, "stats", None)
        if stats is not None:
            record.dimensions = {
                **record.dimensions,
                "chunks": stats.chunk_count,
                "max_chunk_gap_s": round(stats.max_gap_s, 3),
                "reasoning_chars": stats.reasoning_chars,
                "content_chars": stats.content_chars,
            }

    @staticmethod
    def _to_turn(response: Any) -> AssistantTurn:
        """Converte la risposta del provider nel tipo del progetto."""
        choice = response.choices[0]
        message = choice.message
        tool_calls = tuple(
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (getattr(message, "tool_calls", None) or ())
        )
        return AssistantTurn(
            content=getattr(message, "content", None),
            tool_calls=tool_calls,
            outcome=_outcome_openai(getattr(choice, "finish_reason", None), bool(tool_calls)),
        )

    @classmethod
    def _to_wire(cls, messages: list[Any]) -> list[Any]:
        """Riporta la conversazione neutra nel formato atteso dal provider.

        I turni prodotti dal modello sono `AssistantTurn`; tutto il resto
        (sistema, utente, osservazioni dei tool) l'agente lo costruisce gia'
        come dizionari nella forma OpenAI, che passano invariati.
        """
        return [
            cls._turn_to_wire(m) if isinstance(m, AssistantTurn) else m
            for m in messages
        ]

    @staticmethod
    def _turn_to_wire(turn: AssistantTurn) -> dict[str, Any]:
        """Serializza un turno del modello nella forma `chat.completions`."""
        wire: dict[str, Any] = {"role": "assistant", "content": turn.content}
        if turn.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in turn.tool_calls
            ]
        return wire


class AnthropicChatGateway(ChatGatewayBase):
    """Gateway per l'API Messages di Anthropic.

    Nota di design (tesi):
        Tre differenze di forma rispetto a OpenAI, tutte confinate qui dentro:
        il prompt di sistema e' un parametro a se' e non un messaggio; gli
        strumenti hanno uno schema diverso; le osservazioni dei tool tornano
        come messaggi *utente* con blocchi `tool_result`, e quelle relative
        allo stesso turno vanno raggruppate in un messaggio solo.

        `cache_control` viene dichiarato di default: e' la leva di costo che si
        stima piu' grande (-55.6% su un task da 12 iterazioni: calcolo, non
        ancora misurato) ed e' la ragione per cui questo gateway esiste invece
        di passare da un aggregatore.
    """

    MAPPER = AnthropicMessagesUsageMapper
    DEFAULT_API_PROVIDER = "anthropic"
    DEFAULT_BILLING_PROVIDER = "anthropic"
    RETRYABLE = (anthropic.APIConnectionError, anthropic.APITimeoutError)

    #: Anthropic pretende un tetto esplicito sui token generati per turno.
    DEFAULT_MAX_TOKENS = 8192

    def __init__(self, *args: Any, max_tokens: int = DEFAULT_MAX_TOKENS,
                 effort: str = "high", use_cache: bool = True, **kwargs: Any):
        """Args aggiuntivi rispetto alla base.

        Args:
            max_tokens: tetto sui token generati in un turno. Obbligatorio per
                questa API; troncare a meta' costringe a rigenerare, che costa
                piu' di un tetto generoso.
            effort: profondita' del ragionamento. E' una **variabile
                sperimentale**, non un dettaglio: incide direttamente sui token
                di output, che dopo l'attivazione della cache sono oltre meta'
                della spesa. Va dichiarata e tenuta costante fra le condizioni
                di un confronto.
            use_cache: se dichiarare `cache_control`. Serve a poter misurare la
                differenza fra percorso con e senza cache **a parita' di tutto
                il resto** — cioe' l'esperimento della "tassa dell'aggregatore".
        """
        super().__init__(*args, **kwargs)
        self.max_tokens = max_tokens
        self.effort = effort
        self.use_cache = use_cache

    def _invoke(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        """Esegue la chiamata remota e restituisce la risposta grezza."""
        system, conversazione = self._to_wire(messages)
        richiesta: dict[str, Any] = {
            "model": self.api_model,
            "max_tokens": self.max_tokens,
            "messages": conversazione,
            "output_config": {"effort": self.effort},
        }
        if system:
            richiesta["system"] = system
        if tools:
            richiesta["tools"] = self._tools_to_wire(tools)
        if self.use_cache:
            # Mette in cache l'ultimo blocco memorizzabile: in un ciclo ReAct
            # il prefisso cresce solo in coda, quindi e' il caso ideale per un
            # match di prefisso.
            richiesta["cache_control"] = {"type": "ephemeral"}
        return self.client.messages.create(**richiesta)

    @staticmethod
    def _to_turn(response: Any) -> AssistantTurn:
        """Converte i blocchi di contenuto nel turno del progetto.

        Gli argomenti degli strumenti arrivano gia' come dizionario, mentre il
        contratto li vuole come stringa: si serializzano con `sort_keys` cosi'
        che due richieste identiche producano lo stesso testo. Senza, il
        rilevatore di loop — che confronta firme testuali — non riconoscerebbe
        una ripetizione solo perche' le chiavi sono uscite in ordine diverso.
        """
        testi, chiamate = [], []
        for blocco in getattr(response, "content", None) or ():
            tipo = getattr(blocco, "type", None)
            if tipo == "text":
                testi.append(getattr(blocco, "text", "") or "")
            elif tipo == "tool_use":
                chiamate.append(ToolCall(
                    id=blocco.id,
                    name=blocco.name,
                    arguments=json.dumps(blocco.input or {}, sort_keys=True),
                ))
        return AssistantTurn(
            content="\n".join(testi) or None,
            tool_calls=tuple(chiamate),
            outcome=_outcome_anthropic(getattr(response, "stop_reason", None), bool(chiamate)),
        )

    @classmethod
    def _to_wire(cls, messages: list[Any]) -> tuple[str | None, list[dict[str, Any]]]:
        """Traduce la conversazione neutra, estraendone il prompt di sistema.

        Returns:
            La coppia `(system, messaggi)`. `system` e' `None` se la
            conversazione non ne contiene: in questa API non e' un messaggio ma
            un parametro della richiesta.
        """
        system: str | None = None
        fuori: list[dict[str, Any]] = []

        for messaggio in messages:
            if isinstance(messaggio, AssistantTurn):
                fuori.append(cls._turn_to_wire(messaggio))
                continue

            ruolo = messaggio.get("role")
            if ruolo == "system":
                system = messaggio.get("content")
            elif ruolo == "tool":
                cls._accoda_tool_result(fuori, messaggio)
            else:
                fuori.append({"role": ruolo, "content": messaggio.get("content")})

        return system, fuori

    @staticmethod
    def _accoda_tool_result(fuori: list[dict[str, Any]], messaggio: dict[str, Any]) -> None:
        """Accoda un'osservazione, raggruppandola con quelle che la precedono.

        L'agente accoda un messaggio per ogni tool eseguito; questa API vuole
        invece tutti i `tool_result` di uno stesso turno in **un solo**
        messaggio utente. Separarli insegna al modello a non richiedere piu'
        strumenti in parallelo, che e' una perdita di efficienza silenziosa.
        """
        blocco = {
            "type": "tool_result",
            "tool_use_id": messaggio.get("tool_call_id"),
            "content": messaggio.get("content"),
        }
        if (fuori and fuori[-1]["role"] == "user"
                and isinstance(fuori[-1].get("content"), list)):
            fuori[-1]["content"].append(blocco)
        else:
            fuori.append({"role": "user", "content": [blocco]})

    @staticmethod
    def _turn_to_wire(turn: AssistantTurn) -> dict[str, Any]:
        """Serializza un turno del modello in blocchi di contenuto."""
        blocchi: list[dict[str, Any]] = []
        if turn.content:
            blocchi.append({"type": "text", "text": turn.content})
        for tc in turn.tool_calls:
            blocchi.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": json.loads(tc.arguments) if tc.arguments else {},
            })
        return {"role": "assistant", "content": blocchi}

    @staticmethod
    def _tools_to_wire(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Converte gli schemi dei tool dalla forma OpenAI a questa.

        `Tool.schema` produce la forma OpenAI perche' e' quella con cui il
        progetto e' nato. Tradurla qui, invece di cambiare i tool, mantiene la
        conversione dove stanno tutte le altre: dentro il gateway.
        """
        convertiti = []
        for tool in tools:
            funzione = tool.get("function", tool)
            convertiti.append({
                "name": funzione["name"],
                "description": funzione.get("description", ""),
                "input_schema": funzione.get(
                    "parameters", {"type": "object", "properties": {}}),
            })
        return convertiti
