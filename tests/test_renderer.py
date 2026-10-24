"""Il sito consegnato si avvia e si guarda nel renderer, sempre allo stesso modo.

Nota di design (tesi):
    Qui Docker non si lancia: un finto `runner` fa la parte del container e
    scrive nella cartella dei risultati cio' che scriverebbe
    `docker/render_site.py`. Le prove con Docker vero e l'immagine costruita
    stanno in fondo e si lanciano con `ORC_INTEGRATION=1`.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from renderer import (
    PORT,
    RENDERER_IMAGE,
    WIDTHS,
    RenderError,
    docker_command,
    render_site,
)
from task_model import CampaignError


def _workspace(tmp_path: Path, start: str | None = "python3 -m http.server 8080\n") -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "index.html").write_text("<h1>ciao</h1>")
    if start is not None:
        (ws / "start.sh").write_text(start)
    return ws


def _valore(cmd: list[str], opzione: str) -> str:
    return cmd[cmd.index(opzione) + 1]


def _risultato_ok(out: Path) -> dict:
    widths = {}
    for w in WIDTHS:
        (out / f"shot-{w}.png").write_bytes(b"\x89PNG finto")
        widths[str(w)] = {"errors": [], "overflow": w == 375, "screenshot": f"shot-{w}.png",
                          "a11y": [{"id": "image-alt", "impact": "critical", "nodes": 2}] if w == 768 else []}
    return {"started": True, "start_error": None, "widths": widths,
            "versions": {"chromium": "1", "playwright": "1.64.0"}}


def _runner(scrivi=None, *, returncode=0, eccezione=None):
    """Finto `docker run`: trova la cartella dei risultati nel comando e ci scrive."""
    chiamate: list[list[str]] = []

    def run(cmd, **kwargs):
        chiamate.append(cmd)
        if eccezione is not None and cmd[:2] == ["docker", "run"]:
            raise eccezione
        if cmd[:2] == ["docker", "run"] and scrivi is not None:
            volumi = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--volume"]
            out = Path(next(v.split(":")[0] for v in volumi if v.endswith(":/out")))
            site = Path(next(v.split(":")[0] for v in volumi if v.endswith(":/workspace")))
            contenuto = scrivi(out, site)
            if contenuto is not None:
                (out / "result.json").write_text(contenuto)
        return subprocess.CompletedProcess(cmd, returncode, "", "")
    return run, chiamate


# ── Comando del container ──────────────────────────────────────────────────

def test_r1_il_container_e_senza_rete_non_privilegiato_e_con_limiti_propri(tmp_path):
    cmd = docker_command(tmp_path / "site", tmp_path / "out", "orc-renderer-x")

    assert cmd[:3] == ["docker", "run", "--rm"]
    assert _valore(cmd, "--network") == "none"
    assert _valore(cmd, "--user") == "1000:1000"
    assert _valore(cmd, "--memory") == "2g"
    assert _valore(cmd, "--shm-size") == "1g"
    assert _valore(cmd, "--pids-limit") == "1024"
    assert _valore(cmd, "--name") == "orc-renderer-x"
    assert "--init" in cmd
    assert f"{tmp_path / 'site'}:/workspace" in cmd
    assert f"{tmp_path / 'out'}:/out" in cmd
    assert RENDERER_IMAGE in cmd


def test_r2_il_comando_passa_porta_larghezze_e_tempo_di_avvio(tmp_path):
    cmd = docker_command(tmp_path / "s", tmp_path / "o", "n", start_timeout=7)
    coda = " ".join(cmd[cmd.index(RENDERER_IMAGE) + 1:])

    assert f"--port {PORT}" in coda
    assert "--widths " + ",".join(str(w) for w in WIDTHS) in coda
    assert "--start-timeout 7" in coda


# ── Esito ──────────────────────────────────────────────────────────────────

def test_r3_un_risultato_completo_diventa_render_result(tmp_path):
    run, _ = _runner(lambda out, site: json.dumps(_risultato_ok(out)))

    r = render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)

    assert r.started and r.start_error is None
    assert set(r.widths) == set(WIDTHS)
    assert r.widths[375].overflow and not r.widths[1440].overflow
    for w in WIDTHS:
        shot = r.widths[w].screenshot
        assert shot is not None and shot.is_file()
        assert shot.parent == tmp_path / "esito"
    assert r.versions["playwright"] == "1.64.0"


def test_r4_un_sito_che_non_parte_e_un_esito_non_un_guasto(tmp_path):
    run, _ = _runner(lambda out, site: json.dumps(
        {"started": False, "start_error": "porta 8080 non aperta entro 60 s",
         "widths": {}, "versions": {}}))

    r = render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)

    assert not r.started
    assert "8080" in (r.start_error or "")
    assert r.widths == {}


def test_r5_senza_start_sh_non_si_lancia_nessun_container(tmp_path):
    run, chiamate = _runner(lambda out, site: json.dumps(_risultato_ok(out)))

    r = render_site(_workspace(tmp_path, start=None), tmp_path / "esito", runner=run)

    assert not r.started and "start.sh" in (r.start_error or "")
    assert chiamate == []


@pytest.mark.parametrize("contenuto", [None, "{non json", json.dumps({"widths": {}})])
def test_r6_risultato_mancante_o_illeggibile_e_un_guasto(tmp_path, contenuto):
    run, _ = _runner(lambda out, site: contenuto)

    with pytest.raises(RenderError):
        render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)


def test_r7_tempo_scaduto_ferma_il_container_per_nome_ed_e_un_guasto(tmp_path):
    run, chiamate = _runner(eccezione=subprocess.TimeoutExpired(["docker"], 1))

    with pytest.raises(RenderError, match="tempo"):
        render_site(_workspace(tmp_path), tmp_path / "esito", runner=run, timeout=1)

    nome = _valore(chiamate[0], "--name")
    assert nome.startswith("orc-renderer-")
    # P19-D2 (24 ott): `rm -f` toglie anche un container mai partito, `kill` no.
    assert ["docker", "rm", "-f", nome] in [c[:4] for c in chiamate]


def test_r8_la_valutazione_lavora_su_una_copia_del_workspace(tmp_path):
    ws = _workspace(tmp_path)
    prima = sorted(p.name for p in ws.iterdir())

    def scrivi(out, site):
        assert site != ws and (site / "start.sh").is_file()
        (site / "dati.json").write_text("{}")      # il server salva qualcosa
        return json.dumps(_risultato_ok(out))
    run, _ = _runner(scrivi)

    render_site(ws, tmp_path / "esito", runner=run)

    assert sorted(p.name for p in ws.iterdir()) == prima


def test_r9_un_guasto_e_un_errore_del_progetto(tmp_path):
    run, _ = _runner(lambda out, site: None)
    with pytest.raises(CampaignError):
        render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)


def test_r10_la_copia_temporanea_non_resta_su_disco(tmp_path, monkeypatch):
    import tempfile
    radice = tmp_path / "tmp"
    radice.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(radice))
    run, _ = _runner(lambda out, site: json.dumps(_risultato_ok(out)))

    render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)

    assert list(radice.iterdir()) == []


def test_r11_le_violazioni_di_accessibilita_arrivano_per_larghezza(tmp_path):
    run, _ = _runner(lambda out, site: json.dumps(_risultato_ok(out)))

    r = render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)

    assert r.widths[768].a11y == [{"id": "image-alt", "impact": "critical", "nodes": 2}]
    assert r.widths[375].a11y == [] and r.widths[1440].a11y == []


def test_r12_senza_il_campo_a11y_e_un_guasto(tmp_path):
    def scrivi(out, site):
        dati = _risultato_ok(out)
        del dati["widths"]["768"]["a11y"]
        return json.dumps(dati)
    run, _ = _runner(scrivi)

    with pytest.raises(RenderError, match="768"):
        render_site(_workspace(tmp_path), tmp_path / "esito", runner=run)


# ── Prove con Docker vero ──────────────────────────────────────────────────

_INTEGRAZIONE = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION") or shutil.which("docker") is None,
    reason="serve Docker con l'immagine orc-renderer:r1: ORC_INTEGRATION=1")


@_INTEGRAZIONE
def test_i1_un_sito_statico_da_due_volte_lo_stesso_risultato(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<h1>Ciao</h1><p>Pagina di prova.</p>")

    a = render_site(ws, tmp_path / "a")
    b = render_site(ws, tmp_path / "b")

    assert a.started and b.started
    for w in WIDTHS:
        assert a.widths[w].errors == b.widths[w].errors == []
        assert not a.widths[w].overflow and not b.widths[w].overflow
        shot = a.widths[w].screenshot
        assert shot is not None and shot.stat().st_size > 0


@_INTEGRAZIONE
def test_i2_errore_javascript_e_sbordo_a_375_si_vedono(tmp_path):
    ws = _workspace(tmp_path)
    (ws / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<div style='width:600px'>largo</div><script>nonEsiste()</script>")

    r = render_site(ws, tmp_path / "e")

    assert r.started
    assert r.widths[375].overflow and not r.widths[1440].overflow
    assert all(r.widths[w].errors for w in WIDTHS)


@_INTEGRAZIONE
def test_i3_un_server_node_si_avvia(tmp_path):
    ws = _workspace(tmp_path, start="node server.js\n")
    (ws / "server.js").write_text(
        "require('http').createServer((q,s)=>{s.setHeader('content-type','text/html');"
        "s.end('<!doctype html><meta charset=utf-8><h1>node</h1>')}).listen(8080)")

    assert render_site(ws, tmp_path / "n").started


@_INTEGRAZIONE
def test_i4_un_sito_che_non_apre_la_porta_non_parte_in_tempo(tmp_path):
    ws = _workspace(tmp_path, start="sleep 600\n")

    r = render_site(ws, tmp_path / "s", start_timeout=5)

    assert not r.started and r.widths == {}


@_INTEGRAZIONE
def test_i5_axe_trova_immagine_senza_alt_e_contrasto_scarso_solo_dove_ci_sono(tmp_path):
    pulito = _workspace(tmp_path / "p")
    (pulito / "index.html").write_text(
        "<!doctype html><html lang=it><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<title>Prova</title><main><h1>Ciao</h1><p>Testo leggibile.</p></main></html>")
    sporco = _workspace(tmp_path / "s")
    (sporco / "index.html").write_text(
        "<!doctype html><html lang=it><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<title>Prova</title><main><h1>Ciao</h1><img src='data:image/gif;base64,R0lGODlhAQABAAAAACw='>"
        "<p style='color:#ddd;background:#fff'>poco contrasto</p></main></html>")

    a = render_site(pulito, tmp_path / "a")
    b = render_site(sporco, tmp_path / "b")

    assert all(a.widths[w].a11y == [] for w in WIDTHS)
    for w in WIDTHS:
        regole = {v["id"] for v in b.widths[w].a11y}
        assert {"image-alt", "color-contrast"} <= regole
        assert all(v["impact"] in ("critical", "serious") for v in b.widths[w].a11y)


# ── Vetrina (dati d'esempio per gli screenshot, PROTOCOLLO §6) ─────────────

def test_r13_con_uno_script_si_montano_script_e_codice_in_sola_lettura(tmp_path):
    script = tmp_path / "s" / "684.py"
    cmd = docker_command(tmp_path / "site", tmp_path / "out", "n", script=script, code=tmp_path / "py")
    volumi = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--volume"]

    assert f"{script.parent}:/eval:ro" in volumi and f"{tmp_path / 'py'}:/opt/orc/py:ro" in volumi
    assert "PYTHONPATH=/opt/orc/py" in cmd
    assert "--script /eval/684.py" in " ".join(cmd)


def test_r14_senza_script_niente_vetrina_e_niente_volumi_in_piu(tmp_path):
    cmd = docker_command(tmp_path / "site", tmp_path / "out", "n")
    assert "--script" not in cmd and not any(":/eval" in x for x in cmd)


def test_r15_l_esito_della_vetrina_arriva_nel_risultato(tmp_path):
    def scrivi(out, site):
        dati = _risultato_ok(out)
        dati["vetrina"] = "ok"
        return json.dumps(dati)
    run, chiamate = _runner(scrivi)

    r = render_site(_workspace(tmp_path), tmp_path / "esito", runner=run, script=tmp_path / "s.py")

    assert r.vetrina == "ok"
    assert "--script" in chiamate[0]


@_INTEGRAZIONE
def test_i9_la_vetrina_prepara_i_dati_prima_degli_screenshot(tmp_path):
    fixtures = Path(__file__).resolve().parent / "fixtures" / "valutazione"
    ws = tmp_path / "ws"
    shutil.copytree(fixtures / "sito_items", ws)

    con = render_site(ws, tmp_path / "con", script=fixtures / "script_items.py", start_timeout=20)
    senza = render_site(ws, tmp_path / "senza", start_timeout=20)

    assert con.vetrina == "ok" and senza.vetrina is None
    a, b = con.widths[1440].screenshot, senza.widths[1440].screenshot
    assert a is not None and b is not None and a.read_bytes() != b.read_bytes()
    assert not (ws / "data").exists()
