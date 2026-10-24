# pyright: reportMissingImports=false
# (playwright esiste solo nell'immagine del renderer, non nel venv del progetto)
"""Gira DENTRO l'immagine del renderer: avvia il sito, lo guarda, scrive result.json.

Passi: lancia `start.sh` in un gruppo di processi suo; aspetta che la porta
risponda entro il tempo concesso; per ogni larghezza apre una pagina nuova in
Chromium, raccoglie gli errori (eccezioni non gestite e `console.error`; le
risorse mancanti come la favicon non contano), aspetta i font, ferma
animazioni e transizioni, misura lo sbordo orizzontale, cerca con axe-core
le violazioni di accessibilita' gravi e fa uno screenshot a
pagina intera tagliato a un'altezza massima. Alla fine ferma il server.

Un sito che non apre la porta in tempo e' un esito (`started: false`), non un
errore di questo script. Qualunque altra eccezione fa uscire con codice 1
senza `result.json`: dal lato dell'host diventa un guasto della valutazione.
Lo prova `tests/test_renderer.py` (prove i1-i4, con Docker vero).
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

#: Altezza massima di uno screenshot: oltre, i token del giudice esplodono.
MAX_HEIGHT = 4000
#: Altezza della finestra: lo screenshot e' comunque a pagina intera.
VIEWPORT_HEIGHT = 900
#: Tolleranza dello sbordo orizzontale, in pixel (PROTOCOLLO §6).
OVERFLOW_TOLERANCE = 1
#: Impatti axe-core che contano (PROTOCOLLO §6).
A11Y_IMPACTS = ("critical", "serious")
AXE = "/opt/orc/axe.min.js"
STOP_ANIMATIONS = ("*,*::before,*::after{animation:none!important;transition:none!important;"
                   "caret-color:transparent!important}")


def porta_aperta(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def avvia(site: Path, port: int, timeout: int) -> tuple[subprocess.Popen, str | None]:
    """Lancia start.sh; restituisce il processo e un motivo se la porta non si apre."""
    log = open("/tmp/start.log", "w")
    processo = subprocess.Popen(["bash", "start.sh"], cwd=site, stdout=log, stderr=log,
                                start_new_session=True)
    scadenza = time.monotonic() + timeout
    while time.monotonic() < scadenza:
        if porta_aperta(port):
            return processo, None
        if processo.poll() is not None:
            return processo, f"start.sh e' terminato con codice {processo.returncode} senza aprire la porta {port}"
        time.sleep(0.25)
    return processo, f"porta {port} non aperta entro {timeout} s"


def ferma(processo: subprocess.Popen) -> None:
    try:
        os.killpg(processo.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def guarda(browser, url: str, width: int, out: Path) -> dict:
    pagina = browser.new_page(viewport={"width": width, "height": VIEWPORT_HEIGHT})
    errori: list[str] = []
    pagina.on("pageerror", lambda e: errori.append(f"pageerror: {e}"))
    pagina.on("console", lambda m: errori.append(f"console.error: {m.text}")
              if m.type == "error" and "Failed to load resource" not in m.text else None)
    pagina.goto(url, wait_until="load", timeout=30_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass  # un sito che interroga il server di continuo non arriva mai a networkidle
    pagina.evaluate("document.fonts ? document.fonts.ready.then(() => true) : true")
    pagina.add_style_tag(content=STOP_ANIMATIONS)
    sbordo = pagina.evaluate(
        "(t) => document.documentElement.scrollWidth > document.documentElement.clientWidth + t",
        OVERFLOW_TOLERANCE)
    altezza = pagina.evaluate("Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)")
    pagina.add_script_tag(path=AXE)
    violazioni = pagina.evaluate("async () => (await axe.run(document)).violations"
                                 ".map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length}))")
    accessibilita = [v for v in violazioni if v["impact"] in A11Y_IMPACTS]
    nome = f"shot-{width}.png"
    pagina.screenshot(path=str(out / nome), full_page=True,
                      clip={"x": 0, "y": 0, "width": width, "height": max(1, min(int(altezza), MAX_HEIGHT))},
                      animations="disabled")
    pagina.close()
    return {"errors": errori, "overflow": bool(sbordo), "screenshot": nome, "a11y": accessibilita}


def esegui_vetrina(script: Path, port: int) -> str:
    """Esegue `vetrina(c)` dello script, se c'e', sul server gia' avviato.

    Un errore della vetrina non ferma il rendering: gli screenshot si fanno sul
    sito com'e' e l'esito lo dice ("errore: ...").
    """
    import importlib.util
    from valutazione.browser import ContestoBrowser

    spec = importlib.util.spec_from_file_location("script_compito", script)
    if spec is None or spec.loader is None:
        return "errore: script non caricabile"
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    funzione = getattr(modulo, "vetrina", None)
    if funzione is None:
        return "assente"
    contesto = ContestoBrowser(None, f"http://127.0.0.1:{port}", lambda: None, script.parent / "file")
    try:
        funzione(contesto)
    except Exception as errore:
        return f"errore: {type(errore).__name__}: {errore}"
    return "ok"


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--site", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--port", type=int, required=True)
    a.add_argument("--widths", required=True)
    a.add_argument("--start-timeout", type=int, required=True)
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
                widths = {str(w): guarda(browser, url, w, args.out) for w in larghezze}
                versioni = {"chromium": browser.version,
                            "playwright": version("playwright")}
                browser.close()
            risultato = {"started": True, "start_error": None, "widths": widths, "versions": versioni,
                         "vetrina": vetrina}
    finally:
        ferma(processo)
    (args.out / "result.json").write_text(json.dumps(risultato, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
