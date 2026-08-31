"""Mapper dai payload dei provider al contratto interno ``UsageRecord``.

Ogni mapper conosce la forma della risposta di una specifica API; il resto del
dominio conosce soltanto ``UsageRecord``.  Aggiungere un provider o una nuova
modalita' significa quindi aggiungere un mapper, non ramificare l'agente o il
contabile.
"""

from accounting.mappers.openai import (
    OpenAIChatCompletionsUsageMapper,
    OpenAIImageUsageMapper,
    OpenAIResponsesUsageMapper,
    OpenAIVideoUsageMapper,
)

__all__ = [
    "OpenAIChatCompletionsUsageMapper",
    "OpenAIImageUsageMapper",
    "OpenAIResponsesUsageMapper",
    "OpenAIVideoUsageMapper",
]
