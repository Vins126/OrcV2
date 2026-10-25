"""Le coppie di calibrazione si scelgono, si renderizzano e si votano alla cieca (R1.8).

Nota di design (tesi):
    Qui non si scarica niente e Docker non si lancia: un finto `download`
    consegna file costruiti dal test (stessi campi delle risposte pubblicate di
    ArtifactsBench: `question`, `model_infer_result`, `gemini_mllm_score`), e un
    finto `render` fa la parte del renderer scrivendo gli screenshot. I nomi dei
    modelli nei test (`alfa`, `beta`, ...) non compaiono in nessun testo di
    compito, cosi' il controllo di cecita' del pacchetto non da' falsi allarmi.
    La prova sui dati veri sta in fondo e si lancia con `ORC_INTEGRATION=1`.
"""

import dataclasses
import hashlib
import json
import os
import random
import re
import statistics
from collections import Counter
from pathlib import Path

import pytest

from calibration import (
    Pair,
    RenderSummary,
    Response,
    Vote,
    build_vote_package,
    calibration_task_ids,
    extract_html,
    fetch_responses,
    final_pairs,
    is_valid_page,
    load_pairs,
    load_responses,
    load_votes,
    names_a_model,
    render_pairs,
    save_pairs,
    select_pairs,
    usable_responses,
    uses_network,
)
from renderer import RenderError, RenderResult, WidthResult
from webtasks import Source, WebTaskError

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PAGINA = "<!DOCTYPE html>\n<html><body><h1>ciao</h1></body></html>"
START_SH = "exec python3 -m http.server 8080 --bind 0.0.0.0\n"


def _blocco(corpo: str, lingua: str = "html") -> str:
    return f"Ecco la pagina:\n```{lingua}\n{corpo}\n```\n"


def _risposta(task: str, model: str, score: float | None, html: str = PAGINA) -> Response:
    return Response(task_id=task, model=model, text=_blocco(html), score=score)


def _source(name: str, contenuto: bytes) -> Source:
    return Source(name=name, url=f"https://esempio.invalid/{name}.jsonl",
                  filename=f"gemini_2.5_pro_judge_{name}.jsonl",
                  sha256=hashlib.sha256(contenuto).hexdigest())


def _jsonl(righe: list[dict]) -> bytes:
    return "".join(json.dumps(r) + "\n" for r in righe).encode("utf-8")


# ── k1, k2: estrazione dell'HTML ───────────────────────────────────────────

def test_k1_si_estrae_il_corpo_di_un_blocco_html_o_un_documento_senza_blocco():
    assert extract_html(_blocco(PAGINA)) == PAGINA + "\n"
    senza_lingua = "Testo\n```\n<!DOCTYPE html>\n<html><body>x</body></html>\n```\n"
    assert extract_html(senza_lingua) == "<!DOCTYPE html>\n<html><body>x</body></html>\n"
    documento = "<html><body>solo documento</body></html>"
    assert extract_html(documento) == documento


def test_k2_blocchi_multipli_misti_non_html_o_html_in_prosa_non_si_estraggono():
    due_html = _blocco(PAGINA) + _blocco(PAGINA)
    html_e_bash = _blocco(PAGINA) + _blocco("python3 -m http.server", "bash")
    solo_python = _blocco("print('ciao')", "python")
    prosa = "Ecco il codice: <html><body>x</body></html> e basta."

    for testo in (due_html, html_e_bash, solo_python, prosa):
        assert extract_html(testo) is None, testo


# ── k3, k4: pagina valida e rete ───────────────────────────────────────────

def test_k3_una_pagina_e_valida_se_completa_e_senza_file_locali():
    assert not is_valid_page("<div>frammento</div>")
    assert not is_valid_page('<html><body><script src="app.js"></script></body></html>')
    assert not is_valid_page('<html><head><link rel="stylesheet" href="style.css"></head></html>')
    assert is_valid_page('<html><body><script src="https://cdn.esempio.com/x.js"></script></body></html>')
    assert is_valid_page('<html><body><script src="data:text/javascript,1"></script></body></html>')
    assert is_valid_page('<html><head><link rel="stylesheet" href="#"></head></html>')
    assert is_valid_page("<!doctype html><p>x</p>")


@pytest.mark.parametrize("frammento", [
    '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
    '<link rel="stylesheet" href="https://esempio.com/s.css">',
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">',
    "<style>@import url(//esempio.com/a.css);</style>",
    '<img src="https://esempio.com/a.png">',
    "<style>body { background: url(https://esempio.com/b.jpg); }</style>",
    '<script>fetch("https://api.esempio.com/dati")</script>',
    "<script>const s = new WebSocket('ws://x');</script>",
])
def test_k4_ogni_categoria_di_rete_rende_la_pagina_dipendente_dalla_rete(frammento):
    assert uses_network(f"<html><head>{frammento}</head><body></body></html>")


