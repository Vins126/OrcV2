"""Test del registro dei modelli.

Coprono le tre responsabilita' della classe: il **calcolo del costo** con la
formula unica valida per ogni unita' di fatturazione, la **validazione** che
impedisce a una configurazione incoerente di entrare nel sistema, e
l'**assegnazione ruolo -> modello** dello stadio S1 del routing.

Nota di design (tesi):
    I test costruiscono il registro da dizionari invece che da file, cosi' che
    verifichino la logica e non la lettura del TOML. Un unico test in fondo
    carica il `models.toml` reale, per garantire che la configurazione
    effettivamente usata dal progetto sia valida: e' il controllo che
    intercetterebbe un refuso introdotto modificando i prezzi.
"""

import pytest

from accounting import (
    CapabilityUnavailable,
    MalformedRegistry,
    ModelNotFound,
    ModelRegistry,
    RoleNotFound,
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
        **modifiche: sezioni da sostituire (`units`, `providers`,
            `models`, `roles`).

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


def test_prezzo_non_finito_rifiutato():
    modelli = {"rotto": {"provider": "acme", "capabilities": ["code"],
                         "prices": {"input_tokens": float("nan")}}}
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


# ── Ruoli: assegnazione statica (stadio S1) ───────────────────────────────

RUOLI = {
    "planner": {"model": "grosso", "requires": ["reasoning", "code"]},
    "worker": {"model": "piccolo", "requires": ["code"]},
}


def test_il_ruolo_restituisce_il_modello_assegnato():
    """Il lookup che rende possibile il routing per ruolo.

    Chi chiama nomina un mestiere e non un modello: e' cio' che permette di
    cambiare l'assegnazione senza toccare una riga di codice.
    """
    r = _registro(roles=RUOLI)
    assert r.model_for("planner") == "grosso"
    assert r.model_for("worker") == "piccolo"


def test_ruolo_sconosciuto_elenca_quelli_disponibili():
    with pytest.raises(RoleNotFound) as errore:
        _registro(roles=RUOLI).model_for("giudice")
    messaggio = str(errore.value)
    assert "giudice" in messaggio
    assert "planner" in messaggio and "worker" in messaggio


def test_un_registro_senza_ruoli_resta_valido():
    """I ruoli sono facoltativi: senza `[roles]` il registro funziona lo stesso.

    Serve a non rompere le configurazioni precedenti a M2s, e a permettere ai
    test di costruire registri che dei ruoli non hanno bisogno.
    """
    r = _registro()
    assert r.roles == {}
    with pytest.raises(RoleNotFound):
        r.model_for("planner")


# ── Ruoli: validazione al caricamento ─────────────────────────────────────

def test_ruolo_su_modello_inesistente_e_rifiutato():
    with pytest.raises(MalformedRegistry) as errore:
        _registro(roles={"planner": {"model": "fantasma", "requires": []}})
    assert "fantasma" in str(errore.value)


def test_ruolo_con_capacita_sconosciuta_e_rifiutato():
    """Un refuso in `requires` non deve passare inosservato.

    Senza questo controllo, `requires = ["reasonning"]` non verrebbe mai
    soddisfatta da nessun modello, ma il file sembrerebbe corretto.
    """
    with pytest.raises(MalformedRegistry) as errore:
        _registro(roles={"planner": {"model": "grosso", "requires": ["reasonning"]}})
    assert "reasonning" in str(errore.value)


def test_modello_privo_di_una_capacita_richiesta_e_rifiutato():
    """Il cuore del capability-aware routing (D10/D11).

    `piccolo` sa scrivere codice ma non sa ragionare: assegnarlo al planner e'
    un errore di configurazione, e va scoperto all'avvio — non a meta' di una
    run gia' pagata. Il messaggio deve dire **quale** capacita' manca, non
    limitarsi a rifiutare.
    """
    with pytest.raises(MalformedRegistry) as errore:
        _registro(roles={"planner": {"model": "piccolo", "requires": ["reasoning", "code"]}})
    messaggio = str(errore.value)
    assert "reasoning" in messaggio
    assert "piccolo" in messaggio


def test_le_capacita_in_eccesso_non_disturbano():
    """Al ruolo interessa che il modello sappia fare almeno cio' che serve.

    `grosso` offre anche capacita' che il worker non richiede: e' irrilevante.
    Il controllo e' di inclusione, non di uguaglianza.
    """
    r = _registro(roles={"worker": {"model": "grosso", "requires": ["code"]}})
    assert r.model_for("worker") == "grosso"


def test_un_ruolo_senza_requisiti_e_ammesso():
    """`requires` assente significa "nessun requisito", non configurazione rotta."""
    r = _registro(roles={"worker": {"model": "piccolo"}})
    assert r.model_for("worker") == "piccolo"


# ── Capacita' pretesa dal pool ────────────────────────────────────────────

def test_require_capability_restituisce_i_modelli_capaci():
    assert _registro().require_capability("code") == ["grosso", "piccolo"]


def test_capacita_non_coperta_dal_pool_e_un_errore_parlante():
    """Chiedere cio' che nessuno sa fare deve fermarsi qui.

    Il messaggio elenca le capacita' effettivamente coperte: e' la risposta
    alla domanda successiva di chi legge l'errore — *e allora cosa posso
    fare?*
    """
    with pytest.raises(CapabilityUnavailable) as errore:
        _registro().require_capability("video_gen")
    messaggio = str(errore.value)
    assert "video_gen" in messaggio
    assert "code" in messaggio and "image_gen" in messaggio


def test_models_with_resta_tollerante():
    """`models_with` non deve essere stato contagiato da `require_capability`.

    Le due domande convivono: una accetta "nessuno" come risposta, l'altra no.
    Se un domani qualcuno le unificasse, questo test lo segnalerebbe.
    """
    assert _registro().models_with("video_gen") == []


# ── I ruoli reali del progetto ────────────────────────────────────────────

def test_i_ruoli_di_models_toml_sono_coerenti():
    """L'assegnazione realmente in uso regge la validazione delle capacita'.

    E' il test che intercetterebbe un'assegnazione sbagliata introdotta
    modificando la tabella dei ruoli: il caricamento del file reale esercita
    gia' tutti e tre i controlli.
    """
    r = ModelRegistry.from_file("models.toml")
    assert r.model_for("planner") in r.models
    assert r.model_for("worker") in r.models
    # Il worker deve costare meno del planner, altrimenti il routing per ruolo
    # non ha alcun senso economico.
    costo = lambda m: r.cost(m, "output_tokens", 1_000_000)
    assert costo(r.model_for("worker")) < costo(r.model_for("planner"))
