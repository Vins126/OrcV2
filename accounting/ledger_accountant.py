"""Decorator che rende persistenti i consumi di un contabile.

Il calcolo resta delegato al contabile interno; questo oggetto aggiunge solo
la registrazione nel ledger dopo che il record ha ricevuto il suo costo.
"""

from accounting.base import Accountant
from accounting.errors import RegistryError
from accounting.ledger import RunLedger
from accounting.record import UsageRecord


class LedgerAccountant(Accountant):
    """Avvolge un contabile e persiste i suoi esiti nella run corrente."""

    def __init__(self, accountant: Accountant, ledger: RunLedger):
        self.accountant = accountant
        self.ledger = ledger

    def register(self, record: UsageRecord) -> float:
        """Calcola il costo e salva il record solo quando il calcolo riesce.

        Qualunque fallimento di prezzatura — usage assente, unita' senza
        listino, modello non a registro — diventa un evento `unpriced_usage`
        anziche' interrompere la run. Sono tutti la stessa situazione: la
        chiamata al provider e' **gia' avvenuta ed e' gia' stata pagata**, e
        far morire la run qui cancellerebbe dal ledger una spesa realmente
        sostenuta. L'evento conserva le quantita' osservate, cosi' il costo
        resta ricalcolabile a posteriori una volta corretto `models.toml`.
        """
        try:
            cost = self.accountant.register(record)
        except RegistryError as error:
            self.ledger.append_event(
                "unpriced_usage",
                {
                    "model": record.model,
                    "operation": record.operation,
                    "request_id": record.request_id,
                    "measurement_source": record.measurement_source,
                    "reason": type(error).__name__,
                    "quantities": dict(record.quantities),
                },
            )
            raise

        self.ledger.append_usage(record)
        return cost

    @property
    def total_cost(self) -> float:
        """Espone il totale calcolato dal contabile interno."""
        return self.accountant.total_cost

    @property
    def call_count(self) -> int:
        """Espone il numero di consumi prezzati dal contabile interno."""
        return self.accountant.call_count