def test_k4b_pagina_autosufficiente_o_icona_remota_non_usano_la_rete():
    assert not uses_network(PAGINA)
    assert not uses_network('<html><head><link rel="icon" href="https://esempio.com/f.ico"></head></html>')


# ── k14: pagine che nominano un modello ────────────────────────────────────

@pytest.mark.parametrize("html", [
    "<html><body><footer>Built with Claude</footer></body></html>",
    "<html><body>Powered by GPT-4o</body></html>",
    "<html><head><title>Gemini dashboard</title></head></html>",
    "<html><body><script>// generato da DeepSeek\n</script></body></html>",
    "<html><body><!-- qwen --></body></html>",
    "<html><body>Google AI Studio</body></html>",
])
def test_k14_una_pagina_che_nomina_un_modello_si_riconosce(html):
    assert names_a_model(html)


@pytest.mark.parametrize("html", [
    "<html><body>modello gptq quantizzato</body></html>",
    "<html><body>Gustav Klimt</body></html>",
    "<html><body>katana</body></html>",
    PAGINA,
])
def test_k14b_un_nome_non_a_parola_intera_non_conta(html):
    assert not names_a_model(html)


# ── k5: lettura e collegamento ─────────────────────────────────────────────

def _compiti(tmp_path: Path, n: int = 3) -> Path:
    file = tmp_path / "artifacts_bench.jsonl"
    file.write_bytes(_jsonl([{"index": i, "question": f"domanda {i}", "class": "Web Applications-x",
                              "checklist": []} for i in range(1, n + 1)]))
    return file


def _file_risposte(tmp_path: Path, per_modello: dict[str, list[dict]]) -> tuple[Path, tuple[Source, ...]]:
    cartella = tmp_path / "risposte"
    cartella.mkdir(exist_ok=True)
    fonti = []
    for nome, righe in per_modello.items():
        contenuto = _jsonl(righe)
        fonte = _source(nome, contenuto)
        (cartella / fonte.filename).write_bytes(contenuto)
        fonti.append(fonte)
    return cartella, tuple(fonti)


def _riga(question: str, score: object = "50", testo: str = PAGINA) -> dict:
    return {"question": question, "model_infer_result": testo, "gemini_mllm_score": score,
            "class": "x", "checklist": [], "gemini_reason": "r"}


def test_k5_si_collega_per_testo_identico_e_si_contano_le_non_collegate(tmp_path):
    compiti = _compiti(tmp_path)
    dati, fonti = _file_risposte(tmp_path, {
        "alfa": [_riga("domanda 1", "71"), _riga("domanda 2", None), _riga("domanda 9")],
        "beta": [_riga("domanda 1", " 64.5 "), _riga("domanda  1x", "10"), _riga("domanda 3", "n/a")],
    })

    risposte, non_collegate = load_responses(dati, compiti, sources=fonti)

    assert non_collegate == 2
    per_chiave = {(r.task_id, r.model): r for r in risposte}
    assert set(per_chiave) == {("1", "alfa"), ("2", "alfa"), ("1", "beta"), ("3", "beta")}
    assert per_chiave[("1", "alfa")].score == 71.0
    assert per_chiave[("1", "beta")].score == 64.5
    assert per_chiave[("2", "alfa")].score is None
    assert per_chiave[("3", "beta")].score is None
    assert per_chiave[("1", "alfa")].text == PAGINA


def test_k5b_una_coppia_compito_modello_doppia_e_un_errore(tmp_path):
    compiti = _compiti(tmp_path)
    dati, fonti = _file_risposte(tmp_path, {"alfa": [_riga("domanda 1"), _riga("domanda 1")]})

    with pytest.raises(WebTaskError, match="alfa"):
        load_responses(dati, compiti, sources=fonti)


def test_k5c_uno_sha256_diverso_e_un_errore_prima_di_leggere(tmp_path):
    compiti = _compiti(tmp_path)
    dati, fonti = _file_risposte(tmp_path, {"alfa": [_riga("domanda 1")]})
    (dati / fonti[0].filename).write_bytes(_jsonl([_riga("domanda 2")]))

    with pytest.raises(WebTaskError, match="sha256"):
        load_responses(dati, compiti, sources=fonti)


