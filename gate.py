"""Cancello eseguibile D48/R2.6: accetta il sito solo da osservazioni accessibili all'agente.

Usa solo cio' che l'agente stesso puo' vedere nel workspace consegnato:
mai lo script del compito, mai valutazione/. La decisione non richiede modelli.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from renderer import RenderResult, render_site

GATE_DIR = "cancello"


@dataclass(frozen=True)
class GateVerdict:
    """Accettazione del sito e motivo dell'eventuale rifiuto."""

    accepted: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Restituisce il verdetto pronto per la serializzazione JSON."""
        return {"accepted": self.accepted, "reason": self.reason}


def verdict_from_render(resa: RenderResult) -> GateVerdict:
    """Decide da avvio, stato HTTP ed errori JavaScript, in questo ordine."""
    if not resa.started:
        return GateVerdict(False, f"non partito: {resa.start_error or 'motivo sconosciuto'}")
    larghezze = sorted(resa.widths)
    for w in larghezze:
        status = resa.widths[w].status
        if status is None:
            return GateVerdict(False, f"stato HTTP di / non registrato a {w} px (immagine del renderer da ricostruire)")
        if status >= 400:
            return GateVerdict(False, f"/ risponde con stato {status} a {w} px")
    totale_errori = sum(len(r.errors) for r in resa.widths.values())
    for w in larghezze:
        errori = resa.widths[w].errors
        if errori:
            motivo = f"errori JavaScript al caricamento a {w} px: {errori[0][:300]}"
            if totale_errori > 1:
                motivo += f" (+{totale_errori - 1} altri)"
            return GateVerdict(False, motivo)
    if not larghezze:
        return GateVerdict(False, "nessuna larghezza osservata")
    return GateVerdict(True)


def check_site(workspace: Path, out_dir: Path, *,
               render: Callable[..., RenderResult] = render_site) -> GateVerdict:
    """Osserva il sito senza script del compito e restituisce il verdetto.

    Raises:
        RenderError: guasto del renderer; si propaga senza diventare un rifiuto.
    """
    return verdict_from_render(render(workspace, out_dir, script=None))
