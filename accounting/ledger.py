"""Ledger persistente dei fatti osservati durante una singola run.

Il ledger non calcola prezzi e non invoca provider: riceve record gia'
contabilizzati ed eventi gia' accaduti, li conserva in JSONL e al termine
deriva un riepilogo leggibile dalla stessa fonte di verita'.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from accounting.record import UsageRecord


class RunLedger:
    """Archivio append-only associato a una singola esecuzione dell'agente.

    Ogni run possiede una directory autonoma: questo rende le misure facilmente
    confrontabili ed evita che due esecuzioni mescolino chiamate o costi.
    """

    # La v2 separa i provider API e billing nei UsageRecord e aggiunge i
    # breakdown per modello/durata nel summary. I ledger v1 restano immutati.
    SCHEMA_VERSION = 2

    def __init__(
        self,
        *,
        root: Path,
        task: str,
        run_id: str | None = None,
        agent_id: str | None = None,
        role: str | None = None,
    ):
        self.run_id = run_id or uuid4().hex
        self.run_dir = Path(root) / self.run_id
        self.task_hash = sha256(task.encode("utf-8")).hexdigest()
        self.agent_id = agent_id
        self.role = role
        self.started_at = self._now()
        self._usage_sequence = 0
        self._event_sequence = 0

        # Non riusare mai una directory esistente: farlo mescolerebbe i dati di
        # due run e renderebbe il summary non piu' riproducibile.
        self.run_dir.mkdir(parents=True, exist_ok=False)

    def append_usage(self, record: UsageRecord) -> None:
        """Aggiunge un consumo gia' prezzato al ledger della run."""
        self._usage_sequence += 1
        self._append_jsonl(
            self.run_dir / "usage.jsonl",
            {
                "schema_version": self.SCHEMA_VERSION,
                "event_type": "usage",
                "run_id": self.run_id,
                "sequence": self._usage_sequence,
                "record": asdict(record),
            },
        )

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Aggiunge un evento che non rappresenta un consumo prezzato."""
        self._event_sequence += 1
        self._append_jsonl(
            self.run_dir / "events.jsonl",
            {
                "schema_version": self.SCHEMA_VERSION,
                "event_type": event_type,
                "run_id": self.run_id,
                "sequence": self._event_sequence,
                "details": details,
            },
        )

    def read_events(self) -> list[dict[str, Any]]:
        """Restituisce gli eventi append-only della run per report e analisi."""
        return self._read_jsonl(self.run_dir / "events.jsonl")

    def close(self, *, status: str, iterations: int) -> dict[str, Any]:
        """Deriva e persiste il riepilogo finale della run.

        Il summary viene calcolato rileggendo i JSONL: non esiste un contatore
        parallelo da mantenere coerente con i file append-only.
        """
        usage_entries = self._read_jsonl(self.run_dir / "usage.jsonl")
        events = self._read_jsonl(self.run_dir / "events.jsonl")

        cost_by_model: dict[str, float] = {}
        cost_by_operation: dict[str, float] = {}
        quantities_by_unit: dict[str, float] = {}
        total_cost = 0.0
        for entry in usage_entries:
            record = entry["record"]
            cost = float(record["cost"])
            model = record["model"]
            operation = record["operation"]
            total_cost += cost
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost
            cost_by_operation[operation] = cost_by_operation.get(operation, 0.0) + cost
            for unit, quantity in record["quantities"].items():
                quantities_by_unit[unit] = quantities_by_unit.get(unit, 0.0) + float(quantity)

        finished_at = self._now()
        duration_s = (
            datetime.fromisoformat(finished_at) - datetime.fromisoformat(self.started_at)
        ).total_seconds()
        summary = {
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_hash": self.task_hash,
            "agent_id": self.agent_id,
            "role": self.role,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_s": round(duration_s, 6),
            "status": status,
            "iterations": iterations,
            "usage_count": len(usage_entries),
            "event_count": len(events),
            "unpriced_count": sum(
                event["event_type"] == "unpriced_usage" for event in events
            ),
            "total_cost": round(total_cost, 12),
            "cost_by_model": {
                model: round(cost, 12)
                for model, cost in cost_by_model.items()
            },
            "cost_by_operation": {
                operation: round(cost, 12)
                for operation, cost in cost_by_operation.items()
            },
            "quantities_by_unit": quantities_by_unit,
        }
        self._write_summary_atomically(summary)
        return summary

    @staticmethod
    def _now() -> str:
        """Restituisce l'istante corrente in formato ISO 8601 UTC."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        """Legge un JSONL assente come un ledger vuoto."""
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]

    @staticmethod
    def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
        """Scrive una riga completa e forza il flush del suo contenuto."""
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def _write_summary_atomically(self, summary: dict[str, Any]) -> None:
        """Sostituisce il summary solo dopo averlo scritto per intero."""
        temporary_path = self.run_dir / ".summary.json.tmp"
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(summary, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(self.run_dir / "summary.json")