def test_k5d_un_file_mancante_e_un_errore(tmp_path):
    compiti = _compiti(tmp_path)
    dati, fonti = _file_risposte(tmp_path, {"alfa": [_riga("domanda 1")]})
    (dati / fonti[0].filename).unlink()

    with pytest.raises(WebTaskError):
        load_responses(dati, compiti, sources=fonti)


# ── calibration_task_ids ───────────────────────────────────────────────────

def test_k5e_i_compiti_di_calibrazione_partono_dalla_posizione_300(tmp_path):
    ordine = tmp_path / "ordine.json"
    ordine.write_text(json.dumps({"seed": 1, "webgen": ["w"],
                                  "artifactsbench": [str(i) for i in range(1000, 1400)]}))

    ids = calibration_task_ids(ordine)

    assert ids[0] == "1299"
    assert len(ids) == 101
    assert "1298" not in ids


# ── k6, k7: scelta delle coppie ────────────────────────────────────────────

RETE = '<html><head><script src="https://cdn.esempio.com/x.js"></script></head><body></body></html>'
FIRMATA = "<html><body>Built with Claude</body></html>"


def _scenario() -> tuple[list[Response], list[str]]:
    r = [
        _risposta("1", "alfa", 50), _risposta("1", "beta", 55),            # coppia buona
        _risposta("2", "alfa", 50), _risposta("2", "beta", 50),            # pareggio
        _risposta("3", "alfa", 50), _risposta("3", "beta", 65),            # diff 15
        _risposta("4", "alfa", 25), _risposta("4", "beta", 30),            # punteggio basso
        _risposta("5", "alfa", 50), _risposta("5", "beta", 52, RETE),      # rete
        _risposta("6", "alfa", 50), _risposta("6", "beta", 52),            # fuori dalla coda
        _risposta("7", "alfa", 50), _risposta("7", "beta", 52), _risposta("7", "gamma", 54),
        _risposta("8", "alfa", 50), _risposta("8", "beta", 52, FIRMATA),   # pagina firmata
        _risposta("9", "alfa", 50), _risposta("9", "beta", None),          # senza punteggio
        Response(task_id="10", model="alfa", text="nessun codice", score=50),
        _risposta("10", "beta", 52),
    ]
    return r, ["1", "2", "3", "4", "5", "7", "8", "9", "10"]


def test_k6_la_regola_esclude_pareggi_distanze_punteggi_bassi_rete_coda_e_firme():
    risposte, coda = _scenario()

    coppie = select_pairs(risposte, coda, seed=7, iterations=5)

    assert {c.task_id for c in coppie} == {"1", "7"}
    assert len(coppie) == 2                                    # una coppia per compito
    for c in coppie:
        assert c.model_a < c.model_b
        assert 0 < abs(c.score_a - c.score_b) <= 10
        assert min(c.score_a, c.score_b) >= 30
    assert [c.pair_id for c in coppie] == ["c001", "c002"]
    uno = next(c for c in coppie if c.task_id == "1")
    assert (uno.model_a, uno.model_b, uno.score_a, uno.score_b) == ("alfa", "beta", 50.0, 55.0)


def test_k6a_senza_filtro_dei_nomi_la_pagina_firmata_entra():
    risposte, coda = _scenario()

    coppie = select_pairs(risposte, coda, seed=7, iterations=5, exclude_named=False)

    assert {c.task_id for c in coppie} == {"1", "7", "8"}


def test_k6b_tetto_per_modello_e_riserva_che_continua_i_conteggi():
    risposte = [x for t in range(1, 5) for x in (_risposta(str(t), "x", 50), _risposta(str(t), "y", 55))]

    coppie = select_pairs(risposte, ["1", "2", "3", "4"], cap_per_model=2, reserve_cap=3,
                          seed=1, iterations=3)

    # 2 principali (tetto 2), poi la riserva continua da 2 e arriva al tetto 3: una sola in piu'.
    assert len(coppie) == 3
    assert len({c.task_id for c in coppie}) == 3
    conti = Counter(m for c in coppie for m in (c.model_a, c.model_b))
    assert conti == {"x": 3, "y": 3}


def test_k6c_i_conteggi_degli_scarti_seguono_la_cascata():
    risposte, coda = _scenario()

    usabili, scarti = usable_responses(risposte, coda)

    assert scarti == {"fuori_coda": 2, "non_estraibile": 1, "non_valida": 0, "senza_punteggio": 1,
                      "rete": 1, "nome_modello": 1}
    assert len(usabili) == len(risposte) - 6
    assert all(r.task_id != "6" for r in usabili)


