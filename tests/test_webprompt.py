"""Il prompt dei bracci si costruisce da testo del compito, cornice comune e materiale del compito.

Nota di design (tesi):
    Il prompt e' l'unica cosa che i bracci vedono del compito: se cambiasse da un
    braccio all'altro, il confronto misurerebbe il prompt e non il sistema. Per
    questo e' una funzione pura dei file in `campaigns/r1_prompt/` e del testo del
    compito. Il materiale del braccio sta in file separati da quelli di
    valutazione (`campaigns/r1_valutazione/`): script e domande del giudice non
    devono mai entrare nel prompt (stessa regola della soluzione di riferimento in
    Polyglot). I test in fondo controllano che i file veri restino allineati ai
    materiali di valutazione approvati.
"""

import re
from pathlib import Path

import pytest

from webprompt import MATERIAL_DIR, MAX_MARKERS, build_prompt, load_material
from webtasks import ARTIFACTS, WEBGEN, Candidate, WebTask, WebTaskError, load_selection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALUTAZIONE = PROJECT_ROOT / "campaigns" / "r1_valutazione"
DATI = PROJECT_ROOT / "campaigns" / "data" / "webtasks"
COMPITI = ("000098", "000040", "000058", "684", "842")

PREAMBOLO = ("You are a code expert. Please use your professional knowledge to generate accurate and "
             "professional responses.")

#: Parole che segnalano materiale di valutazione finito nel prompt.
PAROLE_RISERVATE = ("script", "judge", "giudice", "passo", "vetrina", "showcase", "checklist", "score",
                    "punteggio")


def _webtask(id_: str = "7", testo: str = f"{PREAMBOLO} Build a page.", fonte: str = ARTIFACTS) -> WebTask:
    return WebTask(candidate=Candidate(id=id_, source=fonte, label="x", text=testo), kind="applicazione")


def _materiale(cartella: Path, id_: str, corpo: str, cornice: str = "## How to deliver\n\n- `start.sh`\n") -> Path:
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "cornice.md").write_text(cornice)
    (cartella / f"{id_}.md").write_text(corpo)
    return cartella


def _marcatori(n: int) -> str:
    righe = "\n".join(f"| `m-{i}` | elemento {i} |" for i in range(n))
    return f"## data-testid markers\n\n| Marker | Element |\n|---|---|\n{righe}\n"


CONTRATTO = ("## Routes contract\n\n| Method | Path | Request body | Response | Errors |\n|---|---|---|---|---|\n"
             "| GET | `/api/things` | — | 200 | — |\n")


# ── Costruzione del prompt ─────────────────────────────────────────────────

def test_p1_il_testo_del_compito_arriva_intatto_col_preambolo(tmp_path):
    cartella = _materiale(tmp_path, "7", _marcatori(2))
    testo = f"{PREAMBOLO}\n\nBuild   a page\nwith two lines."

    prompt = build_prompt(_webtask(testo=testo), cartella)

    assert testo in prompt


def test_p2_contiene_cornice_contratto_e_marcatori(tmp_path):
    cartella = _materiale(tmp_path, "7", CONTRATTO + "\n" + _marcatori(3) + "\n## Notes\n\n- a note\n",
                          cornice="## How to deliver\n\n- start.sh on port 8080\n")

    prompt = build_prompt(_webtask(), cartella)

    assert "start.sh on port 8080" in prompt
    assert "`/api/things`" in prompt
    assert all(f"`m-{i}`" in prompt for i in range(3))
    assert "- a note" in prompt


def test_p3_l_ordine_e_compito_poi_cornice_poi_materiale(tmp_path):
    cartella = _materiale(tmp_path, "7", CONTRATTO + "\n" + _marcatori(1), cornice="## How to deliver\n")

    prompt = build_prompt(_webtask(testo="TESTO DEL COMPITO"), cartella)

    assert prompt.index("TESTO DEL COMPITO") < prompt.index("## How to deliver") < prompt.index("## Routes contract")


def test_p4_senza_contratto_non_c_e_la_sezione_delle_rotte(tmp_path):
    cartella = _materiale(tmp_path, "7", _marcatori(2))

    assert "Routes contract" not in build_prompt(_webtask(), cartella)
    assert load_material(cartella / "7.md").has_contract is False


def test_p5_due_chiamate_danno_lo_stesso_prompt(tmp_path):
    cartella = _materiale(tmp_path, "7", CONTRATTO + _marcatori(2))

    assert build_prompt(_webtask(), cartella) == build_prompt(_webtask(), cartella)


