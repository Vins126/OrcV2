"""Il bootstrap resta importabile e configurabile senza contattare servizi esterni."""

import os

import pytest

import config
import main as modulo_main
from agent import RunResult
from main import build_parser, main
from run_status import RunStatus


def test_parser_esprime_un_task_e_opzioni_di_run_isolate():
    args = build_parser().parse_args([
        "--budget-usd", "1.25",
        "--workspace", "/tmp/work",
        "--runs-dir", "/tmp/runs",
        "task di prova",
    ])

    assert args.task == "task di prova"
    assert args.budget_usd == 1.25
    assert str(args.workspace) == "/tmp/work"
    assert str(args.runs_dir) == "/tmp/runs"


def test_un_budget_invalido_non_lascia_directory_di_run(tmp_path, monkeypatch):
    """La validazione precede la creazione del ledger.

    Una directory creata prima di un `parser.error` resterebbe su disco vuota
    e senza summary, indistinguibile da una run finita male: sporcherebbe
    proprio l'archivio da cui si ricavano i dati della tesi.
    """
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



# ── CLI: il ruolo, scelto dalla riga di comando ───────────────────────────

def test_il_parser_conosce_il_ruolo():
    args = build_parser().parse_args(["--role", "planner", "task"])

    assert args.role == "planner"


def test_per_default_il_ruolo_non_e_imposto():
    args = build_parser().parse_args(["task"])

    assert args.role is None    # il predefinito (worker) lo applica main, non il parser


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
        return RunResult(status=RunStatus(FabbricaFinta.esito), iterations=1)


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

    Il caricamento non pretende nessuna variabile: ogni strada ha la sua chiave
    e se ne legge una sola, quando la fabbrica costruisce l'agente.
    """
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "provvisoria")
    monkeypatch.delenv("ORC2_OPENROUTER_KEY")        # cosi' a fine test torna com'era
    env = tmp_path / ".env"
    env.write_text("ORC2_OPENROUTER_KEY=dal-file\n", encoding="utf-8")

    main(["task"], dotenv_path=env)

    assert os.environ["ORC2_OPENROUTER_KEY"] == "dal-file"


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
    monkeypatch.setenv("ORC2_OPENROUTER_KEY", "provvisoria")
    monkeypatch.delenv("ORC2_OPENROUTER_KEY")

    with pytest.raises(SystemExit) as uscita:
        main(["--role", "worker", "--runs-dir", str(tmp_path / "runs"),
              "--workspace", str(tmp_path / "ws"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert "ORC2_OPENROUTER_KEY" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists() and not (tmp_path / "ws").exists()
