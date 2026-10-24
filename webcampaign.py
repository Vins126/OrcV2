"""Un compito web come task di campagna, verificato da renderer e script (R1.5).

La verifica di un sito scrive `valutazione.json` nella cartella della run, con
due blocchi separati:
- `cancello`: cio' che il sistema potra' leggere per decidere se rifare il
  lavoro (D48): avvio, errori, sbordo, accessibilita', versioni;
- `riservato`: cio' che serve solo alla misura e che nessun braccio deve mai
  vedere: «funziona», «funziona-server», esito dei passi, vetrina, screenshot.

La run e' «verificata» (per `f`) se il sito parte (P9-D2); la misura vera e'
«funziona», con credito parziale. Un guasto della valutazione e' un
`VerificationError` (`RenderError` ne e' un caso), mai uno 0.
"""

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from renderer import EvalResult, RenderResult, evaluate_site, render_site
from task_model import Shell, Task, Verification
from valutazione.libreria import ROTTA, raccogli
from webprompt import MATERIAL_DIR, build_prompt
from webtasks import WebTask, WebTaskError

PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PROJECT_ROOT / "campaigns" / "r1_valutazione"
EVALUATION_FILE = "valutazione.json"


def _ha_rotte(script: Path) -> bool:
    """Se lo script dichiara test delle rotte (cioe' se il compito ha un contratto)."""
    spec = importlib.util.spec_from_file_location("script_compito", script)
    if spec is None or spec.loader is None:
        raise WebTaskError(f"script non caricabile: {script}")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return any(p.tipo == ROTTA for p in raccogli(modulo))


def _cancello(resa: RenderResult) -> dict[str, Any]:
    return {
        "started": resa.started,
        "start_error": resa.start_error,
        "widths": {str(w): {"errors": r.errors, "overflow": r.overflow, "a11y": r.a11y}
                   for w, r in resa.widths.items()},
        "versions": resa.versions,
    }


def _riservato(resa: RenderResult, valutazione: EvalResult) -> dict[str, Any]:
    return {
        "funziona": valutazione.funziona,
        "funziona_server": valutazione.funziona_server,
        "steps": valutazione.steps,
        "vetrina": resa.vetrina,
        "screenshots": {str(w): str(r.screenshot) if r.screenshot else None for w, r in resa.widths.items()},
    }


def _riassunto(documento: dict[str, Any], percorso: Path) -> dict[str, Any]:
    """I numeri che vanno nella riga del manifesto; il resto sta nel file."""
    larghezze = documento["cancello"]["widths"]
    return {
        "path": str(percorso),
        "started": documento["cancello"]["started"],
        "funziona": documento["riservato"]["funziona"],
        "funziona_server": documento["riservato"]["funziona_server"],
        "errors": sum(len(v["errors"]) for v in larghezze.values()),
        "overflow_widths": [int(w) for w, v in larghezze.items() if v["overflow"]],
        "a11y_violations": sum(len(v["a11y"]) for v in larghezze.values()),
    }


@dataclass(frozen=True)
class WebVerifier:
    """Verifica un sito: renderer, poi script d'interazione; scrive valutazione.json.

    Attributes:
        script: lo script d'interazione del compito.
        render, evaluate: renderer e interprete; nei test, finti.
    """

    script: Path
    render: Callable[..., RenderResult] = field(default=render_site, compare=False)
    evaluate: Callable[..., EvalResult] = field(default=evaluate_site, compare=False)

    def __call__(self, workspace: Path, out_dir: Path, shell: Shell) -> Verification:
        """Valuta il sito di `workspace` e scrive `out_dir/valutazione.json`.

        Un sito che non parte vale 0 senza eseguire lo script: ogni passo
        aspetterebbe invano l'avvio. «funziona-server» vale 0 se il compito ha
        un contratto, `None` se non ce l'ha.

        Raises:
            VerificationError: guasto del renderer o dello script; nessun file scritto.
        """
        resa = self.render(workspace, out_dir / "screenshot", script=self.script)
        if resa.started:
            valutazione = self.evaluate(workspace, self.script)
        else:
            valutazione = EvalResult(funziona=0.0, funziona_server=0.0 if _ha_rotte(self.script) else None)
        documento = {"cancello": _cancello(resa), "riservato": _riservato(resa, valutazione)}
        out_dir.mkdir(parents=True, exist_ok=True)
        percorso = out_dir / EVALUATION_FILE
        percorso.write_text(json.dumps(documento, indent=1, ensure_ascii=False) + "\n")
        return Verification(verified=resa.started, summary={"evaluation": _riassunto(documento, percorso)})


def web_task_to_task(task: WebTask, *, scripts_dir: Path = SCRIPTS_DIR,
                     material_dir: Path = MATERIAL_DIR) -> Task:
    """Il task di campagna di un compito web: prompt dei bracci e verificatore del sito.

    Raises:
        WebTaskError: script del compito mancante, o materiale del prompt mancante o non valido.
    """
    script = Path(scripts_dir) / f"{task.candidate.id}.py"
    if not script.is_file():
        raise WebTaskError(f"script d'interazione mancante per il compito {task.candidate.id}: {script}")
    return Task(id=task.candidate.id, prompt=build_prompt(task, material_dir), verify=WebVerifier(script=script))
