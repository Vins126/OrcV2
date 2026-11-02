"""Il cancello R2.6 decide dal sito osservabile, senza script del compito o Docker vero."""

import ast
import json
import subprocess
from functools import partial
from pathlib import Path

import pytest

import gate
from executors.docker import ContainerLimiter
from gate import GATE_DIR, GateVerdict, check_site, verdict_from_render
from renderer import WIDTHS, RenderError, RenderResult, WidthResult, render_site


def _resa(*, statuses: dict[int, int | None] | None = None,
          errors: dict[int, list[str]] | None = None) -> RenderResult:
    return RenderResult(started=True, widths={
        w: WidthResult(width=w, status=(statuses or {}).get(w, 200),
                       errors=(errors or {}).get(w, []), overflow=False, screenshot=None)
        for w in reversed(WIDTHS)})


def test_g1_sito_non_partito_conserva_il_motivo():
    esito = verdict_from_render(RenderResult(started=False, start_error="porta 8080 chiusa"))

    assert esito == GateVerdict(False, "non partito: porta 8080 chiusa")


def test_g2_senza_motivo_di_avvio_usa_quello_sconosciuto():
    assert verdict_from_render(RenderResult(started=False)).reason == "non partito: motivo sconosciuto"


def test_g3_start_sh_mancante_rifiutato_senza_docker(tmp_path):
    esito = check_site(tmp_path, tmp_path / GATE_DIR)

    assert not esito.accepted
    assert "start.sh mancante" in (esito.reason or "")


def test_g4_sito_pulito_accettato_e_serializzabile():
    esito = verdict_from_render(_resa())

    assert esito == GateVerdict(accepted=True, reason=None)
    assert esito.to_dict() == {"accepted": True, "reason": None}


def test_g5_errore_a_una_sola_larghezza_rifiutato():
    esito = verdict_from_render(_resa(errors={768: ["pageerror: x non definito"]}))

    assert esito.to_dict() == {
        "accepted": False, "reason": "errori JavaScript al caricamento a 768 px: pageerror: x non definito"}


def test_g6_primo_errore_in_ordine_di_larghezza_e_conteggio_su_tutte():
    esito = verdict_from_render(_resa(errors={
        1440: ["ultimo"], 768: ["secondo", "terzo"], 375: ["primo", "altro"]}))

    assert esito.reason == "errori JavaScript al caricamento a 375 px: primo (+4 altri)"


def test_g7_errore_troncato_a_trecento_caratteri_prima_del_conteggio():
    esito = verdict_from_render(_resa(errors={768: ["x" * 301, "secondo"]}))

    assert esito.reason == "errori JavaScript al caricamento a 768 px: " + "x" * 300 + " (+1 altri)"


@pytest.mark.parametrize("status", [404, 500])
def test_g8_stato_http_di_errore_rifiutato(status):
    esito = verdict_from_render(_resa(statuses={768: status}))

    assert esito == GateVerdict(False, f"/ risponde con stato {status} a 768 px")


def test_g9_renderer_vecchio_richiede_di_ricostruire_immagine():
    esito = verdict_from_render(_resa(statuses={768: None}))

    assert esito == GateVerdict(
        False, "stato HTTP di / non registrato a 768 px (immagine del renderer da ricostruire)")


@pytest.mark.parametrize("status", [None, 404])
def test_g10_stati_controllati_prima_degli_errori_js(status):
    esito = verdict_from_render(_resa(statuses={1440: status}, errors={375: ["errore"]}))

    assert not esito.accepted
    assert "1440 px" in (esito.reason or "")
    assert "JavaScript" not in (esito.reason or "")


def test_g11_stati_controllati_in_ordine_di_larghezza():
    assert verdict_from_render(_resa(statuses={1440: None, 375: 500})).reason == (
        "/ risponde con stato 500 a 375 px")


def test_g12_nessuna_larghezza_osservata_rifiutato():
    assert verdict_from_render(RenderResult(started=True)) == GateVerdict(False, "nessuna larghezza osservata")


def test_g13_check_site_passa_script_none_esplicito_e_cartella_giusta(tmp_path):
    chiamate = []

    def render(workspace, out_dir, **kwargs):
        chiamate.append((workspace, out_dir, kwargs))
        return _resa()

    ws, out = tmp_path / "ws", tmp_path / GATE_DIR
    assert check_site(ws, out, render=render).accepted
    assert chiamate == [(ws, out, {"script": None})]
    assert GATE_DIR == "cancello"


def test_g14_check_site_propaga_guasto_del_renderer(tmp_path):
    guasto = RenderError("risultato mancante")

    def render(*args, **kwargs):
        raise guasto

    with pytest.raises(RenderError) as errore:
        check_site(tmp_path, tmp_path / GATE_DIR, render=render)
    assert errore.value is guasto


def test_g15_il_cancello_non_legge_la_valutazione(tmp_path):
    chiamate_script = []

    def render(workspace, out_dir, **kwargs):
        chiamate_script.append(kwargs)
        return _resa()

    check_site(tmp_path, tmp_path / GATE_DIR, render=render)
    assert chiamate_script == [{"script": None}]

    albero = ast.parse(Path(gate.__file__).read_text())
    docstring = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (nodo.body and isinstance(nodo.body[0], ast.Expr)
                    and isinstance(nodo.body[0].value, ast.Constant)
                    and isinstance(nodo.body[0].value.value, str)):
                docstring.add(nodo.body[0].value)
    vietati = {"valutazione", "webcampaign", "webtasks", "campaigns"}
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            assert not {a.name.split(".")[0] for a in nodo.names} & vietati
        elif isinstance(nodo, ast.ImportFrom):
            assert (nodo.module or "").split(".")[0] not in vietati
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and nodo not in docstring:
            assert "valutazione" not in nodo.value

    comandi = []

    def runner(cmd, **kwargs):
        comandi.append(cmd)
        volumi = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--volume"]
        out = Path(next(v.removesuffix(":/out") for v in volumi if v.endswith(":/out")))
        dati = {"started": True, "widths": {
            str(w): {"status": 200, "errors": [], "overflow": False, "screenshot": None, "a11y": []}
            for w in WIDTHS}}
        (out / "result.json").write_text(json.dumps(dati))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "start.sh").write_text("exit 0\n")
    limiter = ContainerLimiter(1, tmp_path / "slots")
    esito = check_site(ws, tmp_path / GATE_DIR, render=partial(render_site, runner=runner, limiter=limiter))

    assert esito.accepted
    assert len(comandi) == 1
    assert comandi[0][:2] == ["docker", "run"]
    assert "--script" not in comandi[0]
    assert not any("/eval" in arg or "valutazione" in arg for arg in comandi[0])
    volumi = [comandi[0][i + 1] for i, arg in enumerate(comandi[0]) if arg == "--volume"]
    assert len(volumi) == 2
    assert {v.split(":")[1] for v in volumi} == {"/workspace", "/out"}


def test_g16_sbordo_e_accessibilita_non_decidono_il_verdetto():
    resa = RenderResult(started=True, widths={375: WidthResult(
        width=375, status=200, errors=[], overflow=True, screenshot=None,
        a11y=[{"id": "image-alt", "impact": "critical", "nodes": 1}])})

    assert verdict_from_render(resa).accepted
