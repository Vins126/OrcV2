"""L'incarico in corso di un agente: un solo punto di collegamento verso il suo ledger.

Nota di design (tesi):
    Un agente persistente fa piu' incarichi, ognuno con il proprio ledger. Chi scrive nel
    ledger e' sparso: il contabile (i consumi), il gateway (errori del fornitore, soglie
    di budget), l'esecutore Docker (attese per la sandbox). Prima, a ogni incarico, si
    ricollegava a mano ciascuno di loro: un ricollegamento dimenticato avrebbe mandato
    gli eventi nel ledger dell'incarico precedente, gia' chiuso, senza alcun errore
    (accoppiamento temporale).

    Ora tutti ricevono, una volta sola alla costruzione, lo stesso `CurrentRun`, e a ogni
    incarico si ricollega soltanto lui (`BuiltAgent.assign`). Aggiungere un nuovo
    scrittore non aggiunge una riga da ricordare.
"""

from typing import Any

from accounting.errors import NoActiveRun
from accounting.ledger import RunLedger
from accounting.record import UsageRecord


class CurrentRun:
    """Inoltra consumi ed eventi al ledger dell'incarico in corso."""

    def __init__(self, ledger: RunLedger | None = None):
        """Args:
            ledger: il ledger iniziale; di norma nessuno, perche' un agente appena
                creato non ha ancora un incarico.
        """
        self._ledger = ledger

    @property
    def ledger(self) -> RunLedger | None:
        """Il ledger dell'incarico in corso, o `None` fra un incarico e l'altro."""
        return self._ledger

    def attach(self, ledger: RunLedger) -> None:
        """Collega il ledger dell'incarico che sta per iniziare: da ora tutto va li'."""
        self._ledger = ledger

    def detach(self) -> None:
        """Stacca il ledger a fine incarico.

        Il ledger e' gia' chiuso (riepilogo scritto): un evento arrivato in ritardo
        finirebbe fuori dal riepilogo senza alcun errore. Staccato, fa `NoActiveRun`.
        """
        self._ledger = None

    def require_active(self) -> RunLedger:
        """Il ledger dell'incarico in corso.

        Lo usa anche chi deve sapere **prima** di agire se c'e' dove scrivere: il
        contabile controlla qui prima di contare un consumo, altrimenti la spesa
        finirebbe nel totale ma in nessun ledger.

        Raises:
            NoActiveRun: se non c'e' un incarico in corso.
        """
        if self._ledger is None:
            raise NoActiveRun(
                "nessun incarico in corso: un consumo o un evento scritto ora andrebbe "
                "perso (vedi CurrentRun.attach)")
        return self._ledger

    def append_usage(self, record: UsageRecord) -> None:
        """Scrive un consumo nel ledger dell'incarico in corso.

        Raises:
            NoActiveRun: se non c'e' un incarico in corso.
        """
        self.require_active().append_usage(record)

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Scrive un evento nel ledger dell'incarico in corso.

        Raises:
            NoActiveRun: se non c'e' un incarico in corso.
        """
        self.require_active().append_event(event_type, details)
