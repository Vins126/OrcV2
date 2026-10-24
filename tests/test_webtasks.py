"""I compiti di siti web si scaricano, si filtrano e si scelgono con il seme.

Nota di design (tesi):
    Qui non si scarica niente: un finto `download` consegna file costruiti dal
    test, con gli stessi campi dei file veri (WebGen-Bench: `id`, `instruction`,
    `application_type`, `ui_instruct`; ArtifactsBench: `index`, `question`,
    `class`, `checklist`, una riga JSON per compito). La prova sui file veri sta
    in fondo e si lancia di proposito con `ORC_INTEGRATION=1`.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from task_model import CampaignError
from webtasks import (
    ARTIFACTS,
    SOURCES,
    WEBGEN,
    Candidate,
    Verdict,
    WebTaskError,
    draw_order,
    fetch_webtasks,
    load_artifacts,
    load_selection,
    load_webgen,
    prefilter,
    select,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _webgen_riga(id_: str, tipo: str = "Company Brochure Sites") -> dict:
    return {"id": id_, "instruction": f"compito {id_}", "Category": {"primary_category": "x"},
            "application_type": tipo,
            "ui_instruct": [{"task": "apri", "expected_result": "si apre"}]}


def _artifacts_riga(index: int, classe: str = "Web Applications-Online Shopping") -> dict:
    return {"index": index, "question": f"domanda {index}", "class": classe,
            "difficulty": "easy", "checklist": [{"id": 0, "title": "t", "description": "d"}]}


def _jsonl(righe: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in righe)


def _candidati(n: int, source: str = WEBGEN) -> list[Candidate]:
    return [Candidate(id=str(i), source=source, label="x", text=f"t{i}") for i in range(1, n + 1)]


# ── Lettura ────────────────────────────────────────────────────────────────

def test_w1_webgen_si_legge_con_testo_tipo_e_casi_di_prova(tmp_path):
    file = tmp_path / "w.jsonl"
    file.write_text(_jsonl([_webgen_riga("000001"), _webgen_riga("000002", "CRM Systems")]))

    candidati = load_webgen(file)

    assert [c.id for c in candidati] == ["000001", "000002"]
    assert candidati[1].label == "CRM Systems"
    assert candidati[0].text == "compito 000001"
    assert candidati[0].checks == [{"task": "apri", "expected_result": "si apre"}]
    assert {c.source for c in candidati} == {WEBGEN}


def test_w2_artifacts_si_legge_riga_per_riga_con_id_testuale(tmp_path):
    file = tmp_path / "a.jsonl"
    file.write_text(_jsonl([_artifacts_riga(7), _artifacts_riga(12, "SVG Generation-SVG Images")]))

    candidati = load_artifacts(file)

    assert [c.id for c in candidati] == ["7", "12"]
    assert candidati[1].label == "SVG Generation-SVG Images"
    assert candidati[0].text == "domanda 7"
    assert candidati[0].checks[0]["title"] == "t"
    assert {c.source for c in candidati} == {ARTIFACTS}


def test_w3_una_riga_malformata_e_un_errore_con_il_numero_di_riga(tmp_path):
    file = tmp_path / "a.jsonl"
    file.write_text(_jsonl([_artifacts_riga(1)]) + "{non json\n")

    with pytest.raises(WebTaskError, match="riga 2"):
        load_artifacts(file)


def test_w4_un_campo_mancante_e_un_errore(tmp_path):
    file = tmp_path / "w.jsonl"
    riga = _webgen_riga("000001")
    del riga["instruction"]
    file.write_text(_jsonl([riga]))

    with pytest.raises(WebTaskError, match="instruction"):
        load_webgen(file)


# ── Pre-filtro ─────────────────────────────────────────────────────────────

def test_w5_il_prefiltro_toglie_giochi_e_famiglie_non_web():
    def c(source, label):
        return Candidate(id=label, source=source, label=label, text="")

    tenuti = [
        c(WEBGEN, "Company Brochure Sites"),
        c(ARTIFACTS, "Web Applications-Online Shopping"),
        c(ARTIFACTS, "Management Systems-File Management"),
        c(ARTIFACTS, "Utility Tools-Daily Office Tasks"),
        c(ARTIFACTS, "Data Science-Data Visualization Dashboards"),
    ]
    tolti = [
        c(WEBGEN, "Browser-Based Games"),
        c(ARTIFACTS, "Game Development-Puzzle"),
        c(ARTIFACTS, "Utility Tools-Web Scraping"),
        c(ARTIFACTS, "Data Science-Machine Learning"),
        c(ARTIFACTS, "SVG Generation-SVG Images"),
        c(ARTIFACTS, "Simulation & Modeling-Physics Simulation"),
        c(ARTIFACTS, "Multimedia Editing-Video Production"),
        c(ARTIFACTS, "Other-Web Development"),
    ]

    assert prefilter(tenuti + tolti) == tenuti


# ── Ordine estratto ────────────────────────────────────────────────────────

def test_w6_stesso_seme_stesso_ordine_qualunque_sia_l_ordine_di_partenza():
    candidati = _candidati(30)

    primo = draw_order(candidati, 20261021)
    rovesciato = draw_order(list(reversed(candidati)), 20261021)

    assert [c.id for c in primo] == [c.id for c in rovesciato]
    assert sorted(c.id for c in primo) == sorted(c.id for c in candidati)


def test_w7_l_ordine_e_numerico_non_alfabetico():
    # "10" prima di "9" in ordine alfabetico: il mescolamento deve partire da 1, 2, ..., 10.
    candidati = _candidati(10)
    atteso = [str(i) for i in range(1, 11)]
    import random
    random.Random(5).shuffle(atteso)

    assert [c.id for c in draw_order(candidati, 5)] == atteso


def test_w8_seme_diverso_ordine_diverso():
    candidati = _candidati(30)
    assert [c.id for c in draw_order(candidati, 1)] != [c.id for c in draw_order(candidati, 2)]


# ── Scelta lungo l'ordine ──────────────────────────────────────────────────

def test_w9_si_tengono_i_primi_validi_saltando_gli_scartati():
    ordine = _candidati(5)
    verdetti = [Verdict("1", False, reason="vago"), Verdict("2", True, kind="sito"),
                Verdict("3", True, kind="applicazione")]

    scelti = select(ordine, verdetti, 2)

    assert [(t.candidate.id, t.kind) for t in scelti] == [("2", "sito"), ("3", "applicazione")]


def test_w10_un_compito_raggiunto_senza_verdetto_e_un_errore():
    ordine = _candidati(5)
    verdetti = [Verdict("1", True, kind="sito"), Verdict("3", True, kind="sito")]

    with pytest.raises(WebTaskError, match="'2'"):
        select(ordine, verdetti, 2)


def test_w11_un_verdetto_fuori_turno_e_un_errore():
    # Il 5 viene dopo il punto in cui la scelta si ferma: giudicarlo vuol dire
    # aver letto fuori ordine.
    ordine = _candidati(5)
    verdetti = [Verdict("1", True, kind="sito"), Verdict("5", False, reason="non mi piace")]

    with pytest.raises(WebTaskError, match="'5'"):
        select(ordine, verdetti, 1)


def test_w12_un_verdetto_su_un_compito_che_non_esiste_e_un_errore():
    ordine = _candidati(3)
    verdetti = [Verdict("1", True, kind="sito"), Verdict("99", False, reason="x")]

    with pytest.raises(WebTaskError, match="'99'"):
        select(ordine, verdetti, 1)


def test_w13_compiti_finiti_prima_del_numero_e_un_errore():
    ordine = _candidati(2)
    verdetti = [Verdict("1", True, kind="sito"), Verdict("2", False, reason="x")]

    with pytest.raises(WebTaskError, match="2"):
        select(ordine, verdetti, 2)


# ── File dei verdetti ──────────────────────────────────────────────────────

def _dati(tmp_path: Path) -> Path:
    cartella = tmp_path / "dati"
    cartella.mkdir()
    (cartella / SOURCES[0].filename).write_text(
        _jsonl([_webgen_riga(f"{i:06d}") for i in range(1, 6)]))
    (cartella / SOURCES[1].filename).write_text(
        _jsonl([_artifacts_riga(i) for i in range(1, 6)]))
    return cartella


def _config(tmp_path: Path, testo: str) -> Path:
    file = tmp_path / "c.toml"
    file.write_text(testo)
    return file


def _verdetti_in_ordine(ids: list[str]) -> str:
    return ", ".join(f'{{ id = "{i}", keep = true, kind = "sito" }}' for i in ids)


def test_w14_il_file_dei_verdetti_produce_i_compiti_di_entrambe_le_fonti(tmp_path):
    dati = _dati(tmp_path)
    ordine_w = [c.id for c in draw_order(load_webgen(dati / SOURCES[0].filename), 7)]
    ordine_a = [c.id for c in draw_order(load_artifacts(dati / SOURCES[1].filename), 7)]
    config = _config(tmp_path, f"""
