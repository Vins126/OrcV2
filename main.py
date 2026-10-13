"""Punto d'ingresso CLI e composizione delle dipendenze concrete.

Il resto del progetto usa contratti e dipendenze iniettate; solo questo modulo
legge i segreti e decide dove vivranno workspace e ledger. E' il *composition
root*: l'unico posto in cui si sa quali implementazioni concrete stanno dietro
le interfacce.

Si indica un *ruolo* e la fabbrica di agenti (`agent_factory`) costruisce
l'agente col modello che `models.toml` assegna a quel ruolo, raggiunto tramite
OpenRouter. Cambiare ruolo o modello non richiede di toccare codice.
"""

import argparse
import logging
from pathlib import Path
from typing import Sequence

import config
from accounting import ModelRegistry
from accounting.errors import RegistryError
from agent_factory import AgentFactory, UnsupportedProvider
from executors.docker import SandboxImageMissing, ensure_image


DEFAULT_TASK = "usando bash crea il file ciao.txt con dentro 'hello', poi con read_file rileggilo"
#: Ruolo usato quando non se ne indica uno.
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
    parser.add_argument("--budget-usd", type=float, default=None,
                        help="tetto opzionale in USD per questo agente; senza, non e' limitato")
    parser.add_argument("--max-iterations", type=int, default=config.MAX_ITERAZIONI,
                        help="numero massimo di iterazioni ReAct")
    parser.add_argument("--workspace", type=Path, default=PROJECT_ROOT / "workspace",
                        help="cartella che contiene i workspace, uno per agente")
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
    """La fabbrica costruisce l'agente del ruolo e gli assegna il task.

    Ogni errore di configurazione (ruolo ignoto, fornitore senza gateway,
    chiave mancante, tetto non valido) emerge in `build`, prima che si crei qualunque
    cartella: `parser.error` termina il processo e una directory di run lasciata
    a meta' sarebbe indistinguibile da una run finita male.
    """
    try:
        ensure_image(config.DOCKER_IMAGE, attempts=config.DOCKER_TENTATIVI_AVVIO,
                     delay=config.DOCKER_ATTESA_AVVIO_S, max_total_s=config.DOCKER_ATTESA_AVVIO_MAX_S)
    except SandboxImageMissing as error:
        parser.error(str(error))
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

    configure_logging()
    registry = ModelRegistry.from_file(PROJECT_ROOT / "models.toml")
    dotenv = dotenv_path if dotenv_path is not None else PROJECT_ROOT / ".env"

    return _run_direct(parser, args, registry, dotenv)


if __name__ == "__main__":
    raise SystemExit(main())
