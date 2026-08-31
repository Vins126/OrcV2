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
