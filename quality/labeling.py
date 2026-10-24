"""Mutanti etichettati dai test: dal codice giusto di un agente a esempi sbagliati con etichetta certa."""

import re
import shutil
import subprocess
import zlib
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path

from parallel_runner import run_parallel
from polyglot import Exercise, exercise_to_task
from quality.dataset import Example
from quality.mutants import generate_mutants
from task_model import as_verifier


@dataclass(frozen=True)
class LabelingResult:
    """L'esito dell'etichettatura.

    Attributes:
        examples: i mutanti, nello stesso ordine ricevuto; l'etichetta e' `None`
            solo per quelli la cui esecuzione e' fallita per un guasto dell'ambiente.
        timeouts: quanti mutanti hanno superato il tempo (si contano come test falliti).
        errors: i mutanti non etichettati, con il tipo dell'errore.
    """

    examples: list[Example]
    timeouts: int
    errors: list[tuple[str, str]]


def make_mutant_examples(agent_examples: Sequence[Example], exercises: Mapping[str, Exercise], *,
                         per_solution: int = 4, seed: int = 0) -> list[Example]:
    """I mutanti (senza etichetta) delle soluzioni corrette degli agenti.

    Si parte solo dalle soluzioni con etichetta 1: un mutante di una soluzione gia'
    sbagliata non direbbe di che cosa e' fatto l'errore. Le soluzioni a piu' file si
    saltano. Il campione di mutanti di ogni soluzione dipende dal seme e dalla run:
    stesso seme, stessi mutanti.
    """
    mutanti: list[Example] = []
    for esempio in agent_examples:
        esercizio = exercises.get(esempio.task_id)
        if (esempio.origin != "agente" or esempio.label != 1 or esercizio is None
                or len(esercizio.solution_files) != 1 or esempio.base_run_id is None):
            continue
        run_id = esempio.base_run_id
        campione = generate_mutants(esempio.solution, seed=seed + zlib.crc32(run_id.encode()),
                                    max_mutants=per_solution)
        for n, m in enumerate(campione):
            mutanti.append(Example(
                example_id=f"mutante:{run_id}:{n}", task_id=esempio.task_id, origin="mutante",
                instructions=esempio.instructions, solution=m.source, label=None,
                base_run_id=run_id, operator=m.operator, line=m.line))
    return mutanti


def label_mutants(mutants: Sequence[Example], exercises: Mapping[str, Exercise], *,
                  shell: Callable[[Path, str], int], workers: int,
                  workspace_root: Path) -> LabelingResult:
    """Esegue i test su ogni mutante nella sandbox e ne ricava l'etichetta.

    Per ogni mutante si crea una cartella con il **codice esatto** dell'esempio e i
    test originali dell'esercizio, si lancia il comando di verifica della campagna
    (`shell`) e la cartella si cancella. Exit code 0 = i test passano = etichetta 1.
    Un mutante che supera il tempo ha etichetta 0 (una soluzione che non finisce non
    e' corretta) e si conta a parte; un guasto dell'ambiente lascia il mutante senza
    etichetta e non ferma gli altri. Gli esempi che non sono mutanti da etichettare
    restano com'erano.

    Args:
        mutants: gli esempi, nell'ordine in cui si vogliono riavere.
        exercises: gli esercizi, per nome (test e comando di verifica).
        shell: come eseguire un comando in una cartella (la shell Docker della campagna).
        workers: quanti mutanti in parallelo (un container ciascuno).
        workspace_root: dove creare le cartelle temporanee.

    Raises:
        ValueError: se `workers` e' minore di uno.
    """
    da_fare = [(i, m) for i, m in enumerate(mutants) if m.origin == "mutante" and m.label is None]

    def lavora(voce: tuple[int, Example]) -> tuple[str, int | str]:
        _, mutante = voce
        esercizio = exercises[mutante.task_id]
        cartella = workspace_root / re.sub(r"[^A-Za-z0-9_.-]", "_", mutante.example_id)
        try:
            cartella.mkdir(parents=True, exist_ok=True)
            (cartella / next(iter(esercizio.solution_files))).write_text(mutante.solution)
            for nome, contenuto in esercizio.test_files.items():
                (cartella / nome).write_text(contenuto)
            verifica = as_verifier(exercise_to_task(esercizio).verify)(cartella, cartella, shell)
            return "etichetta", int(verifica.verified)
        except subprocess.TimeoutExpired:
            return "timeout", 0
        except Exception as errore:   # un guasto dell'ambiente non deve fermare gli altri
            return "errore", type(errore).__name__
        finally:
            shutil.rmtree(cartella, ignore_errors=True)

    esiti = run_parallel(da_fare, lavora, max_workers=workers)
    risultato = list(mutants)
    timeouts, errori = 0, []
    for esito in esiti:
        indice, mutante = esito.job
        genere, valore = esito.result if esito.result is not None else ("errore", type(esito.error).__name__)
        if genere == "errore":
            errori.append((mutante.example_id, str(valore)))
            continue
        timeouts += genere == "timeout"
        risultato[indice] = replace(mutante, label=int(valore))
    with suppress(OSError):
        workspace_root.rmdir()          # se e' vuota; altrimenti resta
    return LabelingResult(examples=risultato, timeouts=timeouts, errors=errori)
