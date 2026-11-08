"""Riquadri della pagina intera per il giudizio di sensibilita' (MH-4, P6-D1 d).

Nota di design (tesi):
    I riquadri servono solo al giudice: `view_site`, cancello e valutazione
    restano sull'immagine `orc-renderer:r1` e su `render_site.py`, identici
    alla campagna. Qui Docker non si lancia: il runner finto di
    `tests/test_renderer.py` fa la parte del container. Le prove con Docker
    vero e l'immagine `orc-renderer:r1t` si lanciano con `ORC_INTEGRATION=1`.
"""

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

from renderer import (
    RENDERER_IMAGE,
    TILES_IMAGE,
    WIDTHS,
    RenderError,
    docker_command,
    render_tiles,
    tiles_command,
)
from tests.test_renderer import _runner, _valore, _workspace

DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"


def _render_tiles_module(monkeypatch):
    """Carica `docker/render_tiles.py` come nel container, dove `render_site.py` gli sta accanto."""
    monkeypatch.syspath_prepend(str(DOCKER_DIR))
    spec = importlib.util.spec_from_file_location("render_tiles", DOCKER_DIR / "render_tiles.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ── Ritagli (funzione pura dello script del container) ─────────────────────

@pytest.mark.parametrize(("altezza", "attesi"), [
    (500, [(0, 500)]),
    (900, [(0, 900)]),
    (901, [(0, 900), (900, 1)]),
    (3000, [(0, 900), (900, 900), (1800, 900), (2700, 300)]),
])
def test_t1_i_ritagli_coprono_la_pagina_senza_buchi_ne_sovrapposizioni(monkeypatch, altezza, attesi):
    ritagli = _render_tiles_module(monkeypatch).ritagli(altezza, 900, 20)

    assert ritagli == attesi
    assert sum(h for _, h in ritagli) == altezza
    assert all(y == prima_y + prima_h for (prima_y, prima_h), (y, _) in zip(ritagli, ritagli[1:]))


def test_t2_il_tetto_ferma_i_ritagli_e_la_pagina_risulta_tagliata(monkeypatch):
    modulo = _render_tiles_module(monkeypatch)

    ritagli = modulo.ritagli(20_000, 900, 20)

    assert len(ritagli) == 20 and ritagli[-1] == (17_100, 900)
    assert modulo.tagliata(20_000, 900, 20) and not modulo.tagliata(18_000, 900, 20)


def test_t3_una_pagina_vuota_da_comunque_un_riquadro(monkeypatch):
    assert _render_tiles_module(monkeypatch).ritagli(0, 900, 20) == [(0, 1)]


# ── Comando del container: l'immagine della campagna non cambia ────────────

def test_t4_i_riquadri_usano_un_immagine_e_uno_script_propri(tmp_path):
    cmd = tiles_command(tmp_path / "site", tmp_path / "out", "n", max_tiles=12,
                        script=tmp_path / "s" / "684.py", code=tmp_path / "py")

    assert TILES_IMAGE in cmd and RENDERER_IMAGE not in cmd
    assert "/opt/orc/render_tiles.py" in cmd and "/opt/orc/render_site.py" not in cmd
    assert _valore(cmd, "--max-tiles") == "12"
    assert _valore(cmd, "--network") == "none"
    assert "--script" in cmd


def test_t5_view_site_cancello_e_valutazione_restano_sull_immagine_della_campagna(tmp_path):
    cmd = docker_command(tmp_path / "site", tmp_path / "out", "n")

    assert RENDERER_IMAGE == "orc-renderer:r1"
    assert RENDERER_IMAGE in cmd and TILES_IMAGE not in cmd
    assert "/opt/orc/render_site.py" in cmd and "--max-tiles" not in cmd


# ── Esito ──────────────────────────────────────────────────────────────────

def _risultato_riquadri(out: Path, conteggi: dict[int, int], *, tagliata: int | None = None) -> dict:
    widths = {}
    for w in WIDTHS:
        nomi = []
        for k in range(1, conteggi[w] + 1):
            nome = f"tile-{w}-{k:02d}.png"
            (out / nome).write_bytes(b"\x89PNG finto " + nome.encode())
            nomi.append(nome)
        widths[str(w)] = {"height": conteggi[w] * 900 - 100, "tiles": nomi, "truncated": w == tagliata}
    return {"started": True, "start_error": None, "widths": widths, "vetrina": "ok",
            "versions": {"chromium": "1", "playwright": "1.64.0"}}


def test_t6_un_risultato_a_riquadri_diventa_tiles_result(tmp_path):
    conteggi = {375: 5, 768: 3, 1440: 2}
    run, chiamate = _runner(lambda out, site: json.dumps(_risultato_riquadri(out, conteggi, tagliata=375)))

    r = render_tiles(_workspace(tmp_path), tmp_path / "esito", max_tiles=20, runner=run,
                     script=tmp_path / "s.py")

    assert r.started and r.vetrina == "ok"
    for w in WIDTHS:
        assert len(r.widths[w].tiles) == conteggi[w]
        assert all(p.is_file() and p.parent == tmp_path / "esito" for p in r.widths[w].tiles)
        assert r.widths[w].height == conteggi[w] * 900 - 100
    assert [p.name for p in r.widths[1440].tiles] == ["tile-1440-01.png", "tile-1440-02.png"]
    assert r.widths[375].truncated and not r.widths[1440].truncated
    assert TILES_IMAGE in chiamate[0]


def test_t7_un_riquadro_mancante_e_un_guasto(tmp_path):
    def scrivi(out, site):
        dati = _risultato_riquadri(out, {375: 1, 768: 1, 1440: 2})
        (out / "tile-1440-02.png").unlink()
        return json.dumps(dati)
    run, _ = _runner(scrivi)

    with pytest.raises(RenderError, match="tile-1440-02.png"):
        render_tiles(_workspace(tmp_path), tmp_path / "esito", max_tiles=20, runner=run)


def test_t8_un_sito_che_non_parte_e_un_esito(tmp_path):
    run, _ = _runner(lambda out, site: json.dumps({"started": False, "start_error": "porta 8080 non aperta"}))

    r = render_tiles(_workspace(tmp_path), tmp_path / "esito", max_tiles=20, runner=run)

    assert not r.started and r.start_error == "porta 8080 non aperta" and r.widths == {}


def test_t9_senza_start_sh_nessun_container(tmp_path):
    run, chiamate = _runner(lambda out, site: "{}")

    r = render_tiles(_workspace(tmp_path, start=None), tmp_path / "esito", max_tiles=20, runner=run)

    assert not r.started and chiamate == []


def test_t10_il_workspace_archiviato_non_cambia(tmp_path):
    def scrivi(out, site):
        (site / "data").mkdir()
        (site / "data" / "store.json").write_text("{}")
        return json.dumps(_risultato_riquadri(out, {375: 1, 768: 1, 1440: 1}))
    run, _ = _runner(scrivi)
    ws = _workspace(tmp_path)

    render_tiles(ws, tmp_path / "esito", max_tiles=20, runner=run)

    assert not (ws / "data").exists()


# ── Prove con Docker vero ──────────────────────────────────────────────────

_INTEGRAZIONE = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION") or shutil.which("docker") is None,
    reason="serve Docker con l'immagine orc-renderer:r1t: ORC_INTEGRATION=1")


@_INTEGRAZIONE
def test_i1_una_pagina_di_5000_px_si_vede_tutta_oltre_il_taglio_di_4000(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<style>body{margin:0}</style><div style='height:5000px;background:linear-gradient(red,blue)'></div>")

    r = render_tiles(ws, tmp_path / "esito", max_tiles=20)

    assert r.started
    for w in WIDTHS:
        assert r.widths[w].height == 5000 and not r.widths[w].truncated
        assert len(r.widths[w].tiles) == 6
