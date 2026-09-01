"""Dominio accounting: usage normalizzato, prezzi, calcolo e persistenza.

Il package non decide quale modello chiamare e non importa l'SDK del provider.
Riceve `UsageRecord` gia' normalizzati dai mapper, li prezza con il registro e
puo' salvarli tramite il ledger. Questo confine rende costi e dati confrontabili
anche quando cambiano proxy, endpoint o modelli.
"""

from accounting.base import Accountant
from accounting.errors import (
    CapabilityUnavailable,
    MalformedRegistry,
    InvalidUsage,
    ModelNotFound,
    RegistryError,
    RoleNotFound,
    UnitNotFound,
    UnpricedUsage
)
from accounting.memory import InMemoryAccountant
from accounting.record import UsageRecord
from accounting.registry import CAPACITA_NOTE, ModelRegistry

__all__ = [
    "CAPACITA_NOTE",
    "Accountant",
    "CapabilityUnavailable",
    "InMemoryAccountant",
    "InvalidUsage",
    "MalformedRegistry",
    "ModelNotFound",
    "ModelRegistry",
    "RegistryError",
    "RoleNotFound",
    "UnitNotFound",
    "UsageRecord",
    "UnpricedUsage",
]
