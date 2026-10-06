"""Punto d'ingresso CLI e composizione delle dipendenze concrete.

Il resto del progetto usa contratti e dipendenze iniettate; solo questo modulo
legge i segreti e decide dove vivranno workspace e ledger. E' il *composition
root*: l'unico posto in cui si sa quali implementazioni concrete stanno dietro
le interfacce.

Due percorsi per raggiungere i modelli, scelti dalla riga di comando:

- **diretto** (predefinito): si indica un *ruolo* e la fabbrica di agenti
  (`agent_factory`) costruisce l'agente col modello che `models.toml` assegna a
  quel ruolo, chiamando il suo fornitore con la sua chiave. Cambiare ruolo,
  modello o fornitore non richiede di toccare codice.
- **via proxy** (`--via-proxy`): un solo endpoint compatibile OpenAI per tutti i
  modelli, configurato via `.env`, come prima di M2s. Resta disponibile perche'
  la prima misura reale di M2s.4 confronta lo stesso modello nei due percorsi
  (la «tassa dell'aggregatore»): senza il percorso vecchio il confronto non si
  potrebbe fare. Dopo quella misura questo ramo si puo' togliere.
"""

import argparse
import logging
from pathlib import Path
from typing import Sequence

from openai import OpenAI

import config
from accounting import InMemoryAccountant, ModelRegistry
from accounting.errors import RegistryError
from accounting.ledger import RunLedger
from accounting.ledger_accountant import LedgerAccountant
from agent import Agent
from agent_factory import AgentFactory, UnsupportedProvider
from budget_guard import BudgetGuard
from llm_gateway import OpenAIChatGateway
from run_session import RunSession
from tools import build_default_tools


DEFAULT_TASK = "usando bash crea il file ciao.txt con dentro 'hello', poi con read_file rileggilo"
#: Ruolo usato nel percorso diretto quando non se ne indica uno.
DEFAULT_ROLE = "worker"
PROJECT_ROOT = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    """Costruisce la CLI senza accedere a ambiente, rete o Docker."""
    parser = argparse.ArgumentParser(description="Esegue una run dell'agente ORC")
    parser.add_argument("task", nargs="?", default=DEFAULT_TASK, help="task da assegnare all'agente")
    parser.add_argument(
        "--role",
        help=f"ruolo dell'agente, come in [roles.*] di models.toml (predefinito: "
             f"{DEFAULT_ROLE}); il ruolo decide modello e fornitore",
    )
    parser.add_argument(
        "--via-proxy", action="store_true",
        help="usa l'endpoint unico configurato in .env (ORC2_BASE_URL, ORC2_API_KEY) "
             "invece di chiamare direttamente il fornitore del ruolo",
    )
    parser.add_argument(
        "--model",
        help="solo con --via-proxy: modello da inviare al proxy, una chiave di "
             "models.toml; senza, lo decide --role oppure ORC2_MODEL",
    )
    parser.add_argument("--budget-usd", type=float, default=None,
                        help="tetto opzionale in USD per questo agente; senza, non e' limitato")
    parser.add_argument("--max-iterations", type=int, default=config.MAX_ITERAZIONI,
                        help="numero massimo di iterazioni ReAct")
    parser.add_argument("--workspace", type=Path, default=PROJECT_ROOT / "workspace",
                        help="percorso diretto: cartella che contiene i workspace, uno per "
                             "agente; via proxy: la cartella usata dai tool, montata in Docker")
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


def _run_direct(parser: argparse.ArgumentParser, args: argparse.Namespace,
                registry: ModelRegistry, dotenv_path: Path) -> int:
    """Percorso diretto: la fabbrica costruisce l'agente del ruolo e gli assegna il task.

    Ogni errore di configurazione (ruolo ignoto, fornitore senza gateway, chiave
    mancante, tetto non valido) emerge in `build`, prima che si crei qualunque
    cartella: `parser.error` termina il processo e una directory di run lasciata
    a meta' sarebbe indistinguibile da una run finita male.
    """
    config.load_environment(dotenv_path)
    try:
        factory = AgentFactory(
            registry, runs_root=args.runs_dir, workspaces_root=args.workspace,
            budget_usd=args.budget_usd,
        )
        built = factory.build(args.role or DEFAULT_ROLE)
    except (RegistryError, UnsupportedProvider, RuntimeError, ValueError) as error:
        parser.error(str(error))

    result = built.assign(args.task, max_iterations=args.max_iterations)
    return 0 if result.status == "completed" else 1


def _run_via_proxy(parser: argparse.ArgumentParser, args: argparse.Namespace,
                   registry: ModelRegistry, dotenv_path: Path) -> int:
    """Percorso via proxy: il montaggio a mano di un solo agente, com'era prima di M2s.

    Il modello inviato al proxy si decide cosi': `--model` se c'e', altrimenti
    quello del ruolo (utile a confrontare lo stesso modello nei due percorsi),
    altrimenti `ORC2_MODEL`.
    """
    try:
        override = args.model or (registry.model_for(args.role) if args.role else None)
    except RegistryError as error:
        parser.error(str(error))

    settings = config.load_llm_settings(model_override=override, dotenv_path=dotenv_path)
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


def main(argv: Sequence[str] | None = None, *, dotenv_path: Path | None = None) -> int:
    """Esegue un incarico completo e restituisce un exit code adatto alla shell.

    Args:
        argv: argomenti della riga di comando; `None` usa quelli del processo.
        dotenv_path: file `.env` da caricare; `None` usa quello del progetto.
            Iniettabile perche' i test non devono dipendere da un `.env` reale.

    Returns:
        0 se l'incarico si e' concluso con successo, 1 altrimenti.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_iterations <= 0:
        parser.error("--max-iterations deve essere maggiore di zero")
    if args.model and not args.via_proxy:
        parser.error(
            "--model vale solo con --via-proxy: nel percorso diretto il modello "
            "lo decide il ruolo (--role)"
        )

    configure_logging()
    registry = ModelRegistry.from_file(PROJECT_ROOT / "models.toml")
    dotenv = dotenv_path if dotenv_path is not None else PROJECT_ROOT / ".env"

    if args.via_proxy:
        return _run_via_proxy(parser, args, registry, dotenv)
    return _run_direct(parser, args, registry, dotenv)


if __name__ == "__main__":
    raise SystemExit(main())
