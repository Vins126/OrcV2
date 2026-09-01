"""Il bootstrap resta importabile e configurabile senza contattare servizi esterni."""

import pytest

import config
from main import build_parser, main


def test_parser_esprime_un_task_e_opzioni_di_run_isolate():
    args = build_parser().parse_args([
        "--model", "opus-5",
        "--budget-usd", "1.25",
        "--workspace", "/tmp/work",
        "--runs-dir", "/tmp/runs",
        "task di prova",
    ])

    assert args.task == "task di prova"
    assert args.model == "opus-5"
    assert args.budget_usd == 1.25
    assert str(args.workspace) == "/tmp/work"
    assert str(args.runs_dir) == "/tmp/runs"


def test_configurazione_llm_viene_letta_solo_quando_richiesta(monkeypatch):
    monkeypatch.setenv("ORC2_BASE_URL", "http://proxy.test")
    monkeypatch.setenv("ORC2_API_KEY", "test-key")
    monkeypatch.setenv("ORC2_MODEL", "default-model")
    monkeypatch.setenv("ORC2_API_PROVIDER", "test-proxy")
    monkeypatch.setenv("ORC2_BILLING_PROVIDER", "test-billing")

    settings = config.load_llm_settings(model_override="override-model")

    assert settings.base_url == "http://proxy.test"
    assert settings.model == "override-model"
    assert settings.api_provider == "test-proxy"
    assert settings.billing_provider == "test-billing"


def test_un_budget_invalido_non_lascia_directory_di_run(tmp_path, monkeypatch):
    """La validazione precede la creazione del ledger.

    Una directory creata prima di un `parser.error` resterebbe su disco vuota
    e senza summary, indistinguibile da una run finita male: sporcherebbe
    proprio l'archivio da cui si ricavano i dati della tesi.
    """
    monkeypatch.setenv("ORC2_BASE_URL", "http://proxy.test")
    monkeypatch.setenv("ORC2_API_KEY", "test-key")
    monkeypatch.setenv("ORC2_MODEL", "opus-5")
    runs_dir = tmp_path / "runs"

    with pytest.raises(SystemExit):
        main(["--budget-usd", "-1", "--runs-dir", str(runs_dir), "task"])

    assert not runs_dir.exists() or list(runs_dir.iterdir()) == []


# ── Credenziali per fornitore ─────────────────────────────────────────────

def test_le_credenziali_arrivano_dal_registro_e_dall_ambiente(monkeypatch):
    """Il registro conosce il NOME della variabile, l'ambiente il valore.

    E' la separazione che impedisce a una chiave di finire in un file che i
    test leggono, i messaggi d'errore stampano e i log potrebbero serializzare.
    """
    monkeypatch.setenv("ORC2_TEST_KEY", "segreto")

    credenziali = config.credenziali_fornitore("acme", {
        "base_url": "https://api.acme.test",
        "api_key_env": "ORC2_TEST_KEY",
    })

    assert credenziali.provider == "acme"
    assert credenziali.base_url == "https://api.acme.test"
    assert credenziali.api_key == "segreto"


def test_base_url_assente_lascia_decidere_all_sdk():
    """Un fornitore senza `base_url` usa l'endpoint di default della sua libreria."""
    import os
    os.environ["ORC2_TEST_KEY2"] = "segreto"
    try:
        assert config.credenziali_fornitore(
            "acme", {"api_key_env": "ORC2_TEST_KEY2"}).base_url is None
    finally:
        del os.environ["ORC2_TEST_KEY2"]


def test_fornitore_senza_api_key_env_e_un_errore_parlante():
    with pytest.raises(RuntimeError) as errore:
        config.credenziali_fornitore("acme", {"monthly_fee": 0.0})

    assert "acme" in str(errore.value)
    assert "api_key_env" in str(errore.value)


def test_variabile_dichiarata_ma_assente_nomina_fornitore_e_variabile(monkeypatch):
    """Con cinque fornitori, «manca una chiave» non basta a capire quale."""
    monkeypatch.delenv("ORC2_MANCANTE", raising=False)

    with pytest.raises(RuntimeError) as errore:
        config.credenziali_fornitore("acme", {"api_key_env": "ORC2_MANCANTE"})

    messaggio = str(errore.value)
    assert "acme" in messaggio and "ORC2_MANCANTE" in messaggio


def test_i_fornitori_reali_dichiarano_dove_sta_la_loro_chiave():
    """Ogni provider di `models.toml` deve essere raggiungibile.

    Non verifica che la chiave esista — quello dipende dalla macchina — ma che
    il registro dica dove cercarla. Un provider senza `api_key_env` sarebbe
    inutilizzabile e il difetto si scoprirebbe solo al primo uso.
    """
    from accounting import ModelRegistry

    registro = ModelRegistry.from_file("models.toml")
    senza = [p for p, dati in registro.providers.items() if not dati.get("api_key_env")]

    assert senza == [], f"fornitori senza api_key_env: {senza}"
