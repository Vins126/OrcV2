"""Un compito web diventa un task di campagna; la sua verifica scrive valutazione.json (R1.5).

Nota di design (tesi):
    La verifica di un sito non e' un exit code: e' un documento con due blocchi.
    `cancello` contiene solo cio' che il sistema potra' leggere per decidere se
    rifare il lavoro (D48: avvio, errori, sbordo, accessibilita'); `riservato`
    contiene cio' che serve alla misura e che nessun braccio deve mai vedere
    (punteggi, passi dello script, screenshot del giudice, vetrina). `f` resta
    calcolabile: una run riesce se e' finita regolarmente e il sito parte (P9-D2).
    Un guasto della valutazione e' un errore (`VerificationError`), non uno 0.
    Qui renderer e script sono finti: le prove con Docker vero stanno nei test
    del renderer.
"""

import json
from pathlib import Path

import pytest

from renderer import EvalResult, RenderError, RenderResult, WidthResult
from task_model import ShellVerifier, Task, Verification, VerificationError, as_verifier
from webcampaign import SCRIPTS_DIR, WebVerifier, web_task_to_task
from webprompt import build_prompt
from webtasks import ARTIFACTS, Candidate, WebTask, WebTaskError

COMPITI = ("000098", "000040", "000058", "684", "842")
CAMPI_CANCELLO = {"started", "start_error", "widths", "versions"}
CAMPI_RISERVATO = {"funziona", "funziona_server", "steps", "vetrina", "screenshots"}


def _resa(started: bool = True) -> RenderResult:
    if not started:
        return RenderResult(started=False, start_error="porta 8080 chiusa dopo 60 s", versions={"chromium": "1"})
    larghezze = {w: WidthResult(width=w, errors=["TypeError: x"] if w == 375 else [], overflow=w == 375,
                                screenshot=Path(f"/tmp/{w}.png"),
                                a11y=[{"id": "color-contrast", "impact": "serious", "nodes": 2}])
                 for w in (375, 768, 1440)}
    return RenderResult(started=True, widths=larghezze, versions={"chromium": "1"}, vetrina="ok")


class Finti:
    """Renderer e script finti che registrano le chiamate."""

    def __init__(self, resa: RenderResult | Exception, valutazione: EvalResult | Exception | None = None):
        self.resa, self.valutazione = resa, valutazione
        self.chiamate: list[str] = []

    def render(self, workspace, out_dir, *, script=None):
        self.chiamate.append("render")
        if isinstance(self.resa, Exception):
            raise self.resa
        return self.resa

    def evaluate(self, workspace, script):
        self.chiamate.append("evaluate")
        if isinstance(self.valutazione, Exception):
            raise self.valutazione
        return self.valutazione or EvalResult(funziona=75.0, funziona_server=50.0,
                                              steps=[{"id": "1", "tipo": "interfaccia", "stato": "superato"}])


def _script(tmp_path: Path, con_rotte: bool) -> Path:
    file = tmp_path / "s.py"
    corpo = "from valutazione.libreria import passo, rotta\n\n@passo('1', origine='x')\ndef a(c):\n    pass\n"
    if con_rotte:
        corpo += "\n@rotta('T1', origine='x')\ndef b(c):\n    pass\n"
    file.write_text(corpo)
    return file


def _verifica(tmp_path: Path, finti: Finti, con_rotte: bool = True) -> tuple[Verification, dict]:
    verificatore = WebVerifier(script=_script(tmp_path, con_rotte), render=finti.render, evaluate=finti.evaluate)
    out = tmp_path / "out"
    esito = verificatore(tmp_path / "ws", out, lambda w, c: 0)
    return esito, json.loads((out / "valutazione.json").read_text())


# ── Il documento di valutazione ────────────────────────────────────────────

