"""Il bootstrap resta importabile e configurabile senza contattare servizi esterni."""

import json
import os
from types import SimpleNamespace as NS

import pytest

import config
import main as modulo_main
from agent import RunResult
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



# ── CLI: due percorsi, scelti dalla riga di comando ───────────────────────

def test_il_parser_conosce_il_ruolo_e_il_percorso_via_proxy():
    args = build_parser().parse_args(["--role", "planner", "--via-proxy", "task"])

    assert args.role == "planner"
    assert args.via_proxy is True


def test_per_default_il_percorso_e_diretto_e_il_ruolo_non_e_imposto():
    args = build_parser().parse_args(["task"])

    assert args.via_proxy is False
    assert args.role is None   # il predefinito (worker) lo applica main, non il parser


def test_model_senza_via_proxy_e_un_errore_che_spiega_cosa_fare(capsys, tmp_path):
    """Nel percorso diretto il modello lo decide il ruolo: `--model` sarebbe ignorato.

    Ignorarlo in silenzio farebbe credere di aver scelto un modello che in realta'
    non si sta usando, e il costo misurato sarebbe di un altro.
    """
    with pytest.raises(SystemExit) as uscita:
        main(["--model", "opus-5", "task"], dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert "--via-proxy" in capsys.readouterr().err


# ── Percorso diretto: main parla con la fabbrica ──────────────────────────

class FabbricaFinta:
    """Sostituisce `AgentFactory`: registra come la usa `main`, senza rete ne' Docker."""

    esito = "completed"
    istanze: list = []

    def __init__(self, registry, runs_root, workspaces_root, *, budget_usd=None):
        self.runs_root, self.workspaces_root = runs_root, workspaces_root
        self.budget_usd = budget_usd
        self.ruolo = None
        self.incarichi = []
        FabbricaFinta.istanze.append(self)

    def build(self, role):
        self.ruolo = role
        return self

    def assign(self, task, max_iterations=None):
        self.incarichi.append((task, max_iterations))
        return RunResult(status=FabbricaFinta.esito, iterations=1)


@pytest.fixture
def fabbrica_finta(monkeypatch):
    FabbricaFinta.istanze = []
    FabbricaFinta.esito = "completed"
    monkeypatch.setattr(modulo_main, "AgentFactory", FabbricaFinta)
    return FabbricaFinta


def test_il_percorso_diretto_costruisce_l_agente_del_ruolo_predefinito(
        fabbrica_finta, tmp_path):
    codice = main(
        ["--budget-usd", "0.5", "--max-iterations", "7",
         "--runs-dir", str(tmp_path / "runs"), "--workspace", str(tmp_path / "ws"),
         "fai una cosa"],
        dotenv_path=tmp_path / ".env",
    )

    fabbrica = fabbrica_finta.istanze[0]
    assert codice == 0
    assert fabbrica.ruolo == "worker"
    assert fabbrica.incarichi == [("fai una cosa", 7)]
    assert fabbrica.budget_usd == 0.5
    assert str(fabbrica.runs_root) == str(tmp_path / "runs")
    assert str(fabbrica.workspaces_root) == str(tmp_path / "ws")


def test_il_ruolo_indicato_arriva_alla_fabbrica(fabbrica_finta, tmp_path):
    main(["--role", "planner", "task"], dotenv_path=tmp_path / ".env")

    assert fabbrica_finta.istanze[0].ruolo == "planner"


def test_l_exit_code_dice_se_l_incarico_e_riuscito(fabbrica_finta, tmp_path):
    fabbrica_finta.esito = "budget_exhausted"

    assert main(["task"], dotenv_path=tmp_path / ".env") == 1


def test_il_percorso_diretto_legge_le_chiavi_dal_file_env_indicato(
        fabbrica_finta, monkeypatch, tmp_path):
    """Le chiavi per fornitore stanno in `.env`: va caricato anche qui.

    Prima di M2s l'unico a leggere `.env` era `load_llm_settings`, che chiede la
    terna del proxy. Il percorso diretto non la usa, quindi serve un caricamento
    a se' che non pretenda nessuna variabile.
    """
    monkeypatch.setenv("ORC2_MINIMAX_KEY", "provvisoria")
    monkeypatch.delenv("ORC2_MINIMAX_KEY")        # cosi' a fine test torna com'era
    env = tmp_path / ".env"
    env.write_text("ORC2_MINIMAX_KEY=dal-file\n", encoding="utf-8")

    main(["task"], dotenv_path=env)

    assert os.environ["ORC2_MINIMAX_KEY"] == "dal-file"


# ── Percorso diretto: gli errori di configurazione non lasciano tracce ────

def test_ruolo_ignoto_esce_con_un_messaggio_e_non_crea_cartelle(capsys, tmp_path):
    with pytest.raises(SystemExit) as uscita:
        main(["--role", "giudice", "--runs-dir", str(tmp_path / "runs"),
              "--workspace", str(tmp_path / "ws"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert "giudice" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists() and not (tmp_path / "ws").exists()


def test_chiave_mancante_nomina_la_variabile_e_non_crea_cartelle(
        monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ORC2_MINIMAX_KEY", "provvisoria")
    monkeypatch.delenv("ORC2_MINIMAX_KEY")

    with pytest.raises(SystemExit) as uscita:
        main(["--role", "worker", "--runs-dir", str(tmp_path / "runs"),
              "--workspace", str(tmp_path / "ws"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert "ORC2_MINIMAX_KEY" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists() and not (tmp_path / "ws").exists()


# ── Percorso via proxy: com'era prima, perche' serve al confronto di M2s.4 ─

class ClientProxyFinto:
    """Client compatibile OpenAI che registra le richieste ricevute."""

    def __init__(self):
        self.richieste = []
        self.chat = NS(completions=NS(create=self._crea))

    def _crea(self, **kwargs):
        self.richieste.append(kwargs)
        return NS(
            id="chat_1",
            usage=NS(prompt_tokens=100, completion_tokens=50,
                     prompt_tokens_details=None, completion_tokens_details=None),
            choices=[NS(finish_reason="stop",
                        message=NS(content="fatto", tool_calls=None))],
        )


@pytest.fixture
def proxy_finto(monkeypatch):
    """Sostituisce client OpenAI e strumenti, e fornisce la terna del proxy."""
    client = ClientProxyFinto()
    monkeypatch.setattr(modulo_main, "OpenAI", lambda **kwargs: client)
    monkeypatch.setattr(modulo_main, "build_default_tools", lambda percorso: [])
    monkeypatch.setenv("ORC2_BASE_URL", "http://proxy.test")
    monkeypatch.setenv("ORC2_API_KEY", "chiave-fittizia")
    monkeypatch.setenv("ORC2_MODEL", "minimax-m2-7")
    return client


def test_via_proxy_il_modello_di_models_toml_arriva_al_proxy(
        proxy_finto, tmp_path, capsys):
    codice = main(
        ["--via-proxy", "--model", "minimax-m2-7",
         "--runs-dir", str(tmp_path / "runs"), "--workspace", str(tmp_path / "ws"), "task"],
        dotenv_path=tmp_path / ".env",
    )

    assert codice == 0
    assert proxy_finto.richieste[0]["model"] == "minimax-m2-7"
    (run,) = (tmp_path / "runs").iterdir()
    sommario = json.loads((run / "summary.json").read_text())
    assert sommario["status"] == "completed"
    assert list(sommario["cost_by_model"]) == ["minimax-m2-7"]


def test_via_proxy_il_ruolo_sceglie_il_modello_da_inviare(proxy_finto, tmp_path, capsys):
    """Per confrontare lo stesso modello nei due percorsi serve poterlo indicare per ruolo."""
    main(["--via-proxy", "--role", "planner",
          "--runs-dir", str(tmp_path / "runs"), "--workspace", str(tmp_path / "ws"), "task"],
         dotenv_path=tmp_path / ".env")

    assert proxy_finto.richieste[0]["model"] == "opus-5"


def test_via_proxy_ruolo_ignoto_esce_senza_creare_il_ledger(
        proxy_finto, tmp_path, capsys):
    with pytest.raises(SystemExit) as uscita:
        main(["--via-proxy", "--role", "giudice",
              "--runs-dir", str(tmp_path / "runs"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert not (tmp_path / "runs").exists()
