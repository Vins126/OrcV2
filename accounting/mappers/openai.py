"""Mapper per i payload OpenAI compatibili con l'SDK Python.

La mappatura e' intenzionalmente separata per endpoint: ``chat.completions``
e ``responses`` hanno campi e semantiche differenti, mentre immagini e video
usano unita' di fatturazione diverse dai token testuali.
"""

from typing import Any

from accounting.mappers.base import field, nested, non_zero, number
from accounting.record import UsageRecord


def _common(
    response: Any,
    *,
    model: str,
    operation: str,
    latency_s: float | None,
    attempt: int,
    api_provider: str = "openai",
    billing_provider: str | None = "openai",
    status: str = "succeeded",
    dimensions: dict[str, Any] | None = None,
    measurement_source: str = "reported",
) -> dict[str, Any]:
    """Compone i campi che identificano l'operazione, comuni a ogni mapper.

    Tiene separato cio' che **descrive** il consumo — chi e' stato chiamato,
    che tipo di operazione era, come si e' chiusa — da cio' che viene
    **moltiplicato per un prezzo**, che vive solo in `quantities`.
    """
    return {
        "model": model,
        "api_provider": api_provider,
        "billing_provider": billing_provider,
        "operation": operation,
        "request_id": field(response, "id"),
        "status": status,
        "dimensions": dimensions or {},
        "measurement_source": measurement_source,
        "latency_s": latency_s,
        "attempt": attempt,
    }


class OpenAIChatCompletionsUsageMapper:
    """Converte una risposta ``chat.completions`` in un record di consumo."""

    @staticmethod
    def to_record(response: Any, *, model: str, latency_s: float | None,
                  attempt: int = 1, api_provider: str = "openai",
                  billing_provider: str | None = "openai") -> UsageRecord:
        """Converte una risposta chat.completions in un record di consumo.

        Scorpora i token serviti dalla cache da quelli di input:
        `prompt_tokens` li **include**, quindi sommarli entrambi ne
        conterebbe una parte due volte.

        Args:
            response: la risposta del provider, o un suo finto.
            model: nome del modello, come compare nel registro.
            latency_s: durata misurata dal gateway.
            attempt: a quale tentativo la chiamata e' riuscita.
            api_provider: chi e' stato chiamato direttamente.
            billing_provider: chi fattura il consumo.

        Returns:
            Il `UsageRecord` corrispondente.
        """
        usage = field(response, "usage")
        prompt = number(field(usage, "prompt_tokens"))
        cached = number(nested(usage, "prompt_tokens_details", "cached_tokens"))
        completion = number(field(usage, "completion_tokens"))
        reasoning = number(nested(usage, "completion_tokens_details", "reasoning_tokens"))
        choices = field(response, "choices") or []
        first = choices[0] if choices else None
        message = field(first, "message")
        tool_calls = field(message, "tool_calls") or []

        # prompt_tokens include cached_tokens: scorporarli impedisce il doppio
        # conteggio quando il listino ha una tariffa cache separata.
        quantities = non_zero(
            input_tokens=max(0, prompt - cached),
            cached_input_tokens=cached,
            output_tokens=completion,
        )
        return UsageRecord(
            quantities=quantities,
            finish_reason=field(first, "finish_reason"),
            n_tool_calls=len(tool_calls),
            reasoning_tokens=int(reasoning),
            **_common(response, model=model, operation="chat_completion",
                      latency_s=latency_s, attempt=attempt,
                      api_provider=api_provider, billing_provider=billing_provider,
                      measurement_source="reported" if usage is not None else "missing"),
        )


class OpenAIResponsesUsageMapper:
    """Converte una risposta della Responses API in un record di consumo."""

    @staticmethod
    def to_record(response: Any, *, model: str, latency_s: float | None,
                  attempt: int = 1, api_provider: str = "openai",
                  billing_provider: str | None = "openai") -> UsageRecord:
        """Converte una risposta Responses API in un record di consumo.

        Distingue lettura e scrittura di cache, che questa API riporta
        come voci separate dentro `input_tokens_details`.

        Args:
            response: la risposta del provider, o un suo finto.
            model: nome del modello, come compare nel registro.
            latency_s: durata misurata dal gateway.
            attempt: a quale tentativo la chiamata e' riuscita.
            api_provider: chi e' stato chiamato direttamente.
            billing_provider: chi fattura il consumo.

        Returns:
            Il `UsageRecord` corrispondente.
        """
        usage = field(response, "usage")
        input_tokens = number(field(usage, "input_tokens"))
        cached = number(nested(usage, "input_tokens_details", "cached_tokens"))
        cache_write = number(nested(usage, "input_tokens_details", "cache_write_tokens"))
        output_tokens = number(field(usage, "output_tokens"))
        reasoning = number(nested(usage, "output_tokens_details", "reasoning_tokens"))

        quantities = non_zero(
            input_tokens=max(0, input_tokens - cached),
            cached_input_tokens=cached,
            cache_write_tokens=cache_write,
            output_tokens=output_tokens,
        )
        return UsageRecord(
            quantities=quantities,
            reasoning_tokens=int(reasoning),
            **_common(response, model=model, operation="response",
                      latency_s=latency_s, attempt=attempt,
                      api_provider=api_provider, billing_provider=billing_provider,
                      status=field(response, "status", "succeeded"),
                      measurement_source="reported" if usage is not None else "missing"),
        )


