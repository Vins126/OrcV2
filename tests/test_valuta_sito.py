"""Lo script d'interazione di un compito gira nel renderer e restituisce «funziona».

Nota di design (tesi):
    Come per il rendering, qui Docker non si lancia: un finto `runner` scrive
    l'`eval.json` che scriverebbe il container. Le prove con Docker vero usano
    una mini applicazione d'esempio (`tests/fixtures/valutazione/sito_items`) e
    uno script d'esempio, e si lanciano con `ORC_INTEGRATION=1`.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from renderer import (
    RENDERER_IMAGE,
    EvalResult,
    RenderError,
    eval_command,
    evaluate_site,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "valutazione"


def _valore(cmd: list[str], opzione: str) -> str:
    return cmd[cmd.index(opzione) + 1]


def _volumi(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, x in enumerate(cmd) if x == "--volume"]


def _workspace(tmp_path: Path, start: bool = True) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "index.html").write_text("<h1>ciao</h1>")
    if start:
        (ws / "start.sh").write_text("python3 -m http.server 8080\n")
    return ws


def _runner(contenuto=None, *, eccezione=None):
    chiamate: list[list[str]] = []

    def run(cmd, **kwargs):
        chiamate.append(cmd)
        if cmd[:2] == ["docker", "run"]:
            if eccezione is not None:
                raise eccezione
            out = Path(next(v.split(":")[0] for v in _volumi(cmd) if v.split(":")[1] == "/out"))
            if contenuto is not None:
                (out / "eval.json").write_text(contenuto)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run, chiamate


_ESITO = {"funziona": 50.0, "funziona_server": None,
          "steps": [{"id": "1", "tipo": "interfaccia", "stato": "superato", "motivo": ""},
                    {"id": "2", "tipo": "interfaccia", "stato": "fallito", "motivo": "Fallito: x"}]}


def test_e1_il_comando_monta_script_e_codice_in_sola_lettura_senza_rete(tmp_path):
    script = tmp_path / "s" / "684.py"
    cmd = eval_command(tmp_path / "site", script, tmp_path / "out", "orc-eval-x", start_timeout=9)

    assert cmd[:3] == ["docker", "run", "--rm"]
    assert _valore(cmd, "--network") == "none"
    assert _valore(cmd, "--user") == "1000:1000"
    assert _valore(cmd, "--name") == "orc-eval-x"
    volumi = _volumi(cmd)
    assert f"{script.parent}:/eval:ro" in volumi
    assert any(v.endswith(":/opt/orc/py:ro") for v in volumi)
    assert f"{tmp_path / 'site'}:/site:ro" in volumi
    assert RENDERER_IMAGE in cmd
    coda = " ".join(cmd[cmd.index(RENDERER_IMAGE) + 1:])
    assert "valutazione.contenitore" in coda and "/eval/684.py" in coda and "--start-timeout 9" in coda


def test_e2_l_esito_del_container_diventa_eval_result(tmp_path):
    run, _ = _runner(json.dumps(_ESITO))
    r = evaluate_site(_workspace(tmp_path), tmp_path / "s.py", runner=run)

    assert isinstance(r, EvalResult)
    assert r.funziona == 50 and r.funziona_server is None
    assert [s["stato"] for s in r.steps] == ["superato", "fallito"]


@pytest.mark.parametrize("contenuto", [None, "{non json", json.dumps({"steps": []})])
def test_e3_esito_mancante_o_illeggibile_e_un_guasto(tmp_path, contenuto):
    run, _ = _runner(contenuto)
    with pytest.raises(RenderError):
        evaluate_site(_workspace(tmp_path), tmp_path / "s.py", runner=run)


def test_e4_senza_start_sh_vale_0_e_non_si_lancia_nulla(tmp_path):
    run, chiamate = _runner(json.dumps(_ESITO))
    r = evaluate_site(_workspace(tmp_path, start=False), tmp_path / "s.py", runner=run)

    assert r.funziona == 0 and r.steps == [] and chiamate == []


def test_e5_tempo_scaduto_ferma_il_container_ed_e_un_guasto(tmp_path):
    run, chiamate = _runner(eccezione=subprocess.TimeoutExpired(["docker"], 1))
    with pytest.raises(RenderError, match="tempo"):
        evaluate_site(_workspace(tmp_path), tmp_path / "s.py", runner=run, timeout=1)
    nome = _valore(chiamate[0], "--name")
    # P19-D2 (24 ott): `rm -f` toglie anche un container mai partito, `kill` no.
    assert ["docker", "rm", "-f", nome] in [c[:4] for c in chiamate]


def test_e6_il_workspace_non_viene_toccato(tmp_path):
    ws = _workspace(tmp_path)
    prima = sorted(p.name for p in ws.iterdir())
    run, chiamate = _runner(json.dumps(_ESITO))
    evaluate_site(ws, tmp_path / "s.py", runner=run)

    assert sorted(p.name for p in ws.iterdir()) == prima
    assert f"{ws}:/site:ro" not in _volumi(chiamate[0])     # si monta una copia, mai l'originale


# ── Prove con Docker vero ──────────────────────────────────────────────────

_INTEGRAZIONE = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION") or shutil.which("docker") is None,
    reason="serve Docker con l'immagine orc-renderer:r1: ORC_INTEGRATION=1")


@_INTEGRAZIONE
def test_i6_lo_script_d_esempio_da_100_sul_sito_giusto(tmp_path):
    ws = tmp_path / "ws"
    shutil.copytree(FIXTURES / "sito_items", ws)

    r = evaluate_site(ws, FIXTURES / "script_items.py", start_timeout=20)

    assert r.funziona == 100, r.steps
    assert r.funziona_server == 100, r.steps
    assert not (ws / "data").exists()                       # i dati restano nella copia


@_INTEGRAZIONE
def test_i7_sul_sito_vuoto_vale_0_e_i_passi_preparati_sono_non_valutabili(tmp_path):
    ws = tmp_path / "ws"
    shutil.copytree(FIXTURES / "sito_vuoto", ws)

    r = evaluate_site(ws, FIXTURES / "script_items.py", start_timeout=20)

    stati = {s["id"]: s["stato"] for s in r.steps}
    assert r.funziona == 0
    assert stati["1"] == "fallito" and stati["2"] == "non_valutabile"
    assert stati["3"] == "fallito"                           # dipende dal passo 1, fallito
    assert r.funziona_server == 0


@_INTEGRAZIONE
@pytest.mark.parametrize("compito, riferimento", [
    ("684", "rif_684"), ("000098", "rif_000098"), ("000040", "rif_000040"),
    ("000058", "rif_000058"), ("842", "rif_842")])
def test_i8_gli_script_veri_danno_100_sul_riferimento_e_0_sul_sito_vuoto(tmp_path, compito, riferimento):
    script = Path(__file__).resolve().parent.parent / "campaigns" / "r1_valutazione" / f"{compito}.py"

    giusto = evaluate_site(FIXTURES / riferimento, script, start_timeout=20)
    vuoto = evaluate_site(FIXTURES / "sito_vuoto", script, start_timeout=20)

    server_atteso = None if compito == "842" else 100     # 842 non ha contratto delle rotte
    assert (giusto.funziona, giusto.funziona_server) == (100, server_atteso), giusto.steps
    assert vuoto.funziona == 0 and vuoto.funziona_server in (0, None)