def test_k7_la_scelta_e_deterministica_e_non_dipende_dall_ordine_in_ingresso():
    gen = random.Random(3)
    modelli = ["alfa", "beta", "gamma", "delta", "epsilon"]
    risposte = [_risposta(str(t), m, float(gen.randint(30, 60))) for t in range(1, 40) for m in modelli]
    coda = [str(t) for t in range(1, 40)]

    prima = select_pairs(risposte, coda, cap_per_model=8, reserve_cap=10, seed=11, iterations=10)
    seconda = select_pairs(risposte, coda, cap_per_model=8, reserve_cap=10, seed=11, iterations=10)
    mescolate = risposte[:]
    random.Random(99).shuffle(mescolate)
    terza = select_pairs(mescolate, list(reversed(coda)), cap_per_model=8, reserve_cap=10,
                         seed=11, iterations=10)

    assert prima == seconda == terza
    assert len(prima) > 0


# ── save_pairs / load_pairs ────────────────────────────────────────────────

def _coppie(n: int) -> list[Pair]:
    return [Pair(pair_id=f"c{i:03d}", task_id=str(100 + i), model_a="alfa", model_b="beta",
                 score_a=50.0, score_b=55.0) for i in range(1, n + 1)]


def test_k6d_le_coppie_si_salvano_e_si_rileggono_divise_in_principali_e_riserva(tmp_path):
    file = tmp_path / "r1_coppie.json"

    save_pairs(file, _coppie(5), params={"seed": 20261024, "max_diff": 10.0}, main_count=3)
    dati = json.loads(file.read_text())
    principali, riserva = load_pairs(file)

    assert [c.pair_id for c in principali] == ["c001", "c002", "c003"]
    assert [c.pair_id for c in riserva] == ["c004", "c005"]
    assert dati["seed"] == 20261024
    assert dati["commit"] == "88c968b87e150e63de7660937e6dcfb8e7d643cf"
    assert dati["params"]["max_diff"] == 10.0
    assert "created" in dati


# ── k8: scaricamento ───────────────────────────────────────────────────────

def _a_pezzi(contenuti: dict[str, bytes], chiamate: list[str]):
    def scarica(url: str):
        chiamate.append(url)
        dati = contenuti[url]
        for i in range(0, len(dati), 7):
            yield dati[i:i + 7]
    return scarica


def test_k8_si_scarica_a_pezzi_e_si_verifica_lo_sha256(tmp_path):
    contenuti = {"alfa": b"riga uno\nriga due\n" * 5, "beta": b"altro contenuto\n"}
    fonti = tuple(_source(n, c) for n, c in contenuti.items())
    chiamate: list[str] = []
    per_url = {f.url: contenuti[f.name] for f in fonti}

    dest = fetch_responses(tmp_path / "risposte", download=_a_pezzi(per_url, chiamate), sources=fonti)

    assert dest == tmp_path / "risposte"
    for f in fonti:
        assert (dest / f.filename).read_bytes() == contenuti[f.name]
    assert sorted(chiamate) == sorted(per_url)


def test_k8b_uno_sha256_sbagliato_e_un_errore_e_non_lascia_cartelle(tmp_path):
    fonte = _source("alfa", b"atteso")
    dest = tmp_path / "dati" / "risposte"

    with pytest.raises(WebTaskError, match="sha256"):
        fetch_responses(dest, download=_a_pezzi({fonte.url: b"diverso"}, []), sources=(fonte,))

    assert not dest.exists()
    assert not dest.parent.exists() or list(dest.parent.iterdir()) == []


def test_k8c_una_cartella_completa_non_si_riscarica(tmp_path):
    fonte = _source("alfa", b"contenuto")
    dest = tmp_path / "risposte"
    dest.mkdir()
    (dest / fonte.filename).write_bytes(b"contenuto")

    def mai(url: str):
        raise AssertionError("non doveva scaricare")

    assert fetch_responses(dest, download=mai, sources=(fonte,)) == dest


def test_k8d_una_cartella_incompleta_e_un_errore_e_non_si_tocca(tmp_path):
    fonti = (_source("alfa", b"a"), _source("beta", b"b"))
    dest = tmp_path / "risposte"
    dest.mkdir()
    (dest / fonti[0].filename).write_bytes(b"a")

    with pytest.raises(WebTaskError):
        fetch_responses(dest, download=_a_pezzi({f.url: b"x" for f in fonti}, []), sources=fonti)

    assert sorted(p.name for p in dest.iterdir()) == [fonti[0].filename]


def test_k8e_un_errore_di_rete_diventa_web_task_error(tmp_path):
    fonte = _source("alfa", b"a")

    def rotto(url: str):
        raise OSError("rete giu'")

    with pytest.raises(WebTaskError):
        fetch_responses(tmp_path / "r", download=rotto, sources=(fonte,))
    assert not (tmp_path / "r").exists()


