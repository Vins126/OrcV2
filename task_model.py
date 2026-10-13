"""Tipi condivisi della campagna: il task e l'errore di configurazione.

Stanno in un modulo a parte perche' li usano sia `campaign` sia `polyglot`, e
`campaign.py` si lancia anche da riga di comando: li' il modulo si chiama
`__main__` e, se `polyglot` lo importasse, Python ne caricherebbe una seconda
copia con un'altra `CampaignError`. Gli `except CampaignError` di `main()`
non riconoscerebbero allora gli errori di `polyglot`. Un modulo che nessuno
lancia come programma ha una sola copia.
"""

from dataclasses import dataclass, field


class CampaignError(Exception):
    """Errore di configurazione della campagna, rilevato prima di creare cartelle."""


@dataclass(frozen=True)
class Task:
    """Un task di prova con il suo comando di verifica.

    Attributes:
        id: nome del task, unico nella campagna.
        prompt: cio' che si dice all'agente.
        verify: comando shell, exit code 0 = riuscito.
        setup: comando shell eseguito nel workspace prima dell'incarico.
        files: file da scrivere nel workspace prima dell'incarico (percorso -> contenuto).
        restore: file da riscrivere prima della verifica (per esempio i test originali).
    """

    id: str
    prompt: str
    verify: str
    setup: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    restore: dict[str, str] = field(default_factory=dict)
