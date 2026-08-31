"""Contratti minimi tra il ciclo ReAct e l'infrastruttura LLM.

Questo modulo non importa SDK, configurazione o accounting: l'`Agent` puo'
quindi essere importato e testato senza configurare un provider reale.
"""

from typing import Any, Protocol


class ChatGateway(Protocol):
    """Servizio capace di produrre il prossimo messaggio del modello."""

    def complete(self, messages: list[Any], tools: list[dict[str, Any]]) -> Any:
        """Restituisce un messaggio compatibile OpenAI o solleva un errore terminale."""