# ── k9: rendering ──────────────────────────────────────────────────────────

class FintoRender:
    """Fa la parte di `renderer.render_site`: scrive tre screenshot e annota le chiamate."""

    def __init__(self, guasti: dict[str, int] | None = None, non_partono: set[str] | None = None):
        self.chiamate: list[Path] = []
        self.guasti = dict(guasti or {})
        self.non_partono = non_partono or set()

    def __call__(self, site: Path, out_dir: Path) -> RenderResult:
        self.chiamate.append(site)
        pagina = site.parent.name
        if self.guasti.get(pagina, 0) > 0:
            self.guasti[pagina] -= 1
            raise RenderError("tempo scaduto")
        if pagina in self.non_partono:
            return RenderResult(started=False, start_error="porta mai aperta")
        out_dir.mkdir(parents=True, exist_ok=True)
        larghezze = {}
        for w in (375, 768, 1440):
            shot = out_dir / f"shot-{w}.png"
            shot.write_bytes(f"png {pagina} {w}".encode())
            larghezze[w] = WidthResult(width=w, errors=[], overflow=False, screenshot=shot)
        return RenderResult(started=True, widths=larghezze)


def _coppie_e_risposte(n: int) -> tuple[list[Pair], list[Response]]:
    coppie, risposte = [], []
    for i in range(1, n + 1):
        t = str(1000 + i)
        coppie.append(Pair(pair_id=f"c{i:03d}", task_id=t, model_a="alfa", model_b="beta",
                           score_a=50.0, score_b=55.0))
        risposte += [_risposta(t, "alfa", 50, PAGINA.replace("ciao", f"alfa {t}")),
                     _risposta(t, "beta", 55, PAGINA.replace("ciao", f"beta {t}"))]
    return coppie, risposte


def test_k9_ogni_pagina_si_renderizza_una_volta_con_index_e_start_giusti(tmp_path):
    coppie, risposte = _coppie_e_risposte(2)
    # una terza coppia riusa la pagina 1001-alfa
    risposte.append(_risposta("1001", "gamma", 52))
    coppie.append(Pair(pair_id="c003", task_id="1001", model_a="alfa", model_b="gamma",
                       score_a=50.0, score_b=52.0))
    render = FintoRender()
    out = tmp_path / "render"

    sommario = render_pairs(coppie, risposte, out, render=render, workers=2)

    assert isinstance(sommario, RenderSummary)
    assert sommario.rendered == 5 and sommario.skipped == 0
    assert sorted(s.parent.name for s in render.chiamate) == [
        "1001-alfa", "1001-beta", "1001-gamma", "1002-alfa", "1002-beta"]
    sito = out / "1001-alfa" / "site"
    assert (sito / "index.html").read_text() == PAGINA.replace("ciao", "alfa 1001") + "\n"
    assert (sito / "start.sh").read_text() == START_SH
    esito = json.loads((out / "1001-alfa" / "esito.json").read_text())
    assert esito["started"] is True and esito["failed"] is False
    assert esito["widths"]["1440"]["screenshot"] == "shots/shot-1440.png"
    assert (out / "1001-alfa" / esito["widths"]["375"]["screenshot"]).is_file()


def test_k9b_la_ripresa_salta_le_pagine_con_esito(tmp_path):
    coppie, risposte = _coppie_e_risposte(2)
    out = tmp_path / "render"
    render_pairs(coppie, risposte, out, render=FintoRender(), workers=1)
    secondo = FintoRender()

    sommario = render_pairs(coppie, risposte, out, render=secondo, workers=1)

    assert secondo.chiamate == []
    assert sommario.skipped == 4 and sommario.rendered == 0


def test_k9c_un_render_error_si_riprova_una_volta(tmp_path):
    coppie, risposte = _coppie_e_risposte(1)
    render = FintoRender(guasti={"1001-alfa": 1})

    sommario = render_pairs(coppie, risposte, tmp_path / "r", render=render, workers=1)

    assert [s.parent.name for s in render.chiamate].count("1001-alfa") == 2
    assert sommario.failed == []
    assert json.loads((tmp_path / "r" / "1001-alfa" / "esito.json").read_text())["started"] is True


