"""Mapper per i payload dell'API Messages di Anthropic.

Nota di design (tesi):
    Aggiungere un fornitore significa aggiungere un mapper. Questo file e' la
    verifica sperimentale di quella promessa: il resto del dominio — registro,
    contabile, ledger, agente — non cambia di una riga.

⚠️ La trappola e' **all'opposto** di quella di OpenAI, e sbagliarla costa in
    direzioni diverse:

        OpenAI    `prompt_tokens` **include** i token serviti dalla cache,
                  quindi vanno scorporati o si contano due volte.

        Anthropic `input_tokens` sono **gia' solo** quelli non in cache;
                  `cache_read_input_tokens` e `cache_creation_input_tokens`
                  sono voci separate e disgiunte.

    Copiare qui la logica di scorporo del mapper OpenAI sottrarrebbe una
    seconda volta e **sottostimerebbe** il costo — un errore che non solleva
    eccezioni e produce solo numeri troppo bassi, cioe' esattamente nella
    direzione che farebbe sembrare la tesi piu' forte di quanto e'.
"""

from typing import Any

from accounting.mappers.base import field, non_zero, number
from accounting.record import UsageRecord


class AnthropicMessagesUsageMapper:
    """Converte una risposta dell'API Messages in un record di consumo."""

    @staticmethod
    def to_record(response: Any, *, model: str, latency_s: float | None,
                  attempt: int = 1, api_provider: str = "anthropic",
                  billing_provider: str | None = "anthropic") -> UsageRecord:
        """Costruisce il record a partire dalla risposta del provider.

        Args:
            response: la risposta di `client.messages.create`, o un suo finto.
            model: nome del modello, come compare nel registro.
            latency_s: durata misurata dal gateway.
            attempt: a quale tentativo la chiamata e' riuscita.
            api_provider: chi e' stato chiamato direttamente.
            billing_provider: chi fattura il consumo.

        Returns:
            Il `UsageRecord` corrispondente, con le quattro unita' tenute
            distinte come le dichiara il fornitore.
        """
        usage = field(response, "usage")

        # Nessuna sottrazione: le quattro voci sono gia' disgiunte.
        quantities = non_zero(
            input_tokens=number(field(usage, "input_tokens")),
            cached_input_tokens=number(field(usage, "cache_read_input_tokens")),
            cache_write_tokens=number(field(usage, "cache_creation_input_tokens")),
            output_tokens=number(field(usage, "output_tokens")),
        )

        blocchi = field(response, "content") or []
        tool_uses = [b for b in blocchi if field(b, "type") == "tool_use"]

        return UsageRecord(
            model=model,
            quantities=quantities,
            api_provider=api_provider,
            billing_provider=billing_provider,
            # Stesso nome dell'operazione del mapper chat di OpenAI, di
            # proposito: `cost_by_operation` deve restare confrontabile fra
            # fornitori, altrimenti la misura della "tassa dell'aggregatore"
            # non si puo' fare. A distinguere chi ha risposto c'e' gia'
            # `api_provider`.
            operation="chat_completion",
            request_id=field(response, "id"),
            status="succeeded",
            # `stop_reason` vale `max_tokens` dove OpenAI dice `length`: e' lo
            # stesso segnale di risposta troncata, con un altro nome.
            finish_reason=field(response, "stop_reason"),
            n_tool_calls=len(tool_uses),
            # Il fornitore non espone un conteggio separato dei token di
            # ragionamento: sono fatturati dentro `output_tokens` e non
            # distinguibili. Resta zero, e in analisi va letto come "non
            # disponibile" e non come "non ha ragionato".
            reasoning_tokens=0,
            latency_s=latency_s,
            attempt=attempt,
            measurement_source="reported" if usage is not None else "missing",
        )
