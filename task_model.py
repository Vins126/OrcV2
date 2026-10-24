"""Tipi condivisi della campagna: il task e l'errore di configurazione.

Stanno in un modulo a parte perche' li usano sia `campaign` sia `polyglot`, e
`campaign.py` si lancia anche da riga di comando: li' il modulo si chiama
`__main__` e, se `polyglot` lo importasse, Python ne caricherebbe una seconda
copia con un'altra `CampaignError`. Gli `except CampaignError` di `main()`
non riconoscerebbero allora gli errori di `polyglot`. Un modulo che nessuno
lancia come programma ha una sola copia.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

#: Chi esegue un comando shell nel workspace di una run e ne restituisce l'exit code.
Shell = Callable[[Path, str], int]


class CampaignError(Exception):
    """Errore di configurazione della campagna, rilevato prima di creare cartelle."""


class VerificationError(CampaignError):
    """Guasto della verifica (esito illeggibile, tempo scaduto): non e' un giudizio sul lavoro."""


@dataclass(frozen=True)
class Verification:
    """Esito di una verifica.

    Attributes:
        verified: il lavoro e' accettato (per `f`).
        summary: campi da aggiungere alla riga del manifesto; vuoto per un comando shell.
    """

    verified: bool
    summary: dict[str, Any] = field(default_factory=dict)


class Verifier(Protocol):
    """Verifica il lavoro di una run nel suo workspace; puo' scrivere i suoi file in `out_dir`."""

    def __call__(self, workspace: Path, out_dir: Path, shell: Shell) -> Verification: ...


class ShellVerifier(str):
    """Un comando shell come verificatore: exit code 0 = riuscito.

    E' una stringa, quindi resta uguale al comando scritto nel TOML e si puo'
    leggere e confrontare come prima; in piu' sa eseguirsi.
    """

    def __call__(self, workspace: Path, out_dir: Path, shell: Shell) -> Verification:
        return Verification(verified=shell(workspace, str(self)) == 0)


def as_verifier(verify: "str | Verifier") -> Verifier:
    """Il verificatore di un task: un testo e' un comando shell, il resto si usa com'e'."""
    return verify if callable(verify) else ShellVerifier(verify)


@dataclass(frozen=True)
class Task:
    """Un task di prova con il suo comando di verifica.

    Attributes:
        id: nome del task, unico nella campagna.
        prompt: cio' che si dice all'agente.
        verify: comando shell (exit code 0 = riuscito) oppure un verificatore,
            per esempio quello dei siti (`webcampaign.WebVerifier`).
        setup: comando shell eseguito nel workspace prima dell'incarico.
        files: file da scrivere nel workspace prima dell'incarico (percorso -> contenuto).
        restore: file da riscrivere prima della verifica (per esempio i test originali).
    """

    id: str
    prompt: str
    verify: "str | Verifier"
    setup: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    restore: dict[str, str] = field(default_factory=dict)
