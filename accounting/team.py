"""Contabile di squadra: quanto ha speso un gruppo di agenti, letto mentre lavorano.

Nota di design (tesi):
    E' un `SpendReader`, non un `Accountant` (vedi `accounting/base.py`): non registra
    consumi propri, somma quelli dei membri. Come `InMemoryAccountant`, non tiene un
    contatore parallelo: il totale si ricalcola a ogni lettura, cosi' non puo' divergere
    da quello dei membri. Serve al tetto di spesa di squadra (M4.2c), che deve leggere il
    totale **mentre** gli agenti lavorano, non a cose fatte.

    **Si conta dall'ingresso in squadra.** Il contabile di un agente somma tutta la sua
    vita, e da M2s.3 gli agenti sono persistenti: un agente puo' aver gia' speso per
    altro lavoro. All'ingresso si annota quanto aveva gia' speso (una costante, fissata
    una volta sola: non e' un contatore) e lo si sottrae a ogni lettura.

    Limiti dichiarati (non corretti: il rimedio costa piu' del rischio):
      - vale se un agente lavora per **una squadra alla volta**: se spendesse per due
        squadre nello stesso momento, ciascuna conterebbe anche la spesa dell'altra.
        Il rimedio, se servira' in M4, e' scrivere in ogni consumo per quale squadra
        e' stato fatto (ROADMAP, M4: «C-c»);
      - il doppio ingresso si riconosce solo se e' lo **stesso oggetto**: aggiungere
        sia un `InMemoryAccountant` sia il `LedgerAccountant` che lo avvolge (o una
        sottosquadra che contiene un membro gia' presente) conta due volte la stessa
        spesa;
      - spesa e numero di chiamate si leggono in due istanti: se il membro fa una
        chiamata proprio fra le due letture, all'ingresso o in una lettura, il conteggio
        delle chiamate resta sfasato di una rispetto alla spesa.
"""

import threading
from dataclasses import dataclass

from accounting.base import SpendReader
from accounting.errors import TeamMembershipError


@dataclass(frozen=True)
class _Membro:
    """Un membro e cio' che aveva gia' speso quando e' entrato."""

    reader: SpendReader
    cost_at_join: float
    calls_at_join: int


class TeamAccountant(SpendReader):
    """Somma, a ogni lettura, la spesa dei membri da quando sono entrati in squadra."""

    def __init__(self):
        self._membri: dict[str, _Membro] = {}
        # Protegge l'elenco dei membri: aggiungerne uno mentre un altro thread somma
        # farebbe fallire l'iterazione ("dictionary changed size during iteration").
        # Le letture lavorano su una copia, cosi' il lock dura un istante.
        self._lock = threading.Lock()

    def add(self, name: str, member: SpendReader) -> None:
        """Aggiunge un membro; da ora la sua spesa conta per la squadra.

        Args:
            name: come il membro compare in `breakdown` (per esempio l'`agent_id`).
            member: il suo contabile, o un'altra squadra.

        Raises:
            TeamMembershipError: se il nome e' gia' usato, se lo stesso contabile
                e' gia' nella squadra (conterebbe doppio) o se la squadra e' se stessa.
        """
        if member is self or (isinstance(member, TeamAccountant) and member._contiene(self)):
            raise TeamMembershipError(
                "una squadra non puo' contenere se stessa, neanche attraverso altre squadre")
        # La spesa di partenza si legge FUORI dal lock: se il membro e' una squadra,
        # leggerla prende il suo lock, e due squadre che si aggiungono a vicenda
        # tenendo ciascuna il proprio si bloccherebbero per sempre.
        partenza = _Membro(member, member.total_cost, member.call_count)
        with self._lock:
            if name in self._membri:
                raise TeamMembershipError(f"il nome '{name}' e' gia' usato in questa squadra")
            for altro, membro in self._membri.items():
                if membro.reader is member:
                    raise TeamMembershipError(
                        f"questo contabile e' gia' nella squadra come '{altro}': "
                        f"la sua spesa conterebbe due volte")
            self._membri[name] = partenza

    def _contiene(self, squadra: "TeamAccountant") -> bool:
        """Vero se `squadra` e' fra i membri di questa, anche attraverso sottosquadre."""
        for membro in self._copia().values():
            if membro.reader is squadra:
                return True
            if isinstance(membro.reader, TeamAccountant) and membro.reader._contiene(squadra):
                return True
        return False

    def _copia(self) -> dict[str, _Membro]:
        with self._lock:
            return dict(self._membri)

    @property
    def total_cost(self) -> float:
        """Spesa della squadra: per ogni membro, quanto ha speso da quando e' entrato."""
        return sum(m.reader.total_cost - m.cost_at_join for m in self._copia().values())

    @property
    def call_count(self) -> int:
        """Chiamate della squadra, contate allo stesso modo."""
        return sum(m.reader.call_count - m.calls_at_join for m in self._copia().values())

    def breakdown(self) -> dict[str, dict[str, float | int]]:
        """Spesa e chiamate di ciascun membro dal suo ingresso: ogni consumo resta attribuibile."""
        return {
            nome: {"cost": m.reader.total_cost - m.cost_at_join,
                   "calls": m.reader.call_count - m.calls_at_join}
            for nome, m in self._copia().items()
        }
