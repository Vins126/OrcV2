"""Test del registro dei modelli.

Coprono le due responsabilita' della classe: il **calcolo del costo** con la
formula unica valida per ogni unita' di fatturazione, e la **validazione** che
impedisce a una configurazione incoerente di entrare nel sistema.

Nota di design (tesi):
    I test costruiscono il registro da dizionari invece che da file, cosi' che
    verifichino la logica e non la lettura del TOML. Un unico test in fondo
    carica il `models.toml` reale, per garantire che la configurazione
    effettivamente usata dal progetto sia valida: e' il controllo che
    intercetterebbe un refuso introdotto modificando i prezzi.
"""

import pytest

from accounting import (
    MalformedRegistry,
    ModelNotFound,
    ModelRegistry,
    UnitNotFound,
)

# Configurazione minima ma completa, con prezzi tondi scelti per rendere i
# costi attesi verificabili a mente.
CONFIG = {
    "units": {
        "input_tokens": 1_000_000,   # prezzo per milione
        "output_tokens": 1_000_000,
        "image": 1,                  # prezzo per pezzo
    },
    "providers": {
        "acme": {"monthly_fee": 20.0},
        "gratis": {"monthly_fee": 0.0},
    },
    "models": {
        "grosso": {
            "provider": "acme",
            "capabilities": ["reasoning", "code"],
            "prices": {"input_tokens": 10.0, "output_tokens": 30.0},
        },
        "piccolo": {
            "provider": "gratis",
            "capabilities": ["code"],
            "prices": {"input_tokens": 1.0, "output_tokens": 2.0},
        },
        "pittore": {
            "provider": "acme",
            "capabilities": ["image_gen"],
            "prices": {"image": 0.05},
        },
    },
}


def _registro(**modifiche):
    """Costruisce un registro dalla configurazione base, con sostituzioni.

    Args:
        **modifiche: sezioni da sostituire (`units`, `providers`, `models`).

    Returns:
        Il `ModelRegistry` corrispondente.
    """
    return ModelRegistry({**CONFIG, **modifiche})


# ── Calcolo del costo ─────────────────────────────────────────────────────

def test_costo_token_usa_la_base_per_milione():
    # 500.000 token a $10 per milione -> meta' del prezzo di un milione
    assert _registro().cost("grosso", "input_tokens", 500_000) == pytest.approx(5.0)


def test_costo_per_pezzo_non_viene_diviso():
    # Le immagini hanno base 1: 3 immagini a $0.05 -> $0.15, non $0.00000015.
    # E' il caso che la sezione [units] esiste per non sbagliare.
    assert _registro().cost("pittore", "image", 3) == pytest.approx(0.15)


def test_costo_di_una_chiamata_realistica():
    # 350 token in + 120 out, i due contributi si calcolano separatamente
    r = _registro()
    costo = r.cost("grosso", "input_tokens", 350) + r.cost("grosso", "output_tokens", 120)
    assert costo == pytest.approx(350 / 1e6 * 10.0 + 120 / 1e6 * 30.0)


def test_costo_nullo_per_consumo_nullo():
    assert _registro().cost("grosso", "input_tokens", 0) == 0.0


# ── Errori di lookup ──────────────────────────────────────────────────────

def test_modello_sconosciuto_elenca_le_alternative():
    with pytest.raises(ModelNotFound) as e:
        _registro().cost("inesistente", "input_tokens", 100)
    # Il messaggio deve orientare, non solo segnalare
    assert "inesistente" in str(e.value)
    assert "grosso" in str(e.value)


def test_unita_non_prevista_dal_modello():
    # 'pittore' esiste ma fattura a immagine, non a token
    with pytest.raises(UnitNotFound):
        _registro().cost("pittore", "input_tokens", 100)


def test_fornitore_sconosciuto():
    with pytest.raises(ModelNotFound):
        _registro().monthly_fee("nessuno")


# ── Validazione al caricamento ────────────────────────────────────────────

def test_prezzo_negativo_rifiutato():
    # Un costo negativo non produrrebbe un errore ma un numero sbagliato:
    # va intercettato all'avvio.
    modelli = {"rotto": {"provider": "acme", "capabilities": ["code"],
                         "prices": {"input_tokens": -1.0}}}
    with pytest.raises(MalformedRegistry):
        _registro(models=modelli)


def test_unita_senza_base_rifiutata():
    modelli = {"rotto": {"provider": "acme", "capabilities": ["code"],
                         "prices": {"unita_fantasma": 1.0}}}
    with pytest.raises(MalformedRegistry):
        _registro(models=modelli)


def test_fornitore_non_dichiarato_rifiutato():
    modelli = {"rotto": {"provider": "sconosciuto", "capabilities": ["code"],
                         "prices": {"input_tokens": 1.0}}}
    with pytest.raises(MalformedRegistry):
        _registro(models=modelli)


def test_modello_senza_prezzi_rifiutato():
    modelli = {"rotto": {"provider": "acme", "capabilities": ["code"], "prices": {}}}
    with pytest.raises(MalformedRegistry):
        _registro(models=modelli)


def test_capacita_sconosciuta_rifiutata():
    # Intercetta i refusi che renderebbero il modello invisibile al filtro
    modelli = {"rotto": {"provider": "acme", "capabilities": ["embeding"],
                         "prices": {"input_tokens": 1.0}}}
    with pytest.raises(MalformedRegistry):
        _registro(models=modelli)


def test_base_non_positiva_rifiutata():
    with pytest.raises(MalformedRegistry):
        _registro(units={"input_tokens": 0})


# ── Interrogazioni di supporto ────────────────────────────────────────────

def test_filtro_per_capacita():
    r = _registro()
    assert r.models_with("code") == ["grosso", "piccolo"]
    assert r.models_with("image_gen") == ["pittore"]


def test_capacita_offerta_da_nessuno_non_e_un_errore():
    # Lista vuota: e' un'informazione per il chiamante, non un guasto
    assert _registro().models_with("tts") == []


def test_costo_di_accesso_del_fornitore():
    r = _registro()
    assert r.monthly_fee("acme") == 20.0
    assert r.monthly_fee("gratis") == 0.0


# ── Il file reale del progetto ────────────────────────────────────────────

def test_models_toml_del_progetto_e_valido():
    """Il `models.toml` realmente usato supera la validazione.

    Non verifica i prezzi (cambiano), ma la coerenza strutturale: e' il test
    che segnala un refuso introdotto aggiornando un listino.
    """
    r = ModelRegistry.from_file("models.toml")
    assert r.models, "il registro del progetto non dovrebbe essere vuoto"
    # Il modello di embedding serve al router: la sua assenza sarebbe un errore
    assert r.models_with("embedding")


def test_file_toml_malformato(tmp_path):
    rotto = tmp_path / "rotto.toml"
    rotto.write_text("questo non e' [ TOML valido")
    with pytest.raises(MalformedRegistry):
        ModelRegistry.from_file(rotto)
