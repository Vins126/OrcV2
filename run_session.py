"""Lifecycle applicativo di una run: agente + ledger."""

from typing import Any

from accounting.ledger import RunLedger
from agent import AgentFailure
from run_reporter import RunReporter


class RunSession:
    """Esegue un agente e chiude sempre il ledger associato alla sua run."""

    def __init__(self, agent: Any, ledger: RunLedger, reporter: RunReporter | None = None):
        """Registra agente, ledger e reporter della run.

        Args:
            agent: l'agente da eseguire.
            ledger: il ledger da chiudere in ogni esito, eccezioni comprese.
            reporter: chi emette il rapporto finale; se assente ne viene creato uno.
        """
        self.agent = agent
        self.ledger = ledger
        self.reporter = reporter or RunReporter()

    def run(self, task: str, max_iterations: int | None = None) -> Any:
        """Esegue la run, ne persiste l'esito e propaga errori inattesi."""
        try:
            if max_iterations is None:
                result = self.agent.run(task)
            else:
                result = self.agent.run(task, max_iterations=max_iterations)
        except AgentFailure as error:
            # L'agente allega alle sue eccezioni le iterazioni gia' svolte:
            # senza, il summary direbbe "0 iterazioni" per una run che aveva
            # gia' lavorato, e il costo per iterazione risulterebbe nullo pur
            # essendoci una spesa registrata.
            self.ledger.append_event(
                "unexpected_error",
                {"error_type": error.cause_type, "iterations": error.iterations},
            )
            summary = self.ledger.close(
                status="unexpected_error", iterations=error.iterations,
            )
            self._report(summary)
            raise
        except Exception as error:
            # Guasto fuori dal ciclo dell'agente: qui il conteggio non esiste
            # proprio, e zero e' l'unico valore onesto.
            self.ledger.append_event(
                "unexpected_error",
                {"error_type": type(error).__name__},
            )
            summary = self.ledger.close(status="unexpected_error", iterations=0)
            self._report(summary)
            raise

        if result.status != "completed":
            self.ledger.append_event(
                "run_terminated",
                {"status": result.status, "iterations": result.iterations},
            )
        summary = self.ledger.close(status=result.status, iterations=result.iterations)
        self._report(summary, result.final_message)
        return result

    def _report(self, summary: dict[str, Any], agent_message: str | None = None) -> None:
        """Emette il report soltanto dopo che il summary e' stato persistito."""
        self.reporter.emit(
            summary, self.ledger.read_events(), str(self.ledger.run_dir), agent_message,
        )
