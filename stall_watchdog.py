"""Controllo di stallo di uno stream: scatta se per troppo tempo non arriva un chunk."""

import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


class StallWatchdog:
    """Chiama `on_stall` se per `timeout_s` secondi nessuno chiama `touch`.

    Nota di design (tesi):
        Il timeout di rete (livello 1) si azzera a ogni byte, anche ai commenti
        keep-alive che il fornitore manda nelle pause: scopre una connessione
        morta, non un modello che non produce. Questo controllo guarda solo i
        chunk interpretati, cioe' quelli che l'SDK consegna al gateway.

        Gira su un thread a parte perche' la lettura del flusso e' bloccante e
        non puo' controllarsi da sola.
    """

    def __init__(self, timeout_s: float, on_stall: Callable[[], None],
                 clock: Callable[[], float] = time.monotonic):
        """Args:
            timeout_s: secondi senza chunk dopo i quali scattare.
            on_stall: cosa fare quando scatta (si esegue sul thread del controllo).
            clock: orologio, iniettato per i test.

        Raises:
            ValueError: se `timeout_s` non e' positivo.
        """
        if timeout_s <= 0:
            raise ValueError("timeout_s deve essere positivo")
        self._timeout_s = timeout_s
        self._on_stall = on_stall
        self._clock = clock
        self._ultimo_chunk = clock()
        self._fermo = threading.Event()
        self._scattato = threading.Event()
        self._thread = threading.Thread(target=self._controlla, name="stall-watchdog", daemon=True)

    @property
    def fired(self) -> bool:
        """Vero se e' scattato."""
        return self._scattato.is_set()

    def start(self) -> None:
        """Avvia il controllo: l'attesa parte da adesso."""
        self._ultimo_chunk = self._clock()
        self._thread.start()

    def touch(self) -> None:
        """Segnala che e' arrivato un chunk."""
        self._ultimo_chunk = self._clock()

    def stop(self) -> None:
        """Ferma il controllo senza farlo scattare."""
        self._fermo.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def _controlla(self) -> None:
        # Si guarda spesso rispetto alla soglia (un quarto, al massimo ogni secondo)
        # per scattare con poco ritardo senza consumare un thread in attesa attiva.
        intervallo = max(0.01, min(self._timeout_s / 4, 1.0))
        while not self._fermo.wait(intervallo):
            if self._clock() - self._ultimo_chunk >= self._timeout_s:
                self._scattato.set()
                try:
                    self._on_stall()
                except Exception:  # il controllo non deve morire in silenzio ne' far crollare il processo
                    log.exception("Interruzione dello stream fallita dopo uno stallo")
                return
