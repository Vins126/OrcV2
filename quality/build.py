"""Costruzione del dataset completo: soluzioni degli agenti, mutanti ed etichette dei test."""

import argparse
import json
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Sequence

from polyglot import Exercise, load_exercises
from quality.dataset import build_agent_examples, write_examples
from quality.labeling import label_mutants, make_mutant_examples


def build_dataset(manifest: Path, exercises: Mapping[str, Exercise], out_dir: Path, *,
                  per_solution: int, seed: int, workers: int,
                  shell: Callable[[Path, str], int], workspace_root: Path) -> dict[str, Any]:
    """Scrive `examples.jsonl` e `summary.json` in `out_dir` e restituisce il riepilogo.

    Il riepilogo dice quanti esempi ci sono per origine ed etichetta, quanti sono
    stati scartati e perche', quanti mutanti hanno superato il tempo, e i guasti
    dell'ambiente: i numeri che un lettore deve poter controllare prima di fidarsi
    delle misure.

    Raises:
        FileExistsError: se `out_dir` ha gia' un dataset (non si sovrascrive: i
            risultati dipendono da questo file).
    """
    destinazione = out_dir / "examples.jsonl"
    if destinazione.exists():
        raise FileExistsError(f"esiste gia' un dataset in {out_dir}: scegli un'altra cartella")
    agenti, scartati = build_agent_examples(manifest, exercises)
    mutanti = make_mutant_examples(agenti, exercises, per_solution=per_solution, seed=seed)
    esito = label_mutants(mutanti, exercises, shell=shell, workers=workers, workspace_root=workspace_root)
    tutti = [*agenti, *esito.examples]
    utilizzabili = [e for e in tutti if e.label is not None]
    write_examples(destinazione, utilizzabili)
    riepilogo: dict[str, Any] = {
        "manifest": str(manifest), "per_solution": per_solution, "seed": seed,
        "esempi": len(utilizzabili),
        "per_origine_ed_etichetta": {
            f"{o}:{'corretto' if l else 'sbagliato'}": n
            for (o, l), n in sorted(Counter((e.origin, e.label) for e in utilizzabili).items())},
        "esercizi": len({e.task_id for e in utilizzabili}),
        "mutanti_per_operatore": dict(sorted(Counter(
            e.operator for e in utilizzabili if e.origin == "mutante").items())),
        "scartati_dalle_run": dict(sorted(Counter(s.reason for s in scartati).items())),
        "mutanti_scaduti_di_tempo": esito.timeouts,
        "mutanti_senza_etichetta_per_guasto": [id_ for id_, _ in esito.errors],
    }
    (out_dir / "summary.json").write_text(json.dumps(riepilogo, indent=2, ensure_ascii=False), encoding="utf-8")
    return riepilogo


def main(argv: Sequence[str] | None = None) -> int:
    """Riga di comando: costruisce il dataset dalla campagna e dagli esercizi."""
    from campaign import shell_docker       # importato qui: tira dentro Docker e la campagna

    parser = argparse.ArgumentParser(description="Dataset per la misura degli stimatori (M2b.5)")
    parser.add_argument("--manifest", type=Path, required=True, help="manifesto `.jsonl` della campagna")
    parser.add_argument("--exercises", type=Path, default=Path("campaigns/data/polyglot-python"))
    parser.add_argument("--out", type=Path, required=True, help="cartella di uscita (es. runs/quality/d1)")
    parser.add_argument("--per-solution", type=int, default=4, help="mutanti per soluzione corretta")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1, help="mutanti etichettati in parallelo")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.per_solution < 1:
        print("errore: --workers e --per-solution devono essere almeno 1")
        return 2
    esercizi = {e.name: e for e in load_exercises(args.exercises)}
    try:
        riepilogo = build_dataset(
            args.manifest, esercizi, args.out, per_solution=args.per_solution, seed=args.seed,
            workers=args.workers, shell=shell_docker, workspace_root=Path("workspace") / "quality-mutanti")
    except FileExistsError as errore:
        print(f"errore: {errore}")
        return 2
    print(json.dumps(riepilogo, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