def test_k9d_due_render_error_lasciano_la_pagina_guasta_e_la_ripresa_la_riprova(tmp_path):
    coppie, risposte = _coppie_e_risposte(1)
    out = tmp_path / "r"

    sommario = render_pairs(coppie, risposte, out, render=FintoRender(guasti={"1001-alfa": 2}), workers=1)

    assert sommario.failed == ["1001-alfa"]
    esito = json.loads((out / "1001-alfa" / "esito.json").read_text())
    assert esito["failed"] is True and "tempo scaduto" in esito["error"]

    secondo = FintoRender()
    sommario = render_pairs(coppie, risposte, out, render=secondo, workers=1)
    assert [s.parent.name for s in secondo.chiamate] == ["1001-alfa"]
    assert sommario.failed == []


def test_k9e_una_pagina_che_non_parte_e_un_esito_non_un_guasto(tmp_path):
    coppie, risposte = _coppie_e_risposte(1)

    sommario = render_pairs(coppie, risposte, tmp_path / "r",
                            render=FintoRender(non_partono={"1001-beta"}), workers=1)

    assert sommario.not_started == ["1001-beta"]
    assert sommario.failed == []
    esito = json.loads((tmp_path / "r" / "1001-beta" / "esito.json").read_text())
    assert esito["started"] is False and esito["start_error"] == "porta mai aperta"


# ── k10: coppie finali ─────────────────────────────────────────────────────

def test_k10_una_pagina_non_partita_fa_entrare_la_prima_della_riserva(tmp_path):
    coppie, risposte = _coppie_e_risposte(5)
    file = tmp_path / "coppie.json"
    save_pairs(file, coppie, params={"seed": 1}, main_count=3)
    out = tmp_path / "r"
    render_pairs(coppie, risposte, out, render=FintoRender(non_partono={"1002-beta"}), workers=1)

    finali, note = final_pairs(file, out, count=3)

    assert [c.pair_id for c in finali] == ["c001", "c003", "c004"]
    assert len(note) == 1 and "c002" in note[0] and "1002-beta" in note[0]


def test_k10b_una_riserva_rotta_si_salta_e_se_non_basta_e_un_errore(tmp_path):
    coppie, risposte = _coppie_e_risposte(4)
    file = tmp_path / "coppie.json"
    save_pairs(file, coppie, params={"seed": 1}, main_count=2)
    out = tmp_path / "r"
    render_pairs(coppie, risposte, out,
                 render=FintoRender(non_partono={"1001-alfa", "1003-alfa"}), workers=1)

    finali, _ = final_pairs(file, out, count=2)
    assert [c.pair_id for c in finali] == ["c002", "c004"]

    with pytest.raises(WebTaskError):
        final_pairs(file, out, count=3)


def test_k10c_una_pagina_non_renderizzata_e_un_errore(tmp_path):
    coppie, _ = _coppie_e_risposte(2)
    file = tmp_path / "coppie.json"
    save_pairs(file, coppie, params={"seed": 1}, main_count=2)

    with pytest.raises(WebTaskError):
        final_pairs(file, tmp_path / "vuota", count=2)


# ── k11, k12: pacchetto di voto ────────────────────────────────────────────

MODELLI = ["alfa", "beta", "gamma", "delta"]


@pytest.fixture
def pacchetto(tmp_path):
    """150 coppie renderizzate con il finto renderer e il pacchetto costruito sopra."""
    coppie, risposte = [], []
    for i in range(1, 151):
        t = str(2000 + i)
        a, b = sorted(random.Random(i).sample(MODELLI, 2))
        coppie.append(Pair(pair_id=f"c{i:03d}", task_id=t, model_a=a, model_b=b, score_a=50.0, score_b=55.0))
        risposte += [_risposta(t, a, 50), _risposta(t, b, 55)]
    out = tmp_path / "render"
    render_pairs(coppie, risposte, out, render=FintoRender(), workers=4)
    testi = {c.task_id: f"Build a page number {c.task_id}" for c in coppie}
    dest = tmp_path / "pacchetto"
    chiave = tmp_path / "chiave.json"
    indice = build_vote_package(coppie, testi, out, dest, chiave, seed=5)
    return {"coppie": coppie, "dest": dest, "chiave": chiave, "indice": indice}


def _voci(chiave: Path) -> list[dict]:
    return json.loads(chiave.read_text())["items"]


