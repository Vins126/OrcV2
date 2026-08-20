"""Contabile che tiene i conti in memoria.

E' l'implementazione ordinaria del contratto `Accountant`: conserva i record
delle chiamate in una lista e ricava i totali sommandoli. Il nome dice **dove**
tiene i dati (in RAM), seguendo lo stesso criterio di `executors/docker.py` e
`executors/local.py`, che si distinguono per *come* eseguono i comandi.

Nota di design (tesi):
    I totali non vengono mantenuti in contatori aggiornati a ogni
    registrazione: si calcolano sommando i record quando qualcuno li chiede.
    La ragione e' che un contatore parallelo alla lista sarebbe una **seconda
    fonte di verita'** per lo stesso dato, e prima o poi divergerebbe — basta
    un percorso di codice che aggiunga il record e dimentichi di incrementare
    il contatore. Il costo del ricalcolo e' irrilevante: sommare qualche
    decina di numeri, anche a ogni controllo del budget.

    Il registro arriva per **iniezione** e non viene creato qui dentro. Ne
    discende la struttura prevista per M4: un solo registro immutabile,
    condiviso, e N contabili come questo — uno per worker, ciascuno con i
    propri record, cosi' che le spese restino attribuibili al singolo agente.
"""

from accounting.base import Accountant
from accounting.record import UsageRecord

class InMemoryAccountant(Accountant):
    """Contabile che conserva i record in una lista in memoria.

    Attributes:
        registry: il listino a cui chiedere i prezzi. Iniettato dall'esterno.
        records: le chiamate registrate finora, in ordine cronologico. La
            lista e' creata in `__init__` e non nel corpo della classe: cosi'
            ogni contabile ha la propria. Dichiararla come attributo di classe
            la renderebbe **condivisa fra tutte le istanze**, e nello swarm i
            costi dei worker finirebbero mescolati.
    """

    def __init__(self, registry):
        """Registra il listino da consultare e prepara la lista dei record.

        Args:
            registry: un `ModelRegistry` (o qualunque oggetto che esponga
                `cost(model, unit, quantity)`: nei test si usa un registro
                finto con prezzi tondi, senza leggere alcun file).
        """
        self.registry = registry
        self.records: list[UsageRecord] = []

    def register(self, record: UsageRecord) -> float:
        """Calcola il costo di una chiamata, lo annota nel record e lo archivia.

        Il costo si ottiene sommando il contributo di **ogni unita' di
        consumo** presente nel record: una chiamata testuale ne ha due (token
        di input e di output), una generazione di immagine una sola. E' cio'
        che permette di trattare allo stesso modo unita' di fatturazione
        diverse, perche' la conversione in dollari la fa il registro.

        Args:
            record: la scheda della chiamata. Viene **modificata**: il campo
                `cost` viene valorizzato prima dell'archiviazione.

        Returns:
            Il costo in dollari di questa singola chiamata.

        Raises:
            ModelNotFound: se il modello del record non e' a registro.
            UnitNotFound: se il modello non espone un prezzo per una delle
                unita' dichiarate (per esempio chiedere il prezzo di
                un'immagine a un modello di solo testo).
        """
        totale = 0.0

        for unit, qty in record.quantities.items():
            totale += self.registry.cost(record.model, unit, qty)

        record.cost = totale
        self.records.append(record)
        return totale

    @property
    def call_count(self) -> int:
        """Quante chiamate sono state registrate."""
        return len(self.records)

    @property
    def total_cost(self) -> float:
        """Somma dei costi di tutte le chiamate registrate.

        Ricalcolata a ogni lettura invece di essere mantenuta in un contatore:
        vedi la nota di design in cima al modulo.
        """
        return sum(r.cost for r in self.records)