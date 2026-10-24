"""Il contesto dei passi con il browser vero: gira solo nell'immagine del renderer.

Uno script chiama questi metodi; ogni elemento si trova SOLO tramite il suo
marcatore `data-testid` (PROTOCOLLO §6). Le attese sono brevi e fisse (5 s per
azione), uguali per tutti i bracci. Non e' coperto dai test unitari: lo provano
le prove reali di `tests/test_valuta_sito.py` (i6, i7).
"""

# pyright: reportMissingImports=false
# (playwright esiste solo nell'immagine del renderer, non nel venv del progetto)

import json as json_lib
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from valutazione.libreria import Fallito, NonValutabile

#: Attesa massima di ogni azione e di ogni «visibile», in millisecondi.
ATTESA_MS = 5_000


@dataclass(frozen=True)
class Risposta:
    """Risposta di una rotta: codice, testo e, se c'e', il JSON."""

    status: int
    testo: str

    @property
    def json(self) -> Any:
        try:
            return json_lib.loads(self.testo)
        except ValueError:
            return None


def _multipart(campo: str, file: Path) -> tuple[bytes, str]:
    confine = uuid.uuid4().hex
    testa = (f"--{confine}\r\nContent-Disposition: form-data; name=\"{campo}\"; "
             f"filename=\"{file.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    corpo = testa + file.read_bytes() + f"\r\n--{confine}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={confine}"


class ContestoBrowser:
    """Cio' che un passo puo' fare: pagina, rotte, riavvio del server, attesi."""

    def __init__(self, pagina, base_url: str, riavvia: Callable[[], None], cartella_file: Path):
        self.pagina = pagina
        self.base_url = base_url.rstrip("/")
        self._riavvia = riavvia
        self.cartella_file = cartella_file

    # ── pagina ──────────────────────────────────────────────────────────────

    def apri(self, percorso: str = "/") -> None:
        self.pagina.goto(self.base_url + percorso, wait_until="load", timeout=30_000)
        try:
            self.pagina.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass  # un sito che interroga il server di continuo non arriva mai a networkidle

    def ricarica(self) -> None:
        self.pagina.reload(wait_until="load", timeout=30_000)
        try:
            self.pagina.wait_for_load_state("networkidle", timeout=3_000)
        except Exception:
            pass

    def aspetta(self, secondi: float) -> None:
        self.pagina.wait_for_timeout(secondi * 1000)

    def elementi(self, marcatore: str, *, dentro=None, testo: str | None = None):
        """Tutti gli elementi con quel marcatore, eventualmente dentro un altro e con un testo."""
        radice = dentro if dentro is not None else self.pagina
        trovati = radice.get_by_test_id(marcatore)
        return trovati.filter(has_text=testo) if testo is not None else trovati

    def elemento(self, marcatore: str, *, dentro=None, testo: str | None = None, n: int = 0):
        return self.elementi(marcatore, dentro=dentro, testo=testo).nth(n)

    def clicca(self, marcatore: str, *, dentro=None, testo: str | None = None, n: int = 0) -> None:
        self.elemento(marcatore, dentro=dentro, testo=testo, n=n).click(timeout=ATTESA_MS)

    def scrivi(self, marcatore: str, valore: str, *, dentro=None, n: int = 0) -> None:
        self.elemento(marcatore, dentro=dentro, n=n).fill(valore, timeout=ATTESA_MS)

    def carica_file(self, marcatore: str, nome: str, *, dentro=None, n: int = 0) -> None:
        self.elemento(marcatore, dentro=dentro, n=n).set_input_files(
            str(self.cartella_file / nome), timeout=ATTESA_MS)

    def visibile(self, marcatore: str, *, dentro=None, testo: str | None = None,
                 attesa_ms: int = ATTESA_MS) -> bool:
        try:
            self.elementi(marcatore, dentro=dentro, testo=testo).first.wait_for(
                state="visible", timeout=attesa_ms)
            return True
        except Exception:
            return False

    def conta(self, marcatore: str, *, dentro=None, testo: str | None = None) -> int:
        """Quanti elementi visibili hanno quel marcatore (aspetta che compaia il primo)."""
        trovati = self.elementi(marcatore, dentro=dentro, testo=testo)
        try:
            trovati.first.wait_for(state="visible", timeout=ATTESA_MS)
        except Exception:
            return 0
        return sum(1 for i in range(trovati.count()) if trovati.nth(i).is_visible())

    def testo(self, marcatore: str, *, dentro=None, n: int = 0) -> str:
        return self.elemento(marcatore, dentro=dentro, n=n).inner_text(timeout=ATTESA_MS)

    def testi(self, marcatore: str, *, dentro=None) -> list[str]:
        if not self.visibile(marcatore, dentro=dentro):
            return []
        return self.elementi(marcatore, dentro=dentro).all_inner_texts()

    def stile(self, marcatore: str, proprieta: str, *, dentro=None, n: int = 0) -> str:
        """Valore calcolato di una proprieta' CSS, es. `background-color` -> `rgb(255, 239, 213)`."""
        return self.elemento(marcatore, dentro=dentro, n=n).evaluate(
            "(e, p) => getComputedStyle(e).getPropertyValue(p)", proprieta, timeout=ATTESA_MS)

    def attributo(self, marcatore: str, nome: str, *, dentro=None, n: int = 0) -> str | None:
        return self.elemento(marcatore, dentro=dentro, n=n).get_attribute(nome, timeout=ATTESA_MS)

    # ── rotte e server ──────────────────────────────────────────────────────

    def api(self, metodo: str, percorso: str, *, json: Any = None, file: str | None = None,
            campo: str = "file") -> Risposta:
        """Chiama una rotta del sito. Una risposta 4xx/5xx non e' un'eccezione."""
        corpo: bytes | None = None
        intestazioni: dict[str, str] = {}
        if file is not None:
            corpo, tipo = _multipart(campo, self.cartella_file / file)
            intestazioni["Content-Type"] = tipo
        elif json is not None:
            corpo = json_lib.dumps(json).encode()
            intestazioni["Content-Type"] = "application/json"
        richiesta = urllib.request.Request(self.base_url + percorso, data=corpo, method=metodo,
                                           headers=intestazioni)
        try:
            with urllib.request.urlopen(richiesta, timeout=10) as r:
                return Risposta(r.status, r.read().decode(errors="replace"))
        except urllib.error.HTTPError as errore:
            return Risposta(errore.code, errore.read().decode(errors="replace"))

    def prepara(self, metodo: str, percorso: str, **opzioni: Any) -> Risposta:
        """Come `api`, ma se la rotta non risponde o da' 4xx/5xx il passo e' «non valutabile»."""
        try:
            risposta = self.api(metodo, percorso, **opzioni)
        except OSError as errore:
            raise NonValutabile(f"preparazione {metodo} {percorso}: {errore}") from errore
        if risposta.status >= 400:
            raise NonValutabile(f"preparazione {metodo} {percorso}: {risposta.status}")
        return risposta

    def riavvia_server(self) -> None:
        """Ferma e riavvia `start.sh` sugli stessi dati; aspetta la porta."""
        self._riavvia()

    # ── esito ───────────────────────────────────────────────────────────────

    def atteso(self, condizione: bool, messaggio: str) -> None:
        if not condizione:
            raise Fallito(messaggio)


def attendi_porta(porta: int, secondi: float, vivo: Callable[[], bool]) -> bool:
    """True se la porta risponde entro `secondi`; False se scade o se il server muore."""
    import socket
    scadenza = time.monotonic() + secondi
    while time.monotonic() < scadenza:
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.5):
                return True
        except OSError:
            if not vivo():
                return False
            time.sleep(0.25)
    return False