def test_v1_sito_che_parte_documento_con_i_due_blocchi_e_run_verificata(tmp_path):
    esito, documento = _verifica(tmp_path, Finti(_resa()))

    assert esito.verified is True
    assert set(documento) == {"cancello", "riservato"}
    assert set(documento["cancello"]) == CAMPI_CANCELLO
    assert set(documento["riservato"]) == CAMPI_RISERVATO
    assert documento["riservato"]["funziona"] == 75.0
    assert documento["riservato"]["funziona_server"] == 50.0
    assert documento["cancello"]["widths"]["375"] == {
        "errors": ["TypeError: x"], "overflow": True,
        "a11y": [{"id": "color-contrast", "impact": "serious", "nodes": 2}]}


def test_v2_il_cancello_non_contiene_nulla_della_misura(tmp_path):
    # D48: il cancello del sistema non deve mai ricevere passi, punteggi o screenshot del giudice.
    _, documento = _verifica(tmp_path, Finti(_resa()))

    testo = json.dumps(documento["cancello"])
    for parola in ("funziona", "steps", "screenshot", "vetrina", "superato", ".png"):
        assert parola not in testo, parola


def test_v3_il_riassunto_per_il_manifesto(tmp_path):
    esito, _ = _verifica(tmp_path, Finti(_resa()))

    assert esito.summary == {"evaluation": {
        "path": str(tmp_path / "out" / "valutazione.json"), "started": True, "funziona": 75.0,
        "funziona_server": 50.0, "errors": 1, "overflow_widths": [375], "a11y_violations": 3}}


@pytest.mark.parametrize("con_rotte, server_atteso", [(True, 0.0), (False, None)])
def test_v4_sito_che_non_parte_vale_zero_senza_eseguire_lo_script(tmp_path, con_rotte, server_atteso):
    finti = Finti(_resa(started=False))

    esito, documento = _verifica(tmp_path, finti, con_rotte=con_rotte)

    assert esito.verified is False
    assert finti.chiamate == ["render"]
    assert documento["riservato"]["funziona"] == 0.0
    assert documento["riservato"]["funziona_server"] == server_atteso
    assert documento["cancello"]["start_error"] == "porta 8080 chiusa dopo 60 s"


@pytest.mark.parametrize("dove", ("render", "evaluate"))
def test_v5_un_guasto_della_valutazione_e_un_verification_error(tmp_path, dove):
    guasto = RenderError("result.json non e' JSON valido")
    finti = Finti(guasto if dove == "render" else _resa(), guasto if dove == "evaluate" else None)

    with pytest.raises(VerificationError):
        _verifica(tmp_path, finti)
    assert not (tmp_path / "out" / "valutazione.json").exists()


# ── Dal compito al task ────────────────────────────────────────────────────

def _webtask(id_: str) -> WebTask:
    return WebTask(candidate=Candidate(id=id_, source=ARTIFACTS, label="x", text="Build it."), kind="applicazione")


def test_v6_il_task_ha_il_prompt_dei_bracci_e_lo_script_del_compito():
    task = web_task_to_task(_webtask("842"))

    assert isinstance(task, Task)
    assert task.id == "842"
    assert task.prompt == build_prompt(_webtask("842"))
    assert isinstance(task.verify, WebVerifier)
    assert task.verify.script == SCRIPTS_DIR / "842.py"


def test_v7_script_mancante_e_un_errore_prima_di_generare(tmp_path):
    with pytest.raises(WebTaskError, match="842"):
        web_task_to_task(_webtask("842"), scripts_dir=tmp_path)


@pytest.mark.parametrize("id_", COMPITI)
def test_v8_ogni_compito_di_sviluppo_ha_il_suo_script(id_):
    assert (SCRIPTS_DIR / f"{id_}.py").is_file()


def test_v9_un_comando_shell_diventa_un_verificatore_uguale_al_testo():
    task = Task(id="a", prompt="p", verify="pytest -q")
    chiamate = []

    verificatore = as_verifier(task.verify)
    esito = verificatore(Path("/w"), Path("/o"), lambda w, c: chiamate.append((w, c)) or 1)

    assert isinstance(verificatore, ShellVerifier) and verificatore == "pytest -q"
    assert as_verifier(verificatore) is verificatore
    assert chiamate == [(Path("/w"), "pytest -q")]
    assert esito == Verification(verified=False)
