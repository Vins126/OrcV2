"""Report umano di fine run, derivato dal ledger senza ricalcolare costi."""

import logging
from typing import Any


log = logging.getLogger(__name__)


class RunReporter:
    """Trasforma summary ed eventi della run in un riepilogo leggibile."""

    _STATUS_LABELS = {
        "completed": "completato",
        "max_iterations": "limite di iterazioni raggiunto",
        "loop_detected": "loop rilevato",
        "budget_exhausted": "budget esaurito",
        "service_unavailable": "servizio LLM non disponibile",
        "unexpected_error": "errore inatteso",
    }

    def emit(
        self,
        summary: dict[str, Any],
        events: list[dict[str, Any]],
        ledger_path: str,
        agent_message: str | None = None,
    ) -> str:
        """Stampa, logga e restituisce il report della run appena chiusa."""
        report = self.render(summary, events, ledger_path)
        if agent_message:
            print(f"AGENTE: {agent_message}")
        print(report)
        # Il logger di sviluppo scrive anch'esso sul terminale: loggare il blocco
        # completo lo mostrerebbe due volte. Manteniamo quindi il report umano
        # una sola volta e nel log una riga strutturata, interrogabile.
        log.info(
            "run_report run_id=%s status=%s iterations=%s duration_s=%.3f "
            "usage_count=%s total_cost_usd=%.8f ledger=%s",
            summary["run_id"], summary["status"], summary["iterations"],
            summary["duration_s"], summary["usage_count"], summary["total_cost"],
            ledger_path,
        )
        return report

    def render(self, summary: dict[str, Any], events: list[dict[str, Any]], ledger_path: str) -> str:
        """Formatta il report; non legge file e non modifica alcuno stato."""
        quantities = summary["quantities_by_unit"]
        lines = [
            "REPORT RUN",
            f"run_id: {summary['run_id']}",
            f"esito: {self._STATUS_LABELS.get(summary['status'], summary['status'])}",
            f"iterazioni: {summary['iterations']}",
            f"durata: {summary['duration_s']:.3f}s",
            f"chiamate prezzate: {summary['usage_count']}",
            f"costo totale: ${summary['total_cost']:.8f}",
            f"costo per iterazione: ${self._cost_per_iteration(summary):.8f}",
            f"token: input={quantities.get('input_tokens', 0):g}, "
            f"cached={quantities.get('cached_input_tokens', 0):g}, "
            f"output={quantities.get('output_tokens', 0):g}",
        ]
        other_quantities = {
            unit: quantity for unit, quantity in quantities.items()
            if unit not in {"input_tokens", "cached_input_tokens", "output_tokens"}
        }
        if other_quantities:
            formatted = ", ".join(f"{unit}={quantity:g}" for unit, quantity in other_quantities.items())
            lines.append(f"altre quantita': {formatted}")
        if summary["unpriced_count"]:
            lines.append(f"usage non prezzabili: {summary['unpriced_count']}")

        budget_event = next(
            (event for event in reversed(events) if event["event_type"] == "budget_exhausted"),
            None,
        )
        if budget_event is not None:
            details = budget_event["details"]
            lines.append(
                "budget: "
                f"cap=${details['hard_limit_usd']:.8f}, "
                f"speso=${details['total_cost_usd']:.8f}, "
                f"sforamento=${details['overrun_usd']:.8f}"
            )
        lines.append(f"ledger: {ledger_path}")
        return "\n".join(lines)

    @staticmethod
    def _cost_per_iteration(summary: dict[str, Any]) -> float:
        """Evita la divisione per zero per errori prima della prima iterazione."""
        iterations = summary["iterations"]
        return summary["total_cost"] / iterations if iterations else 0.0
