"""Esecuzione degli stimatori sul dataset: ogni giudizio su una riga, riprendibile, con tetto di spesa."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from budget_guard import BudgetExceeded
from parallel_runner import Admission, JobOutcome, run_parallel
from quality.dataset import Example
from quality.estimators import Estimate, Estimator


@dataclass(frozen=True)
class Judgment:
    """Un giudizio: lo stimatore, l'esempio, la ripetizione e cosa e' venuto fuori."""

    example_id: str
    estimator: str
    rep: int
    probability: float | None
    error: str | None
    cost_usd: float
    latency_s: float
    input_tokens: int | None


@dataclass(frozen=True)
class EvaluationSummary:
    """Cosa e' successo in questa esecuzione.

    Attributes:
        calls: giudizi nuovi per stimatore.
        errors: di questi, quanti senza risposta valida.
        skipped_done: giudizi gia' presenti (ripresa), non rifatti.
        cost_usd: spesa totale dell'esperimento, compresa quella delle esecuzioni precedenti.
        stopped_by_budget: vero se il tetto ha fermato dei giudizi.
    """

    calls: dict[str, int]
    errors: dict[str, int]
    skipped_done: int
    cost_usd: float
    stopped_by_budget: bool


def read_judgments(path: Path) -> list[Judgment]:
    """Rilegge i giudizi scritti da `run_evaluation` (vuoto se il file non c'e')."""
    if not path.exists():
        return []
    return [Judgment(**json.loads(riga)) for riga in path.read_text(encoding="utf-8").splitlines()
            if riga.strip()]


def run_evaluation(examples: Sequence[Example], estimators: Mapping[str, Estimator],
                   repetitions: Mapping[str, int], results_path: Path, *, workers: int,
                   max_total_usd: float | None = None, reserve_per_call_usd: float = 0.0,
                   on_progress: Callable[[str, int, int], None] | None = None) -> EvaluationSummary:
    """Fa girare ogni stimatore su ogni esempio per il numero di ripetizioni dato.

    Ogni giudizio si scrive appena arriva, dal thread principale. Rilanciando, i
    giudizi gia' fatti con una risposta valida non si rifanno (e non si ripagano);
    quelli senza risposta valida si riprovano, e in lettura vale l'ultimo. Il tetto di
    spesa vale per **tutto l'esperimento**: conta anche cio' che e' gia' nel file, e,
    come nella campagna, ogni giudizio in volo si prenota a `reserve_per_call_usd`.
    Gli stimatori vanno nell'ordine dato: i gratuiti per primi, cosi' il tetto non li
    affama. Uno stimatore che solleva `BudgetExceeded` ferma tutti i giudizi seguenti.

    Args:
        examples: gli esempi da giudicare.
        estimators: gli stimatori, per nome, nell'ordine di esecuzione.
        repetitions: quante volte giudicare ogni esempio, per stimatore.
        results_path: il file `.jsonl` dei giudizi.
        workers: giudizi in parallelo per ogni stimatore.
        max_total_usd: tetto di spesa dell'esperimento; `None` = nessuno.
        reserve_per_call_usd: prenotazione per ogni giudizio in volo.
        on_progress: chiamata (dal thread principale) con stimatore, fatti e totale.

    Raises:
        ValueError: se `workers` e' minore di uno.
    """
    if workers < 1:
        raise ValueError(f"workers deve essere almeno 1, non {workers}")
    precedenti = read_judgments(results_path)
    stato = {"spent": sum(g.cost_usd for g in precedenti), "stop": False}
    fatti = {(g.example_id, g.estimator, g.rep) for g in precedenti if g.probability is not None}
    calls: dict[str, int] = {}
    errors: dict[str, int] = {}
    saltati = 0
    fermato = False
    results_path.parent.mkdir(parents=True, exist_ok=True)

    with results_path.open("a", encoding="utf-8") as uscita:
        for nome, stimatore in estimators.items():
            tutti = [(e, r) for r in range(1, repetitions[nome] + 1) for e in examples]
            da_fare = [(e, r) for e, r in tutti if (e.example_id, nome, r) not in fatti]
            saltati += len(tutti) - len(da_fare)
            calls[nome], errors[nome] = 0, 0

            def admit(_job: tuple[Example, int], in_volo: int) -> Admission:
                if stato["stop"]:
                    return Admission.STOP
                if max_total_usd is None:
                    return Admission.START
                if stato["spent"] >= max_total_usd:
                    return Admission.STOP
                if stato["spent"] + in_volo * reserve_per_call_usd >= max_total_usd:
                    return Admission.WAIT
                return Admission.START

            def on_done(esito: JobOutcome[tuple[Example, int], Estimate], nome: str = nome) -> None:
                esempio, rep = esito.job
                if isinstance(esito.error, BudgetExceeded):
                    stato["stop"] = True            # ordine di fermarsi: il giudizio non c'e'
                    return
                stima = esito.result if esito.error is None and esito.result is not None else Estimate(
                    probability=None, error=type(esito.error).__name__)
                giudizio = Judgment(
                    example_id=esempio.example_id, estimator=nome, rep=rep,
                    probability=stima.probability, error=stima.error, cost_usd=stima.cost_usd,
                    latency_s=stima.latency_s, input_tokens=stima.input_tokens)
                uscita.write(json.dumps(asdict(giudizio), ensure_ascii=False) + "\n")
                uscita.flush()
                stato["spent"] += stima.cost_usd
                calls[nome] += 1
                errors[nome] += stima.probability is None
                if on_progress is not None:
                    on_progress(nome, calls[nome], len(da_fare))

            esiti = run_parallel(da_fare, lambda job, s=stimatore: s.estimate(job[0]),
                                 max_workers=workers, admit=admit, on_done=on_done)
            fermato = fermato or any(not e.started for e in esiti) or stato["stop"]

    return EvaluationSummary(calls=calls, errors=errors, skipped_done=saltati,
                             cost_usd=stato["spent"], stopped_by_budget=fermato)