def test_k11_155_voci_con_5_ripetute_a_lati_invertiti_e_distanti(pacchetto):
    voci = _voci(pacchetto["chiave"])
    assert pacchetto["indice"] == pacchetto["dest"] / "index.html"
    assert len(voci) == 155
    assert [v["item"] for v in voci] == [f"v{i:03d}" for i in range(1, 156)]
    assert Counter(v["pair_id"] for v in voci if v["repeat_of"] is None) == Counter(
        c.pair_id for c in pacchetto["coppie"])

    posizione = {v["item"]: i for i, v in enumerate(voci)}
    per_voce = {v["item"]: v for v in voci}
    ripetute = [v for v in voci if v["repeat_of"] is not None]
    assert len(ripetute) == 5
    assert len({v["pair_id"] for v in ripetute}) == 5
    for v in ripetute:
        originale = per_voce[v["repeat_of"]]
        assert originale["repeat_of"] is None
        assert originale["pair_id"] == v["pair_id"]
        assert (v["left_model"], v["right_model"]) == (originale["right_model"], originale["left_model"])
        assert posizione[v["item"]] - posizione[originale["item"]] >= 20


def test_k11b_la_chiave_e_coerente_con_le_coppie(pacchetto):
    per_id = {c.pair_id: c for c in pacchetto["coppie"]}
    for v in _voci(pacchetto["chiave"]):
        c = per_id[v["pair_id"]]
        assert {v["left_model"], v["right_model"]} == {c.model_a, c.model_b}
    lati = Counter(v["left_model"] == per_id[v["pair_id"]].model_a for v in _voci(pacchetto["chiave"]))
    assert lati[True] > 30 and lati[False] > 30      # lato sorteggiato, non sempre lo stesso


def test_k11c_nessun_nome_di_modello_ne_pair_id_nel_pacchetto(pacchetto):
    vietati = MODELLI + [c.pair_id for c in pacchetto["coppie"]]
    for file in pacchetto["dest"].rglob("*"):
        assert not any(v in file.name for v in vietati), file.name
        if file.is_file() and file.suffix in (".html", ".js", ".json", ".css"):
            testo = file.read_text(encoding="utf-8")
            trovati = [v for v in vietati if re.search(rf"\b{re.escape(v)}\b", testo)]
            assert trovati == [], (file.name, trovati[:5])


def test_k11d_immagini_con_nomi_neutri_tre_larghezze_per_lato(pacchetto):
    immagini = sorted(p.name for p in (pacchetto["dest"] / "img").iterdir())
    assert len(immagini) == 155 * 2 * 3
    assert all(re.fullmatch(r"v\d{3}-[sd]-(375|768|1440)\.png", n) for n in immagini)


def test_k11e_l_immagine_di_sinistra_e_quella_del_modello_di_sinistra(pacchetto):
    voce = _voci(pacchetto["chiave"])[0]
    c = next(c for c in pacchetto["coppie"] if c.pair_id == voce["pair_id"])
    immagine = (pacchetto["dest"] / "img" / f"{voce['item']}-s-768.png").read_bytes()
    assert immagine == f"png {c.task_id}-{voce['left_model']} 768".encode()


def test_k11f_una_cartella_esistente_non_si_sovrascrive(pacchetto, tmp_path):
    with pytest.raises(WebTaskError):
        build_vote_package(pacchetto["coppie"], {}, tmp_path / "render", pacchetto["dest"],
                           tmp_path / "altra_chiave.json")
    assert not (tmp_path / "altra_chiave.json").exists()


def test_k12_index_senza_fetch_ne_moduli_e_coppie_js_assegna_window_coppie(pacchetto):
    indice = pacchetto["indice"].read_text(encoding="utf-8")
    assert "fetch(" not in indice
    assert not re.search(r"^\s*import\s", indice, re.M)
    assert 'type="module"' not in indice
    assert '<script src="coppie.js"></script>' in indice

    righe = (pacchetto["dest"] / "coppie.js").read_text(encoding="utf-8").splitlines()
    assert righe[0].startswith("window.COPPIE = ") and righe[0].endswith(";")
    voci = json.loads(righe[0][len("window.COPPIE = "):-1])
    assert len(voci) == 155
    assert voci[0]["task"].startswith("Build a page number")
    assert set(voci[0]["images"]) == {"s", "d"}
    assert set(voci[0]["images"]["s"]) == {"375", "768", "1440"}
    assert righe[1] == "window.PAUSA = 20;"


# ── k13: lettura dei voti ──────────────────────────────────────────────────

def _scrivi_voti(pacchetto: dict, tmp_path: Path, voti: list[dict], package_id: str | None = None) -> Path:
    if package_id is None:
        package_id = hashlib.sha256((pacchetto["dest"] / "coppie.js").read_bytes()).hexdigest()
    file = tmp_path / "voti-v3.json"
    file.write_text(json.dumps({"voter": "v3", "package_id": package_id, "created": "2026-10-25",
                                "votes": voti}))
    return file


