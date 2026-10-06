"""Decorator che rende persistenti i consumi di un contabile.

Il calcolo resta delegato al contabile interno; questo oggetto aggiunge solo
la registrazione nel ledger dopo che il record ha ricevuto il suo costo.
"""

from accounting.base import Accountant
from accounting.errors import RegistryError
from accounting.ledger import RunLedger
from accounting.record import UsageRecord


class LedgerAccountant(Accountant):
    """Avvolge un contabile e persiste i suoi esiti nella run corrente.

    Il contabile interno puo' vivere piu' a lungo di un ledger: un agente
    persistente riceve piu' incarichi, ognuno col proprio ledger, ma conserva
    un solo contabile che somma la spesa di tutta la sua vita. Per questo il
    ledger si puo' cambiare con `attach`.
    """

    def __init__(self, accountant: Accountant, ledger: RunLedger | None = None):
        """Avvolge un contabile e gli affianca il ledger della run.

        Args:
            accountant: il contabile a cui delegare interamente il calcolo.
            ledger: dove persistere gli esiti e le anomalie. Facoltativo: un
                agente appena creato non ha ancora un incarico, quindi nemmeno
                un ledger; lo si collega con `attach` all'inizio di ogni incarico.
        """
        self.accountant = accountant
        self.ledger = ledger

    def attach(self, ledger: RunLedger) -> None:
        """Collega il ledger dell'incarico che sta per iniziare.

        Da questo momento i consumi finiscono nel nuovo ledger. Il totale del
        contabile interno non si azzera: continua a sommare tutta la vita.
        """
        self.ledger = ledger

    def _ledger_collegato(self) -> RunLedger:
        """Restituisce il ledger corrente, o fallisce con un messaggio chiaro.

        Registrare un consumo senza ledger vorrebbe dire perderlo: meglio un
        errore subito che una spesa che non compare da nessuna parte.
        """
        if self.ledger is None:
            raise RuntimeError(
                "nessun ledger collegato: un consumo non si puo' registrare "
                "fuori da un incarico (vedi LedgerAccountant.attach)"
            )
        return self.ledger

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
        ledger = self._ledger_collegato()
        try:
            cost = self.accountant.register(record)
        except RegistryError as error:
            ledger.append_event(
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

        ledger.append_usage(record)
        return cost

    @property
    def total_cost(self) -> float:
        """Espone il totale calcolato dal contabile interno."""
        return self.accountant.total_cost

    @property
    def call_count(self) -> int:
        """Espone il numero di consumi prezzati dal contabile interno."""
        return self.accountant.call_count