def test_p6_i_marcatori_si_leggono_in_ordine_e_la_famiglia_conta_uno(tmp_path):
    corpo = ("## data-testid markers\n\n| Marker | Element |\n|---|---|\n"
             "| `nav-link-<section>` | one per section: `nav-link-home`, `nav-link-cart` |\n"
             "| `site-nav` | the bar |\n")

    materiale = load_material(_scrivi(tmp_path, corpo))

    assert materiale.markers == ("nav-link-<section>", "site-nav")


def _scrivi(cartella: Path, corpo: str) -> Path:
    percorso = cartella / "7.md"
    percorso.write_text(corpo)
    return percorso


# ── Errori: si fermano prima di qualunque generazione ──────────────────────

def test_p7_materiale_mancante_e_un_errore(tmp_path):
    cartella = _materiale(tmp_path, "8", _marcatori(1))

    with pytest.raises(WebTaskError, match="7"):
        build_prompt(_webtask(id_="7"), cartella)


def test_p8_cornice_mancante_e_un_errore(tmp_path):
    cartella = _materiale(tmp_path, "7", _marcatori(1))
    (cartella / "cornice.md").unlink()

    with pytest.raises(WebTaskError, match="cornice"):
        build_prompt(_webtask(), cartella)


def test_p9_piu_di_dodici_marcatori_e_un_errore(tmp_path):
    with pytest.raises(WebTaskError, match=str(MAX_MARKERS)):
        load_material(_scrivi(tmp_path, _marcatori(MAX_MARKERS + 1)))


def test_p10_dodici_marcatori_vanno_bene(tmp_path):
    assert len(load_material(_scrivi(tmp_path, _marcatori(MAX_MARKERS))).markers) == MAX_MARKERS


def test_p11_marcatore_doppio_e_un_errore(tmp_path):
    corpo = "## data-testid markers\n\n| Marker | Element |\n|---|---|\n| `a` | x |\n| `a` | y |\n"

    with pytest.raises(WebTaskError, match="`a`"):
        load_material(_scrivi(tmp_path, corpo))


def test_p12_sezione_dei_marcatori_mancante_o_vuota_e_un_errore(tmp_path):
    with pytest.raises(WebTaskError, match="markers"):
        load_material(_scrivi(tmp_path, CONTRATTO))
    with pytest.raises(WebTaskError, match="markers"):
        load_material(_scrivi(tmp_path, "## data-testid markers\n\nnessuna tabella\n"))


def test_p13_una_sezione_sconosciuta_e_un_errore(tmp_path):
    # Una sezione con un altro titolo potrebbe essere materiale di valutazione copiato per sbaglio.
    with pytest.raises(WebTaskError, match="Interaction script"):
        load_material(_scrivi(tmp_path, _marcatori(1) + "\n## Interaction script\n\n1. click\n"))


def test_p14_testo_prima_della_prima_sezione_e_un_errore(tmp_path):
    with pytest.raises(WebTaskError, match="prima"):
        load_material(_scrivi(tmp_path, "# Titolo\n\n" + _marcatori(1)))


# ── File veri: allineati ai materiali di valutazione approvati ─────────────

def _sezione(testo: str, numero: int) -> str:
    """Il corpo della sezione `## <numero>.` di un file di valutazione."""
    trovata = re.search(rf"^## {numero}\..*?$(.*?)(?=^## |\Z)", testo, re.MULTILINE | re.DOTALL)
    assert trovata, f"sezione {numero} non trovata"
    return trovata.group(1)


def _primi_codici_delle_righe(sezione: str) -> list[str]:
    """Il primo testo fra backtick di ogni riga di tabella (le righe d'intestazione non ne hanno)."""
    codici = []
    for riga in sezione.splitlines():
        if riga.startswith("|"):
            trovato = re.search(r"`([^`]+)`", riga)
            if trovato:
                codici.append(trovato.group(1))
    return codici


def _rotte(sezione: str) -> set[tuple[str, str]]:
    return set(re.findall(r"^\| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)`", sezione, re.MULTILINE))