def test_k13_il_voto_si_riporta_all_orientamento_della_coppia(pacchetto, tmp_path):
    voci = _voci(pacchetto["chiave"])
    b_a_sinistra = next(v for v in voci if v["repeat_of"] is None and v["left_model"] > v["right_model"])
    b_a_destra = next(v for v in voci if v["repeat_of"] is None and v["left_model"] < v["right_model"])
    ripetuta = next(v for v in voci if v["repeat_of"] is not None)
    file = _scrivi_voti(pacchetto, tmp_path, [
        {"item": b_a_sinistra["item"], "value": 2, "ms": 4000, "ts": "t"},
        {"item": b_a_destra["item"], "value": 1, "ms": 3000, "ts": "t"},
        {"item": ripetuta["item"], "value": 0, "ms": 2000, "ts": "t"},
    ])

    voti = load_votes(file, pacchetto["chiave"], pacchetto["dest"])

    assert voti[0] == Vote(voter="v3", pair_id=b_a_sinistra["pair_id"], value=-2, repeat=False, ms=4000)
    assert voti[1] == Vote(voter="v3", pair_id=b_a_destra["pair_id"], value=1, repeat=False, ms=3000)
    assert voti[2].repeat is True and voti[2].pair_id == ripetuta["pair_id"]


@pytest.mark.parametrize("guasto", ["pacchetto", "voce", "valore"])
def test_k13b_pacchetto_diverso_voce_sconosciuta_o_valore_fuori_scala_sono_errori(pacchetto, tmp_path, guasto):
    voce = _voci(pacchetto["chiave"])[0]["item"]
    voto = {"item": voce, "value": 1, "ms": 1, "ts": "t"}
    package_id = None
    if guasto == "pacchetto":
        package_id = "0" * 64
    elif guasto == "voce":
        voto["item"] = "v999"
    else:
        voto["value"] = 3
    file = _scrivi_voti(pacchetto, tmp_path, [voto], package_id)

    with pytest.raises(WebTaskError):
        load_votes(file, pacchetto["chiave"], pacchetto["dest"])


# ── k15: riga di comando ───────────────────────────────────────────────────

def test_k15_il_sottocomando_calibration_ha_le_quattro_fasi():
    from campaign import build_parser

    for fase in ("fetch", "select", "render", "package"):
        args = build_parser().parse_args(["calibration", fase])
        assert args.comando == "calibration" and args.fase == fase
    args = build_parser().parse_args(["calibration", "render", "--workers", "2"])
    assert args.workers == 2
    assert build_parser().parse_args(["calibration", "render"]).workers == 3


# ── r18: dati veri ─────────────────────────────────────────────────────────

DATI = PROJECT_ROOT / "campaigns" / "data" / "calibrazione" / "risposte"
COMPITI = PROJECT_ROOT / "campaigns" / "data" / "webtasks" / "artifacts_bench.jsonl"


@pytest.mark.skipif(not os.environ.get("ORC_INTEGRATION"),
                    reason="legge 1 GB di risposte vere: ORC_INTEGRATION=1")
def test_r18_i_numeri_dell_analisi_si_riproducono_sui_dati_veri():
    if not DATI.is_dir() or not COMPITI.is_file():
        pytest.skip("dati non scaricati: python campaign.py calibration fetch")
    risposte, non_collegate = load_responses(DATI, COMPITI)
    coda = calibration_task_ids(PROJECT_ROOT / "campaigns" / "r1_ordine.json")

    assert non_collegate == 38
    _, scarti = usable_responses(risposte, coda, exclude_named=False)
    in_coda = len(risposte) - scarti["fuori_coda"]
    valide = in_coda - scarti["non_estraibile"] - scarti["non_valida"] - scarti["senza_punteggio"]
    assert in_coda == 14316
    assert valide == 3675
    assert valide - scarti["rete"] == 1815

    _, scarti = usable_responses(risposte, coda)
    assert scarti["nome_modello"] == 32

    coppie = select_pairs(risposte, coda)
    principali = coppie[:150]
    conti = Counter(m for c in principali for m in (c.model_a, c.model_b))
    assert len(conti) == 20 and set(conti.values()) == {15}
    assert 4.5 <= statistics.mean(abs(c.score_a - c.score_b) for c in principali) <= 5.5
    assert len(coppie) == 175

    senza_filtro = select_pairs(risposte, coda, exclude_named=False)
    print(f"\nsenza filtro dei nomi: {len(senza_filtro)} coppie in tutto")


def test_le_dataclass_sono_immutabili():
    for classe in (Response, Pair, Vote):
        assert dataclasses.is_dataclass(classe)
        assert classe.__dataclass_params__.frozen  # type: ignore[attr-defined]
