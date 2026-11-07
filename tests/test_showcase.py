"""Vetrina dei siti per l'autore (task 7, P2-D1 scelta (c)): sito vivo e galleria.

Serve a guardare e mostrare i siti consegnati dai bracci; non entra nella
misura e nessun braccio la vede. Docker non serve: il comando si controlla
come lista di argomenti e l'esecuzione passa da un `runner` finto.
"""

import json
import subprocess
from pathlib import Path

import pytest

import showcase
from showcase import ShowcaseError, build_gallery, manifest_rows, serve_command, serve_site
from task_model import CampaignError


# ── Aiuti ──────────────────────────────────────────────────────────────────

def _png(percorso: Path) -> Path:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes(b"\x89PNG\r\n\x1a\nfinto")
    return percorso


def _riga(tmp_path: Path, braccio: str, task: str, *, costo: float, accettato: bool,
          funziona: float | None = 50.0, con_screenshot: bool = True) -> dict:
    """Una riga di manifesto come la scrive `_esegui_run` per un sito."""
    cartella = tmp_path / "out" / braccio / f"{task}-1"
    cartella.mkdir(parents=True, exist_ok=True)
    schermate = ({w: str(_png(cartella / "screenshot" / f"{w}.png")) for w in ("375", "768", "1440")}
                 if con_screenshot else {w: None for w in ("375", "768", "1440")})
    valutazione = cartella / "valutazione.json"
    valutazione.write_text(json.dumps({"cancello": {}, "riservato": {"screenshots": schermate},
                                       "gate": {"accepted": accettato, "reason": None}}))
    return {"task_id": task, "rep": 1, "run_id": "r", "model": "m", "workspace": str(tmp_path / "ws" / braccio),
            "status": "completed", "verified": True, "success": True, "total_cost": costo,
            "evaluation": {"path": str(valutazione), "started": True, "funziona": funziona},
            "gate": {"accepted": accettato, "reason": None if accettato else "errori JavaScript al caricamento"}}


def _manifesto(tmp_path: Path, nome: str, righe: list[dict]) -> Path:
    percorso = tmp_path / f"{nome}.jsonl"
    testo = json.dumps({"environment": {"image": "x"}}) + "\n"
    percorso.write_text(testo + "".join(json.dumps(r) + "\n" for r in righe))
    return percorso


class RunnerFinto:
    def __init__(self, solleva: BaseException | None = None):
        self.comandi: list[list[str]] = []
        self.solleva = solleva

    def __call__(self, comando, **_):
        self.comandi.append(list(comando))
        if self.solleva is not None and comando[:2] == ["docker", "run"]:
            raise self.solleva
        return subprocess.CompletedProcess(comando, 0, "", "")


# ── Manifesto ──────────────────────────────────────────────────────────────

def test_v1_le_righe_del_manifesto_per_compito_saltano_l_ambiente(tmp_path):
    manifesto = _manifesto(tmp_path, "b", [_riga(tmp_path, "B", "t1", costo=1.0, accettato=True),
                                           _riga(tmp_path, "B", "t2", costo=2.0, accettato=False)])

    righe = manifest_rows(manifesto)

    assert sorted(righe) == ["t1", "t2"]
    assert righe["t2"]["total_cost"] == 2.0


def test_v2_manifesto_mancante_o_compito_doppio_sono_errori_parlanti(tmp_path):
    assert issubclass(ShowcaseError, CampaignError)
    with pytest.raises(ShowcaseError, match="non trovato"):
        manifest_rows(tmp_path / "manca.jsonl")
    riga = _riga(tmp_path, "B", "t1", costo=1.0, accettato=True)
    with pytest.raises(ShowcaseError, match="t1"):
        manifest_rows(_manifesto(tmp_path, "doppio", [riga, riga]))


# ── Sito vivo ──────────────────────────────────────────────────────────────

def test_v3_il_comando_pubblica_la_porta_solo_su_localhost_senza_privilegi(tmp_path):
    comando = serve_command(tmp_path / "site", "orc-vetrina-x", host_port=8080)

    assert comando[:2] == ["docker", "run"]
    assert "--rm" in comando and "--read-only" in comando
    assert comando[comando.index("--user") + 1] == "1000:1000"
    assert comando[comando.index("--name") + 1] == "orc-vetrina-x"
    # Raggiungibile solo dal Mac dell'autore, non dalla rete locale.
    assert comando[comando.index("--publish") + 1] == f"127.0.0.1:8080:{showcase.PUBLIC_PORT}"
    assert f"{tmp_path / 'site'}:/workspace" in comando
    # Lo script che avvia start.sh e inoltra la porta entra in sola lettura.
    assert any(v.endswith(":ro") and "serve_site.py" in v for v in comando)