seed = 7
[webgen]
count = 2
verdicts = [{_verdetti_in_ordine(ordine_w[:2])}]
[artifactsbench]
count = 1
verdicts = [{_verdetti_in_ordine(ordine_a[:1])}]
""")

    scelti = load_selection(config, dati)

    assert [(t.candidate.source, t.candidate.id) for t in scelti] == [
        (WEBGEN, ordine_w[0]), (WEBGEN, ordine_w[1]), (ARTIFACTS, ordine_a[0])]


@pytest.mark.parametrize("verdetto, attesa", [
    ('{ id = "X", keep = true }', "kind"),
    ('{ id = "X", keep = true, kind = "gioco" }', "gioco"),
    ('{ id = "X", keep = false }', "reason"),
])
def test_w15_un_verdetto_incompleto_e_un_errore(tmp_path, verdetto, attesa):
    dati = _dati(tmp_path)
    primo = draw_order(load_webgen(dati / SOURCES[0].filename), 7)[0].id
    config = _config(tmp_path, f"""
seed = 7
[webgen]
count = 1
verdicts = [{verdetto.replace('"X"', f'"{primo}"')}]
[artifactsbench]
count = 0
verdicts = []
""")

    with pytest.raises(WebTaskError, match=attesa):
        load_selection(config, dati)


def test_w16_dati_non_scaricati_e_un_errore_che_dice_come_scaricarli(tmp_path):
    config = _config(tmp_path, "seed = 1\n[webgen]\ncount = 0\nverdicts = []\n"
                               "[artifactsbench]\ncount = 0\nverdicts = []\n")

    with pytest.raises(WebTaskError, match="fetch-webtasks"):
        load_selection(config, tmp_path / "manca")


# ── Scaricamento ───────────────────────────────────────────────────────────

def _download_finto(contenuti: dict[str, bytes]):
    chiamate: list[str] = []

    def scarica(url: str) -> bytes:
        chiamate.append(url)
        return contenuti[url]
    return scarica, chiamate


def test_w17_lo_scaricamento_verifica_l_hash_e_scrive_i_due_file(tmp_path, monkeypatch):
    contenuti = {s.url: f"dati {s.name}\n".encode() for s in SOURCES}
    import webtasks
    monkeypatch.setattr(webtasks, "SOURCES", tuple(
        webtasks.Source(s.name, s.url, s.filename, hashlib.sha256(contenuti[s.url]).hexdigest())
        for s in SOURCES))
    scarica, chiamate = _download_finto(contenuti)

    cartella = fetch_webtasks(tmp_path / "dati", download=scarica)

    assert sorted(chiamate) == sorted(s.url for s in SOURCES)
    for s in SOURCES:
        assert (cartella / s.filename).read_bytes() == contenuti[s.url]


def test_w18_un_hash_sbagliato_e_un_errore_e_non_lascia_nulla(tmp_path):
    scarica, _ = _download_finto({s.url: b"contenuto diverso" for s in SOURCES})

    with pytest.raises(WebTaskError, match="sha256"):
        fetch_webtasks(tmp_path / "dati", download=scarica)

    assert list(tmp_path.iterdir()) == []


def test_w19_una_cartella_esistente_non_si_sovrascrive(tmp_path):
    (tmp_path / "dati").mkdir()
    scarica, chiamate = _download_finto({})

    with pytest.raises(WebTaskError, match="esiste"):
        fetch_webtasks(tmp_path / "dati", download=scarica)

    assert chiamate == []


def test_w20_un_errore_di_rete_e_un_errore_del_progetto(tmp_path):
    def scarica(url: str) -> bytes:
        raise OSError("rete giu'")

    with pytest.raises(CampaignError, match="rete giu'"):
        fetch_webtasks(tmp_path / "dati", download=scarica)


# ── Prova reale ────────────────────────────────────────────────────────────

@pytest.mark.skipif(not os.environ.get("ORC_INTEGRATION"),
                    reason="scarica i file veri dalla rete: ORC_INTEGRATION=1")
def test_w21_i_file_veri_danno_i_cinque_compiti_del_protocollo(tmp_path):
    dati = fetch_webtasks(tmp_path / "dati")

    scelti = load_selection(PROJECT_ROOT / "campaigns" / "r1_compiti.toml", dati)

    assert [(t.candidate.id, t.kind) for t in scelti] == [
        ("000098", "applicazione"), ("000040", "sito"), ("000058", "applicazione"),
        ("842", "applicazione"), ("684", "applicazione")]


def test_w22_da_riga_di_comando_una_cartella_esistente_da_errore_e_codice_2(tmp_path):
    r = subprocess.run([sys.executable, "campaign.py", "fetch-webtasks", "--dest", str(tmp_path)],
                       cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60)

    assert r.returncode == 2, r.stderr[-400:]
    assert "esiste" in r.stderr and "Traceback" not in r.stderr