class OpenAIImageUsageMapper:
    """Converte una risposta Images API, incluse generation ed edit.

    ``gpt-image`` restituisce token separati per testo e immagine; i vecchi
    endpoint possono non restituire usage. In quest'ultimo caso il numero di
    asset prodotti e' una misura derivata esplicitamente marcata come tale.
    """

    @staticmethod
    def to_record(response: Any, *, model: str, latency_s: float | None,
                  attempt: int = 1, operation: str = "image_generation",
                  api_provider: str = "openai",
                  billing_provider: str | None = "openai") -> UsageRecord:
        """Converte una risposta Images API in un record di consumo.

        Quando il provider non dichiara l'usage, il numero di immagini
        prodotte e' una misura **derivata** e viene marcata come tale:
        non e' la stessa cosa di un consumo dichiarato.

        Args:
            response: la risposta del provider, o un suo finto.
            model: nome del modello, come compare nel registro.
            latency_s: durata misurata dal gateway.
            attempt: a quale tentativo la chiamata e' riuscita.
            api_provider: chi e' stato chiamato direttamente.
            billing_provider: chi fattura il consumo.

        Returns:
            Il `UsageRecord` corrispondente.
        """
        usage = field(response, "usage")
        data = field(response, "data") or []
        dimensions = {
            key: value for key in ("size", "quality", "background", "output_format")
            if (value := field(response, key)) is not None
        }
        if usage is None:
            quantities = non_zero(image=float(len(data)))
            source = "derived" if data else "missing"
        else:
            quantities = non_zero(
                input_text_tokens=number(nested(usage, "input_tokens_details", "text_tokens")),
                input_image_tokens=number(nested(usage, "input_tokens_details", "image_tokens")),
                output_text_tokens=number(nested(usage, "output_tokens_details", "text_tokens")),
                output_image_tokens=number(nested(usage, "output_tokens_details", "image_tokens")),
            )
            source = "reported"
        return UsageRecord(
            quantities=quantities,
            **_common(response, model=model, operation=operation,
                      latency_s=latency_s, attempt=attempt,
                      api_provider=api_provider, billing_provider=billing_provider,
                      dimensions=dimensions, measurement_source=source),
        )


class OpenAIVideoUsageMapper:
    """Converte lo stato di un job video in consumo per secondi generati.

    Il gateway deve registrare il record al completamento del job, non quando
    la creazione restituisce ``queued``: altrimenti una richiesta fallita
    verrebbe contabilizzata come un video prodotto.
    """

    @staticmethod
    def to_record(response: Any, *, model: str, latency_s: float | None,
                  attempt: int = 1, operation: str = "video_generation",
                  api_provider: str = "openai",
                  billing_provider: str | None = "openai") -> UsageRecord:
        """Converte una risposta job video in un record di consumo.

        Registra un consumo solo a job `completed`: contabilizzare una
        creazione ancora in coda fatturerebbe un video mai prodotto.

        Args:
            response: la risposta del provider, o un suo finto.
            model: nome del modello, come compare nel registro.
            latency_s: durata misurata dal gateway.
            attempt: a quale tentativo la chiamata e' riuscita.
            api_provider: chi e' stato chiamato direttamente.
            billing_provider: chi fattura il consumo.

        Returns:
            Il `UsageRecord` corrispondente.
        """
        status = field(response, "status", "unknown")
        seconds = number(field(response, "seconds"))
        dimensions = {
            key: value for key in ("size", "quality")
            if (value := field(response, key)) is not None
        }
        quantities = non_zero(video_second=seconds) if status == "completed" else {}
        return UsageRecord(
            quantities=quantities,
            **_common(response, model=model, operation=operation,
                      latency_s=latency_s, attempt=attempt, status=status,
                      api_provider=api_provider, billing_provider=billing_provider,
                      dimensions=dimensions,
                      measurement_source="reported" if status == "completed" else "missing"),
        )
