"""Punto d'ingresso CLI e composizione delle dipendenze concrete.

Il resto del progetto usa contratti e dipendenze iniettate; solo questo modulo
legge i segreti, costruisce i client dei fornitori e decide dove vivranno
workspace e ledger della run. E' il *composition root*: l'unico posto in cui
si sa quali implementazioni concrete stanno dietro le interfacce.

Stato (M2s.2): la run mono-agente passa ancora dal solo gateway compatibile
OpenAI, configurato via `.env`. Il percorso per fornitore — un client e un
gateway scelti in base al modello del ruolo — arriva con la fabbrica di agenti
di M2s.3; l'infrastruttura che gli serve (`config.credenziali_fornitore`,
`AnthropicChatGateway`, i campi `base_url` / `api_key_env` del registro) e' gia'
in piedi e coperta da test.
"""

import argparse
import logging
from pathlib import Path
from typing import Sequence

from openai import OpenAI

import config
from accounting import InMemoryAccountant, ModelRegistry
from accounting.ledger import RunLedger
from accounting.ledger_accountant import LedgerAccountant
from agent import Agent
from budget_guard import BudgetGuard
from llm_gateway import OpenAIChatGateway
from run_session import RunSession
from tools import build_default_tools


DEFAULT_TASK = "usando bash crea il file ciao.txt con dentro 'hello', poi con read_file rileggilo"
PROJECT_ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    """Costruisce la CLI senza accedere a ambiente, rete o Docker."""
    parser = argparse.ArgumentParser(description="Esegue una run dell'agente ORC")
    parser.add_argument("task", nargs="?", default=DEFAULT_TASK, help="task da assegnare all'agente")
    parser.add_argument(
        "--model",
        help="modello da usare: deve essere una chiave di models.toml, e un nome che "
             "l'endpoint configurato sappia servire",
    )
    parser.add_argument("--budget-usd", type=float, default=None,
                        help="tetto opzionale in USD per questa sola run; senza, la run "
                             "non e' limitata")
    parser.add_argument("--max-iterations", type=int, default=config.MAX_ITERAZIONI,
                        help="numero massimo di iterazioni ReAct")
    parser.add_argument("--workspace", type=Path, default=PROJECT_ROOT / "workspace",
                        help="directory usata dai tool e montata in Docker")
    parser.add_argument("--runs-dir", type=Path, default=PROJECT_ROOT / "runs",
                        help="directory in cui salvare i ledger delle run")
    return parser


def configure_logging() -> None:
    """Configura il logging dell'applicazione, senza effetti durante gli import."""
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: Sequence[str] | None = None) -> int:
    """Esegue una run completa e restituisce un exit code adatto alla shell."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_iterations <= 0:
        parser.error("--max-iterations deve essere maggiore di zero")

    configure_logging()
    settings = config.load_llm_settings(
        model_override=args.model, dotenv_path=PROJECT_ROOT / ".env",
    )
    registry = ModelRegistry.from_file(PROJECT_ROOT / "models.toml")
    if settings.model not in registry.models:
        parser.error(
            f"modello '{settings.model}' assente da models.toml; "
            "aggiungi il listino prima di lanciare una run"
        )

    # Ogni validazione precede la creazione del ledger: `parser.error` termina
    # il processo, e una directory di run creata prima resterebbe su disco
    # vuota e senza summary, indistinguibile da una run finita male.
    try:
        budget_guard = BudgetGuard(args.budget_usd)
    except ValueError as error:
        parser.error(str(error))

    ledger = RunLedger(root=args.runs_dir, task=args.task)
    ledger.append_event("budget_policy", budget_guard.policy_details)
    accountant = LedgerAccountant(InMemoryAccountant(registry), ledger)
    client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)
    gateway = OpenAIChatGateway(
        client, settings.model, accountant,
        api_provider=settings.api_provider,
        billing_provider=settings.billing_provider,
        event_sink=ledger,
        budget_guard=budget_guard,
    )
    agent = Agent(gateway, build_default_tools(str(args.workspace)))
    result = RunSession(agent, ledger).run(args.task, max_iterations=args.max_iterations)
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
