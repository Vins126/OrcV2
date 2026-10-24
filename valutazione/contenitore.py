"""Esegue uno script d'interazione DENTRO l'immagine del renderer e scrive eval.json.

Per ogni passo il sito riparte da uno stato pulito: `/workspace` si svuota e si
riempie di nuovo dalla copia intatta in `/site` (in sola lettura), poi si lancia
`start.sh` e si aspetta la porta. Le cartelle pesanti e gia' costruite
(`node_modules`, `.venv`, `venv`) non si ricopiano: si collegano. Il sito gira
in `/workspace`, lo stesso percorso in cui l'agente l'ha costruito, cosi' i
percorsi assoluti scritti dagli strumenti (un venv di Python) restano validi.

Uso (dal lato dell'host lo compone `renderer.eval_command`):
    python3 -m valutazione.contenitore --script /eval/684.py --site /site
        --work /workspace --out /out --port 8080 --start-timeout 60
"""

# pyright: reportMissingImports=false

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from valutazione.browser import ContestoBrowser, attendi_porta
from valutazione.libreria import esegui, raccogli

#: Cartelle costruite dall'agente che si collegano invece di ricopiarle.
PESANTI = ("node_modules", ".venv", "venv")
VIEWPORT = {"width": 1440, "height": 900}


def ripristina(site: Path, work: Path) -> None:
    """Svuota `work` e lo riempie dalla copia intatta del sito."""
    for voce in work.iterdir():
        if voce.is_dir() and not voce.is_symlink():
            shutil.rmtree(voce)
        else:
            voce.unlink()
    for voce in site.iterdir():
        destinazione = work / voce.name
        if voce.name in PESANTI and voce.is_dir():
            destinazione.symlink_to(voce)
        elif voce.is_dir():
            shutil.copytree(voce, destinazione, symlinks=True)
        else:
            shutil.copy2(voce, destinazione)


class Server:
    """`start.sh` in un gruppo di processi suo, da fermare e riavviare."""

    def __init__(self, work: Path, porta: int, attesa: int):
        self.work, self.porta, self.attesa = work, porta, attesa
        self.processo: subprocess.Popen | None = None

    def avvia(self) -> None:
        log = open("/tmp/start.log", "a")
        self.processo = subprocess.Popen(["bash", "start.sh"], cwd=self.work, stdout=log, stderr=log,
                                         start_new_session=True)
        processo = self.processo
        if not attendi_porta(self.porta, self.attesa, lambda: processo.poll() is None):
            self.ferma()
            raise RuntimeError(f"server non partito: porta {self.porta} chiusa dopo {self.attesa} s")

    def ferma(self) -> None:
        if self.processo is None:
            return
        try:
            os.killpg(self.processo.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.processo.wait()
        self.processo = None
        # Il riavvio deve trovare la porta libera: si aspetta che smetta di rispondere.
        for _ in range(40):
            if not attendi_porta(self.porta, 0.1, lambda: False):
                break
            time.sleep(0.1)

    def riavvia(self) -> None:
        self.ferma()
        self.avvia()


def carica_script(percorso: Path):
    spec = importlib.util.spec_from_file_location("script_compito", percorso)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"script non caricabile: {percorso}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--script", type=Path, required=True)
    a.add_argument("--site", type=Path, required=True)
    a.add_argument("--work", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--port", type=int, required=True)
    a.add_argument("--start-timeout", type=int, required=True)
    args = a.parse_args()

    from playwright.sync_api import sync_playwright

    passi = raccogli(carica_script(args.script))
    with sync_playwright() as p:
        browser = p.chromium.launch()

        @contextmanager
        def nuovo_contesto():
            ripristina(args.site, args.work)
            server = Server(args.work, args.port, args.start_timeout)
            pagina = None
            try:
                server.avvia()
                pagina = browser.new_page(viewport=VIEWPORT)
                pagina.on("dialog", lambda d: d.accept())
                yield ContestoBrowser(pagina, f"http://127.0.0.1:{args.port}", server.riavvia,
                                      args.script.parent / "file")
            finally:
                if pagina is not None:
                    pagina.close()
                server.ferma()

        punteggio = esegui(passi, nuovo_contesto)
        browser.close()

    esito = {"funziona": punteggio.funziona, "funziona_server": punteggio.funziona_server,
             "steps": [asdict(e) for e in punteggio.esiti]}
    (args.out / "eval.json").write_text(json.dumps(esito, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