def test_v4_serve_lavora_su_una_copia_e_la_cancella(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "start.sh").write_text("echo ciao\n")
    runner = RunnerFinto()

    codice = serve_site(ws, host_port=9000, runner=runner)

    assert codice == 0
    run = [c for c in runner.comandi if c[:2] == ["docker", "run"]][0]
    montato = next(v for v in run if v.endswith(":/workspace"))
    copia = Path(montato.rsplit(":", 1)[0])
    assert copia != ws and not copia.exists()       # copia temporanea, rimossa alla fine
    assert (ws / "start.sh").read_text() == "echo ciao\n"   # l'originale resta intatto


def test_v5_senza_start_sh_e_un_errore_prima_di_docker(tmp_path):
    runner = RunnerFinto()
    with pytest.raises(ShowcaseError, match="start.sh"):
        serve_site(tmp_path, host_port=9000, runner=runner)
    assert runner.comandi == []


def test_v6_ctrl_c_toglie_il_container_per_nome(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "start.sh").write_text("true\n")
    runner = RunnerFinto(solleva=KeyboardInterrupt())

    codice = serve_site(ws, host_port=9000, runner=runner)

    nome = next(c for c in runner.comandi if c[:2] == ["docker", "run"])
    nome = nome[nome.index("--name") + 1]
    assert ["docker", "rm", "-f", nome] in [c[:4] for c in runner.comandi]
    assert codice == 130


# ── Galleria ───────────────────────────────────────────────────────────────

def _bracci(tmp_path: Path, *, d_accettato: bool) -> dict[str, Path]:
    return {
        "B": _manifesto(tmp_path, "b", [_riga(tmp_path, "B", "t1", costo=2.0, accettato=True)]),
        "D": _manifesto(tmp_path, "d", [_riga(tmp_path, "D", "t1", costo=0.05, accettato=d_accettato)]),
        "C": _manifesto(tmp_path, "c", [_riga(tmp_path, "C", "t1", costo=1.25, accettato=True,
                                              funziona=None, con_screenshot=False)]),
    }


def test_v7_la_galleria_e_una_cartella_portabile_con_le_schermate_copiate(tmp_path):
    out = tmp_path / "vetrina"

    indice = build_gallery(_bracci(tmp_path, d_accettato=True), out)

    assert indice == out / "index.html"
    html = indice.read_text()
    for braccio in ("B", "D", "C", "V"):
        assert f">{braccio}<" in html
    # Le immagini sono copiate dentro la cartella e citate con percorsi relativi.
    immagini = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.png"))
    assert immagini and all(f'src="{i}"' in html or f'href="{i}"' in html for i in immagini)
    assert str(tmp_path / "out") not in html
    # Costi e verdetti del cancello sono scritti per braccio.
    assert "$2.00" in html and "$0.05" in html and "$1.25" in html


def test_v8_v_e_d_se_d_passa_il_cancello_altrimenti_b_con_i_due_costi(tmp_path):
    passa = build_gallery(_bracci(tmp_path / "a", d_accettato=True), tmp_path / "g1").read_text()
    ripiega = build_gallery(_bracci(tmp_path / "b", d_accettato=False), tmp_path / "g2").read_text()

    assert "V = D" in passa and "$0.05" in passa
    # Cascata: D gira sempre, B solo se D e' rifiutato; il costo di V e' la somma.
    assert "V = B" in ripiega and "$2.05" in ripiega


def test_v9_un_sito_senza_schermate_resta_in_galleria_con_la_nota(tmp_path):
    html = build_gallery(_bracci(tmp_path, d_accettato=True), tmp_path / "g").read_text()

    assert "nessuno screenshot" in html


def test_v10_una_cartella_di_galleria_gia_esistente_e_un_errore(tmp_path):
    out = tmp_path / "g"
    out.mkdir()
    with pytest.raises(ShowcaseError, match="esiste"):
        build_gallery(_bracci(tmp_path, d_accettato=True), out)


def test_v11_un_braccio_ignoto_e_un_errore_prima_di_scrivere(tmp_path):
    bracci = {**_bracci(tmp_path, d_accettato=True), "Z": tmp_path / "z.jsonl"}
    with pytest.raises(ShowcaseError, match="Z"):
        build_gallery(bracci, tmp_path / "g")
    assert not (tmp_path / "g").exists()