def _senza_segnaposto(rotte: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Toglie i segnaposto, che il prompt traduce (`<etichetta>` -> `<tag>`, `?q=testo` -> `?q=text`)."""
    return {(m, re.sub(r"=[^&]*", "=", re.sub(r"<[^>]+>", "<>", p))) for m, p in rotte}


@pytest.mark.parametrize("id_", COMPITI)
def test_p15_i_marcatori_sono_quelli_dei_materiali_di_valutazione(id_):
    valutazione = (VALUTAZIONE / f"{id_}.md").read_text()

    attesi = _primi_codici_delle_righe(_sezione(valutazione, 3))
    attesi = [a.replace("<sezione>", "<section>") for a in attesi]

    assert list(load_material(MATERIAL_DIR / f"{id_}.md").markers) == attesi


@pytest.mark.parametrize("id_", COMPITI)
def test_p16_le_rotte_sono_quelle_dei_materiali_di_valutazione(id_):
    valutazione = (VALUTAZIONE / f"{id_}.md").read_text()
    prompt = (MATERIAL_DIR / f"{id_}.md").read_text()

    rotte_valutazione = _senza_segnaposto(_rotte(_sezione(valutazione, 2)))

    assert _senza_segnaposto(_rotte(prompt)) == rotte_valutazione
    assert load_material(MATERIAL_DIR / f"{id_}.md").has_contract is bool(rotte_valutazione)


@pytest.mark.parametrize("id_", COMPITI)
def test_p17_ogni_marcatore_e_usato_dallo_script(id_):
    script = (VALUTAZIONE / f"{id_}.py").read_text()

    for marcatore in load_material(MATERIAL_DIR / f"{id_}.md").markers:
        assert marcatore.split("<")[0] in script, marcatore


@pytest.mark.parametrize("nome", ("cornice", *COMPITI))
def test_p18_il_materiale_non_contiene_parole_della_valutazione(nome):
    testo = (MATERIAL_DIR / f"{nome}.md").read_text().lower()

    assert [p for p in PAROLE_RISERVATE if p in testo] == []


@pytest.mark.skipif(not (DATI / "artifacts_bench.jsonl").exists(),
                    reason="servono i file veri: python campaign.py fetch-webtasks")
def test_p19_i_cinque_prompt_veri_si_costruiscono_col_testo_intatto():
    compiti = load_selection(PROJECT_ROOT / "campaigns" / "r1_compiti.toml", DATI)

    assert sorted(c.candidate.id for c in compiti) == sorted(COMPITI)
    for compito in compiti:
        prompt = build_prompt(compito)
        assert compito.candidate.text in prompt
        assert "start.sh" in prompt and "8080" in prompt and "datetime-local" in prompt
        assert ("You are a code expert" in prompt) is (compito.candidate.source == ARTIFACTS)
        assert compito.candidate.source in (WEBGEN, ARTIFACTS)


# ── Revisione indipendente del 24 ott: titoli, doppioni, codici ────────────

@pytest.mark.parametrize("titolo", ("### Test diretti sulle rotte", "# Titolo", "#### Vetrina"))
def test_p20_qualunque_altro_titolo_dentro_una_sezione_e_un_errore(tmp_path, titolo):
    # I file di valutazione usano sottosezioni `###`: e' la copia per sbaglio piu' probabile.
    with pytest.raises(WebTaskError, match=re.escape(titolo.lstrip("# "))):
        load_material(_scrivi(tmp_path, CONTRATTO + f"\n{titolo}\n\n| `x` | y |\n" + _marcatori(1)))


def test_p21_una_sezione_ripetuta_e_un_errore(tmp_path):
    with pytest.raises(WebTaskError, match="Notes"):
        load_material(_scrivi(tmp_path, _marcatori(1) + "\n## Notes\n\n- a\n\n## Notes\n\n- b\n"))


def test_p22_i_titoli_dentro_un_blocco_di_codice_non_contano(tmp_path):
    corpo = CONTRATTO + "\n```text\n## Notes\n### altro\n```\n\n" + _marcatori(2)

    materiale = load_material(_scrivi(tmp_path, corpo))

    assert materiale.markers == ("m-0", "m-1")


def _codici_per_rotta(testo: str) -> dict[tuple[str, str], set[str]]:
    """Per ogni riga di rotta, i codici HTTP che compaiono nella riga."""
    codici = {}
    for riga in testo.splitlines():
        trovata = re.match(r"^\| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)`", riga)
        if trovata:
            chiave = next(iter(_senza_segnaposto({(trovata.group(1), trovata.group(2))})))
            codici[chiave] = set(re.findall(r"\b[1-5]\d\d\b", riga))
    return codici


@pytest.mark.parametrize("id_", COMPITI)
def test_p23_ogni_rotta_ha_gli_stessi_codici_http_dei_materiali_di_valutazione(id_):
    valutazione = _sezione((VALUTAZIONE / f"{id_}.md").read_text(), 2)

    assert _codici_per_rotta((MATERIAL_DIR / f"{id_}.md").read_text()) == _codici_per_rotta(valutazione)
