"""Il gateway isola provider e accounting dal ciclo dell'agente."""

from types import SimpleNamespace as NS

import pytest

from accounting.errors import UnpricedUsage
from budget_guard import BudgetExceeded, BudgetGuard
from llm_gateway import OpenAIChatGateway


def _response():
    return NS(
        id="chat_1",
        usage=NS(prompt_tokens=10, completion_tokens=4,
                 prompt_tokens_details=None, completion_tokens_details=None),
        choices=[NS(finish_reason="stop", message=NS(tool_calls=None, content="ok"))],
    )


class Client:
    def __init__(self, response):
        self.calls = 0
        self.chat = NS(completions=NS(create=self.create))
        self.response = response

    def create(self, **_kwargs):
        self.calls += 1
        return self.response


class FailingClient:
    def __init__(self, error):
        self.calls = 0
        self.error = error
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **_kwargs):
        self.calls += 1
        raise self.error


class HttpError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class EventSink:
    def __init__(self):
        self.events = []

    def append_event(self, event_type, details):
        self.events.append((event_type, details))


class Accountant:
    def __init__(self, error=None, total_cost=0.0):
        self.records = []
        self.error = error
        self._total_cost = total_cost

    def register(self, record):
        if self.error:
            raise self.error
        self.records.append(record)
        return 0.0

    @property
    def total_cost(self):
        return self._total_cost


def test_gateway_registra_la_risposta_e_restituisce_solo_il_messaggio():
    client, accountant = Client(_response()), Accountant()
    gateway = OpenAIChatGateway(client, "m", accountant, retry_max=1)

    message = gateway.complete([], [])

    assert message.content == "ok"
    assert client.calls == 1
    assert accountant.records[0].quantities == {"input_tokens": 10, "output_tokens": 4}


def test_gateway_registra_separatamente_api_e_billing_provider():
    client, accountant = Client(_response()), Accountant()
    gateway = OpenAIChatGateway(
        client, "m", accountant, retry_max=1,
        api_provider="litellm", billing_provider="openrouter",
    )

    gateway.complete([], [])

    record = accountant.records[0]
    assert record.api_provider == "litellm"
    assert record.billing_provider == "openrouter"


def test_errore_accounting_non_ripete_una_risposta_gia_ricevuta():
    client = Client(_response())
    gateway = OpenAIChatGateway(client, "m", Accountant(ValueError("listino errato")), retry_max=3)

    with pytest.raises(ValueError, match="listino errato"):
        gateway.complete([], [])

    assert client.calls == 1


def test_usage_non_prezzabile_non_interrompe_il_task():
    client = Client(_response())
    response_without_usage = _response()
    response_without_usage.usage = None
    client.response = response_without_usage
    gateway = OpenAIChatGateway(client, "m", Accountant(UnpricedUsage()), retry_max=1)

    message = gateway.complete([], [])

    assert message.content == "ok"
    assert client.calls == 1


def test_gateway_registra_errore_provider_sanitizzato_dopo_l_ultimo_tentativo():
    error = RuntimeError("testo remoto che non deve finire nel ledger")
    client, events = FailingClient(error), EventSink()
    gateway = OpenAIChatGateway(
        client, "m", Accountant(), retry_max=1,
        api_provider="litellm", billing_provider="openrouter", event_sink=events,
    )

    with pytest.raises(RuntimeError, match="LLM irraggiungibile"):
        gateway.complete([], [])

    assert events.events == [("provider_error", {
        "model": "m",
        "api_provider": "litellm",
        "billing_provider": "openrouter",
        "error_type": "RuntimeError",
        "attempts": 1,
    })]


def test_gateway_non_ritenta_un_errore_di_richiesta_non_recuperabile():
    client = FailingClient(HttpError(400))
    gateway = OpenAIChatGateway(client, "m", Accountant(), retry_max=3)

    with pytest.raises(RuntimeError, match="LLM irraggiungibile"):
        gateway.complete([], [])

    assert client.calls == 1


def test_gateway_ferma_prima_della_rete_quando_il_budget_e_esaurito():
    client, events = Client(_response()), EventSink()
    gateway = OpenAIChatGateway(
        client, "m", Accountant(total_cost=0.01), retry_max=1,
        event_sink=events, budget_guard=BudgetGuard(0.01),
    )

    with pytest.raises(BudgetExceeded):
        gateway.complete([], [])

    assert client.calls == 0
    assert events.events == [("budget_exhausted", {
        "enabled": True,
        "hard_limit_usd": 0.01,
        "soft_limit_usd": 0.008,
        "soft_ratio": 0.8,
        "total_cost_usd": 0.01,
        "overrun_usd": 0.0,
    })]
