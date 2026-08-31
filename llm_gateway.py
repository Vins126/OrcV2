"""Confine fra il ciclo dell'agente e un provider LLM.

L'agente chiede un messaggio; il gateway sa come invocare il provider, misurare
la latenza e registrare il consumo. Separare queste responsabilita' evita che
il ciclo ReAct dipenda da SDK, listini o formati di usage.
"""

import logging
import time
from typing import Any, Protocol

import config
from openai import APIConnectionError, APITimeoutError
from accounting.base import Accountant
from accounting.errors import RegistryError
from accounting.mappers.openai import OpenAIChatCompletionsUsageMapper
from budget_guard import BudgetExceeded, BudgetGuard, BudgetVerdict
from llm_contracts import ChatGateway

log = logging.getLogger(__name__)


class RunEventSink(Protocol):
    """Destinazione opzionale di eventi tecnici, senza dipendere dal ledger."""

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Registra un fatto della run che non e' un usage record."""


class OpenAIChatGateway:
    """Gateway per ``client.chat.completions`` compatibile OpenAI.

    Il blocco di retry protegge esclusivamente la chiamata remota: ripetere
    una risposta gia' ricevuta per un problema locale creerebbe una seconda
    spesa. Dopo la risposta i due tipi di errore si comportano in modo
    opposto — un fallimento di **prezzatura** viene annotato e la run
    prosegue, perche' la spesa e' gia' stata sostenuta e va conservata; un
    errore di **codice** emerge subito, perche' e' un difetto da correggere.
    """

    def __init__(self, client: Any, model: str, accountant: Accountant,
                 mapper: Any = OpenAIChatCompletionsUsageMapper,
                 retry_max: int = config.RETRY_MAX,
                 retry_delay: float = config.RETRY_DELAY,
                 api_provider: str = "openai",
                 billing_provider: str | None = "openai",
                 event_sink: RunEventSink | None = None,
                 budget_guard: BudgetGuard | None = None):
        self.client = client
        self.model = model
        self.accountant = accountant
        self.mapper = mapper
        self.retry_max = retry_max
        self.retry_delay = retry_delay
        self.api_provider = api_provider
        self.billing_provider = billing_provider
        self.event_sink = event_sink
        self.budget_guard = budget_guard

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        self._check_budget_before_request()
        for attempt in range(1, self.retry_max + 1):
            try:
                started = time.perf_counter()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                )
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

        # Da qui in poi non c'e' piu' rete: qualunque errore e' locale e non
        # deve produrre un retry della chiamata potenzialmente gia' fatturata.
        message = response.choices[0].message
        record = self.mapper.to_record(
            response, model=self.model, latency_s=latency_s, attempt=attempt,
            api_provider=self.api_provider, billing_provider=self.billing_provider,
        )
        try:
            self.accountant.register(record)
        except RegistryError as error:
            # Il provider ha gia' risposto: l'agent puo' usare il messaggio,
            # mentre LedgerAccountant conserva l'anomalia come evento.
            # Vale per ogni causa di mancata prezzatura, non solo per l'usage
            # assente: un'unita' senza listino (per esempio i token da cache
            # di un modello che non li dichiara) fermerebbe altrimenti una run
            # gia' pagata, e per giunta con costo totale a zero.
            log.warning("Usage non prezzabile per richiesta %s (%s: %s)",
                        record.request_id, type(error).__name__, error)
        return message

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

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """Ritenta soltanto guasti transitori, mai errori di richiesta o codice.

        Un 400 (modello assente, payload invalido) non migliora con un retry e
        ritarderebbe inutilmente la diagnosi. Connessione, timeout, rate limit e
        5xx sono invece tipicamente temporanei.
        """
        if isinstance(error, (APIConnectionError, APITimeoutError)):
            return True
        status_code = getattr(error, "status_code", None)
        return isinstance(status_code, int) and (
            status_code in {408, 409, 429} or status_code >= 500
        )
