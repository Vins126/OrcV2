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
import time
from typing import Any, Protocol

import anthropic
import openai

import config
from accounting.base import Accountant
from accounting.errors import RegistryError
from accounting.mappers.anthropic import AnthropicMessagesUsageMapper
from accounting.mappers.openai import OpenAIChatCompletionsUsageMapper
from budget_guard import BudgetExceeded, BudgetGuard, BudgetVerdict
from llm_contracts import AssistantTurn, ChatGateway, ToolCall

log = logging.getLogger(__name__)


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
                 budget_guard: BudgetGuard | None = None):
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
        """
        if retry_max < 1:
            raise ValueError(
                "retry_max deve essere almeno 1: con zero tentativi non ci sarebbe "
                "nessuna chiamata da fare"
            )
        self.client = client
        self.model = model
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

    # -- Il contratto ------------------------------------------------------

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> AssistantTurn:
        """Restituisce il turno prodotto dal modello, gia' contabilizzato."""
        self._check_budget_before_request()

        for attempt in range(1, self.retry_max + 1):
            try:
                started = time.perf_counter()
                response = self._invoke(messages, tools)
                latency_s = time.perf_counter() - started
                break
            except Exception as error:
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
        if self.RETRYABLE and isinstance(error, self.RETRYABLE):
            return True
        status_code = getattr(error, "status_code", None)
        return isinstance(status_code, int) and (
            status_code in {408, 409, 429} or status_code >= 500
        )

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
    RETRYABLE = (openai.APIConnectionError, openai.APITimeoutError)

    def _invoke(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        """Esegue la chiamata remota e restituisce la risposta grezza."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=self._to_wire(messages),
            tools=tools,
        )

    @staticmethod
    def _to_turn(response: Any) -> AssistantTurn:
        """Converte la risposta del provider nel tipo del progetto."""
        message = response.choices[0].message
        return AssistantTurn(
            content=getattr(message, "content", None),
            tool_calls=tuple(
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in (getattr(message, "tool_calls", None) or ())
            ),
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

        `cache_control` viene dichiarato di default: e' la leva di costo piu'
        grande misurata (-55.6% su un task da 12 iterazioni) ed e' la ragione
        per cui questo gateway esiste invece di passare da un aggregatore.
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
            "model": self.model,
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
