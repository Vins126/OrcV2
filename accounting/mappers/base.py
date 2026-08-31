"""Primitive condivise dai mapper.

I client OpenAI restituiscono oggetti Pydantic, mentre i test e alcuni proxy
restituiscono dizionari o semplici namespace. I mapper supportano tutti e tre
senza dipendere dall'SDK.
"""

from typing import Any


def field(value: Any, name: str, default: Any = None) -> Any:
    """Legge ``name`` sia da un mapping sia da un oggetto."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def nested(value: Any, *names: str, default: Any = None) -> Any:
    """Legge un percorso di attributi, restituendo ``default`` se manca."""
    for name in names:
        value = field(value, name)
        if value is None:
            return default
    return value


def number(value: Any, default: float = 0) -> float:
    """Converte prudentemente un valore di usage in numero non negativo."""
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        return default


def non_zero(**quantities: float) -> dict[str, float]:
    """Elimina gli zeri: un'assenza di usage non deve sembrare una voce prezzata."""
    return {unit: qty for unit, qty in quantities.items() if qty > 0}
