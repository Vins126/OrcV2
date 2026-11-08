# pyright: reportMissingImports=false
# (playwright esiste solo nell'immagine del renderer, non nel venv del progetto)
"""Gira DENTRO l'immagine `orc-renderer:r1t`: la pagina `/` intera, in riquadri, per il giudice.

Serve solo al giudizio di sensibilita' di MH-4 (P6-D1 d): il giudizio principale
usa gli screenshot di `render_site.py`, tagliati a 4000 px, su cui il giudice e'
stato calibrato. Qui la pagina si divide in riquadri alti quanto la finestra,
dall'alto in basso, fino a un tetto; si registra l'altezza vera della pagina e
se il tetto l'ha tagliata.

Avvio del sito, vetrina e arresto sono quelli di `render_site.py`, importati
senza cambiarli: il sito si guarda nello stesso modo, cambia solo lo scatto.
Come `render_site.py`, un sito che non parte e' un esito (`started: false`) e
qualunque altra eccezione fa uscire con codice 1 senza `result.json`.
"""

import argparse
import json
from pathlib import Path

from render_site import STOP_ANIMATIONS, VIEWPORT_HEIGHT, avvia, esegui_vetrina, ferma


def ritagli(altezza: int, finestra: int, tetto: int) -> list[tuple[int, int]]:
    """Inizio e altezza di ogni riquadro, contigui, fino a `tetto` riquadri.

    Una pagina vuota da' comunque un riquadro alto 1 px: Playwright rifiuta
    un ritaglio di altezza 0, e il giudice deve vedere qualcosa per ogni larghezza.
    """
    if altezza <= 0:
        return [(0, 1)]
    riquadri = []
    inizio = 0
    while inizio < altezza and len(riquadri) < tetto:
        riquadri.append((inizio, min(finestra, altezza - inizio)))
        inizio += finestra
    return riquadri


def tagliata(altezza: int, finestra: int, tetto: int) -> bool:
    """Vero se la pagina continua oltre l'ultimo riquadro concesso."""
    return altezza > finestra * tetto


def guarda(browser, url: str, width: int, out: Path, tetto: int) -> dict:
    """Stessa attesa di `render_site.guarda` (load, networkidle, font, animazioni ferme), poi i riquadri."""
    pagina = browser.new_page(viewport={"width": width, "height": VIEWPORT_HEIGHT})
    pagina.goto(url, wait_until="load", timeout=30_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass  # un sito che interroga il server di continuo non arriva mai a networkidle
    pagina.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true")
    pagina.add_style_tag(content=STOP_ANIMATIONS)
    altezza = int(pagina.evaluate(
        "Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)"))
    nomi = []
    for numero, (inizio, alto) in enumerate(ritagli(altezza, VIEWPORT_HEIGHT, tetto), 1):
        nome = f"tile-{width}-{numero:02d}.png"
        pagina.screenshot(path=str(out / nome), full_page=True,
                          clip={"x": 0, "y": inizio, "width": width, "height": alto},
                          animations="disabled")
        nomi.append(nome)
    pagina.close()
    return {"height": altezza, "tiles": nomi, "truncated": tagliata(altezza, VIEWPORT_HEIGHT, tetto)}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--site", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--port", type=int, required=True)
    a.add_argument("--widths", required=True)
    a.add_argument("--start-timeout", type=int, required=True)
    a.add_argument("--max-tiles", type=int, required=True)
    a.add_argument("--script", type=Path, default=None)
    args = a.parse_args()
    larghezze = [int(w) for w in args.widths.split(",")]

    from importlib.metadata import version
    from playwright.sync_api import sync_playwright

    processo, motivo = avvia(args.site, args.port, args.start_timeout)
    try:
        if motivo is not None:
            risultato = {"started": False, "start_error": motivo, "widths": {}, "versions": {}}
        else:
            vetrina = esegui_vetrina(args.script, args.port) if args.script is not None else None
            with sync_playwright() as p:
                browser = p.chromium.launch()
                url = f"http://127.0.0.1:{args.port}/"
                widths = {str(w): guarda(browser, url, w, args.out, args.max_tiles) for w in larghezze}
                versioni = {"chromium": browser.version, "playwright": version("playwright")}
                browser.close()
            risultato = {"started": True, "start_error": None, "widths": widths, "versions": versioni,
                         "vetrina": vetrina}
    finally:
        ferma(processo)
    (args.out / "result.json").write_text(json.dumps(risultato, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
