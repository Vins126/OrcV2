"""Contabilita' dei costi del sistema ORC.

Package deliberatamente **scollegato dall'agente**: registro e contabile si
costruiscono e si testano da soli, e l'aggancio ad `Agent` avviene in un unico
punto (M2a.3). Ne segue che `agent.py` viene modificato una volta sola, e che
da quel momento il contabile e' sostituibile senza toccarlo piu' — la stessa
proprieta' che `Tool` e `CommandExecutor` danno rispettivamente ai tool e agli
esecutori.

Contenuto attuale (M2a.1 e M2a.2):
    - `ModelRegistry`: listino passivo e immutabile (prezzi, capacita', costi
      di accesso), letto da `models.toml`. Sa quanto costano le cose.
    - `UsageRecord`: la scheda di una singola chiamata. Dice quanto se n'e'
      usato.
    - `Accountant`: il contratto del contabile.
    - `InMemoryAccountant`: l'implementazione che tiene i conti in memoria.
      Riceve il registro per iniezione e fa la moltiplicazione.
    - le eccezioni del package.

In arrivo (M2a.3): l'aggancio all'`Agent`, unica modifica a codice
preesistente dell'intera fase.
"""

from accounting.base import Accountant
from accounting.errors import (
    MalformedRegistry,
    ModelNotFound,
    RegistryError,
    UnitNotFound,
)
from accounting.memory import InMemoryAccountant
from accounting.record import UsageRecord
from accounting.registry import CAPACITA_NOTE, ModelRegistry

__all__ = [
    "CAPACITA_NOTE",
    "Accountant",
    "InMemoryAccountant",
    "MalformedRegistry",
    "ModelNotFound",
    "ModelRegistry",
    "RegistryError",
    "UnitNotFound",
    "UsageRecord",
]
