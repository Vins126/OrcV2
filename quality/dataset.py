"""Il dataset di esempi (compito, soluzione, etichetta) per misurare gli stimatori."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from polyglot import Exercise
from quality.mutants import normalize


@dataclass(frozen=True)
class Example:
    """Un esempio da giudicare.

    Attributes:
        example_id: identificativo stabile (`agente:<run>` o `mutante:<run>:<n>`).
        task_id: l'esercizio: e' il blocco per gli intervalli di confidenza.
        origin: `agente` (soluzione vera di un agente) oppure `mutante`.
        instructions: le istruzioni dell'esercizio, in inglese. Mai i test.
        solution: il codice, in forma normalizzata (stessa forma per tutti gli esempi).
        label: 1 se i test passano, 0 se falliscono, `None` se non ancora eseguiti.
        base_run_id: la run dell'agente da cui viene (per i mutanti, la soluzione corretta).
        operator: il tipo di guasto, solo per i mutanti.
        line: la riga del guasto nel codice originale, solo per i mutanti.
    """

    example_id: str
    task_id: str
    origin: str
    instructions: str
    solution: str
    label: int | None
    base_run_id: str | None = None
    operator: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class Skipped:
    """Una run che non diventa un esempio, con il motivo: nessuna sparisce in silenzio."""

    run_id: str | None
    task_id: str
    reason: str


def solution_text(files: Mapping[str, str]) -> str:
    """Il codice di una soluzione, normalizzato; con piu' file, ognuno con la sua intestazione.

    Raises:
        ValueError: se un file non e' Python valido.
    """
    if len(files) == 1:
        return normalize(next(iter(files.values())))
    return "\n\n".join(f"# FILE: {nome}\n{normalize(files[nome])}" for nome in sorted(files))


#: Stati di una riga del manifesto che dicono un guasto della campagna, non del modello.
_GUASTI_DELLA_CAMPAGNA = ("build_failed", "setup_failed")


def build_agent_examples(manifest: Path, exercises: Mapping[str, Exercise]) -> tuple[list[Example], list[Skipped]]:
    """Un esempio per ogni run di un agente del manifesto della campagna.

    L'etichetta e' `success` della riga: incarico `completed` **e** verifica con
    exit 0. Il codice si legge dalla cartella di lavoro dell'agente, che e' quello
    che la verifica ha eseguito. Le righe che non sono run (l'ambiente, lo stop) si
    ignorano; una run che non diventa un esempio finisce fra gli scartati.

    Args:
        manifest: il file `.jsonl` della campagna.
        exercises: gli esercizi, per nome (servono le istruzioni e i nomi dei file).

    Returns:
        (esempi, scartati), nell'ordine del manifesto.
    """
    esempi: list[Example] = []
    scartati: list[Skipped] = []
    for linea in manifest.read_text().splitlines():
        riga = json.loads(linea) if linea.strip() else {}
        if not riga.get("task_id"):
            continue
        task_id, run_id = riga["task_id"], riga.get("run_id")

        def scarta(motivo: str) -> None:
            scartati.append(Skipped(run_id, task_id, motivo))

        if riga.get("status") in _GUASTI_DELLA_CAMPAGNA:
            scarta("guasto_della_campagna")
            continue
        esercizio = exercises.get(task_id)
        if esercizio is None:
            scarta("esercizio_sconosciuto")
            continue
        file_soluzione = {nome: Path(riga["workspace"]) / nome for nome in esercizio.solution_files}
        if not all(p.is_file() for p in file_soluzione.values()):
            scarta("soluzione_mancante")
            continue
        try:
            codice = solution_text({nome: p.read_text() for nome, p in file_soluzione.items()})
        except ValueError:
            scarta("non_valida")
            continue
        esempi.append(Example(
            example_id=f"agente:{run_id}", task_id=task_id, origin="agente",
            instructions=esercizio.instructions, solution=codice,
            label=1 if riga.get("success") else 0, base_run_id=run_id))
    return esempi, scartati


def write_examples(path: Path, examples: Iterable[Example]) -> None:
    """Scrive gli esempi in JSONL, uno per riga (crea la cartella se manca)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for e in examples:
            file.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")


def read_examples(path: Path) -> list[Example]:
    """Rilegge gli esempi scritti da `write_examples`."""
    return [Example(**json.loads(linea)) for linea in path.read_text(encoding="utf-8").splitlines() if linea.strip()]
