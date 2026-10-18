"""Riga di comando dell'esperimento: `evaluate` fa girare gli stimatori, `report` scrive la tabella."""

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from quality.cascade import CostModel, analyze, cases_from, render_cascade_markdown
from quality.dataset import read_examples
from quality.evaluate import EvaluationSummary, read_judgments, run_evaluation
from quality.factory import ORDINE, build_estimators, frontier_gateway_maker
from quality.protocol import load_protocol
from quality.report import build_report, render_markdown
from quality.sample import stratified_sample

#: Costo medio OSSERVATO di un giudizio frontier (17 giudizi, 14 ott 2026): $0,0207, con un minimo
#: di $0,007 e un massimo di $0,040. La stima iniziale (0,007, ricavata dai token) era sbagliata: il modello
#: ragiona (output medio implicito ~640 token) e la richiesta scrive in cache. Serve al preventivo.
COSTO_STIMATO_FRONTIER_USD = 0.0207


def _scrivi_rapporto(dataset: Path, results: Path, protocol_path: Path, out: Path,
                     subset_ids: list[str] | None = None) -> str:
    protocollo = load_protocol(protocol_path)
    rapporto = build_report(read_examples(dataset / "examples.jsonl"), read_judgments(results), protocollo,
                            only_examples=subset_ids)
    testo = render_markdown(rapporto, protocollo)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(testo, encoding="utf-8")
    (out / "report.json").write_text(json.dumps(dataclasses.asdict(rapporto), indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    return testo


def _cascade(args: argparse.Namespace) -> int:
    esempi = read_examples(args.dataset / "examples.jsonl")
    giudizi = read_judgments(args.out / "results.jsonl")
    percorso = args.subset or (args.out / "sample.json")
    ids = json.loads(percorso.read_text())["example_ids"] if percorso.exists() else None
    casi = cases_from(esempi, giudizi, args.cheap, args.strong, ids)
    if not casi:
        print("errore: nessun esempio giudicato da entrambi gli stimatori", file=sys.stderr)
        return 2
    ammessi = {c.example_id for c in casi}
    valide = [g for g in giudizi if g.example_id in ammessi and g.probability is not None]

    def per_chiamata(nome: str, campo: str) -> float:
        righe = [getattr(g, campo) for g in valide if g.estimator == nome]
        return sum(righe) / len(righe)

    n = len(casi)
    costi = CostModel(
        cheap_usd=sum(g.cost_usd for g in valide if g.estimator == args.cheap) / n,   # tutte le ripetizioni
        strong_usd=sum(g.cost_usd for g in valide if g.estimator == args.strong) / n,
        cheap_latency_s=per_chiamata(args.cheap, "latency_s"), strong_latency_s=per_chiamata(args.strong, "latency_s"))
    righe = analyze(casi, costi, seed=args.seed, tolerances=(0.0, args.tolerance, 0.05))
    testo = render_cascade_markdown(righe, args.tolerance)
    (args.out / "cascade.md").write_text(testo, encoding="utf-8")
    (args.out / "cascade.json").write_text(json.dumps(
        [dataclasses.asdict(r) for r in righe], indent=2, ensure_ascii=False), encoding="utf-8")
    print(testo)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Esperimento M2b.5: stimatori di qualita'")
    sotto = parser.add_subparsers(dest="comando", required=True)
    ev = sotto.add_parser("evaluate", help="fa girare gli stimatori sul dataset")
    ev.add_argument("--dataset", type=Path, required=True, help="cartella con examples.jsonl")
    ev.add_argument("--protocol", type=Path, default=Path("quality/protocol.toml"))
    ev.add_argument("--out", type=Path, required=True, help="cartella dei risultati (results.jsonl)")
    ev.add_argument("--only", default="heuristic,d1_local_plain,d1_local_criteria,d1_hosted_plain,d1_hosted_criteria",
                    help="stimatori separati da virgola; il giudice `frontier` costa e va chiesto di proposito")
    ev.add_argument("--sample", type=int, default=None,
                    help="giudica solo un campione bilanciato di N esempi (scelto con --sample-seed)")
    ev.add_argument("--sample-seed", type=int, default=0)
    ev.add_argument("--max-total-usd", type=float, default=None,
                    help="tetto di spesa dell'esperimento (conta anche cio' che e' gia' nel file); "
                         "prevale su quello del protocollo, che non cambia")
    ev.add_argument("--yes", action="store_true", help="conferma la spesa mostrata nel preventivo (frontier)")
    ev.add_argument("--env-file", type=Path, default=Path(".env"),
                    help="file con le chiavi; si legge solo se serve (d1 ospitato o frontier)")
    rp = sotto.add_parser("report", help="calcola metriche e verdetto")
    rp.add_argument("--dataset", type=Path, required=True)
    rp.add_argument("--protocol", type=Path, default=Path("quality/protocol.toml"))
    rp.add_argument("--out", type=Path, required=True)
    rp.add_argument("--subset", type=Path, default=None,
                    help="`sample.json`: misura tutti gli stimatori sugli stessi esempi del campione")
    ca = sotto.add_parser("cascade", help="analisi esplorativa: economico per i casi sicuri, costoso per i dubbi")
    ca.add_argument("--dataset", type=Path, required=True)
    ca.add_argument("--out", type=Path, required=True, help="cartella con results.jsonl (e dove scrivere cascade.md)")
    ca.add_argument("--subset", type=Path, default=None, help="`sample.json`; predefinito: out/sample.json se c'e'")
    ca.add_argument("--cheap", default="d1_hosted_plain")
    ca.add_argument("--strong", default="frontier")
    ca.add_argument("--seed", type=int, default=0)
    ca.add_argument("--tolerance", type=float, default=0.02, help="la tolleranza fissata prima (le altre sono sensibilita')")
    args = parser.parse_args(argv)

    if args.comando == "cascade":
        return _cascade(args)

    if args.comando == "report":
        ids = json.loads(args.subset.read_text())["example_ids"] if args.subset else None
        print(_scrivi_rapporto(args.dataset, args.out / "results.jsonl", args.protocol, args.out, ids))
        return 0

    try:
        protocollo = load_protocol(args.protocol)
    except ValueError as errore:
        print(f"errore nel protocollo: {errore}", file=sys.stderr)
        return 2
    nomi = [n.strip() for n in args.only.split(",") if n.strip()]
    esempi = read_examples(args.dataset / "examples.jsonl")
    sample_ids: list[str] | None = None
    if args.sample:
        esempi = stratified_sample(esempi, args.sample, args.sample_seed)
        sample_ids = [e.example_id for e in esempi]
        percorso_campione = args.out / "sample.json"
        if percorso_campione.exists() and json.loads(percorso_campione.read_text())["example_ids"] != sample_ids:
            print("errore: in questa cartella c'e' gia' un campione diverso", file=sys.stderr)
            return 2
        args.out.mkdir(parents=True, exist_ok=True)
        percorso_campione.write_text(json.dumps(
            {"n": args.sample, "seed": args.sample_seed, "example_ids": sample_ids}, indent=1))
    tetto = args.max_total_usd if args.max_total_usd is not None else protocollo.max_total_usd
    ripetizioni = {n: (protocollo.repetitions_frontier if n == "frontier"
                       else 1 if n == "heuristic" else protocollo.repetitions_d1) for n in nomi}
    if "frontier" in nomi:
        giudizi = len(esempi) * ripetizioni["frontier"]
        stima = giudizi * COSTO_STIMATO_FRONTIER_USD
        print(f"PREVENTIVO frontier ({protocollo.frontier_model}): {giudizi} giudizi x "
              f"${COSTO_STIMATO_FRONTIER_USD} = circa ${stima:.2f} CALCOLATI (non misurati); "
              f"costo medio OSSERVATO su 17 giudizi (varia da $0.007 a $0.040); "
              f"tetto dell'esecuzione ${tetto:.2f}, che conta anche cio' che e' gia' stato speso")
        if not args.yes:
            print("Non lancio senza --yes: la spesa va approvata.", file=sys.stderr)
            return 2
    # Il `.env` si legge solo se un stimatore ha bisogno di una chiave: l'euristica e il d1
    # locale girano senza, e una prova non deve poter pescare le chiavi vere per sbaglio.
    if any(n.startswith("d1_hosted") or n == "frontier" for n in nomi):
        import config
        config.load_environment(args.env_file)
    frontier_maker = None
    if "frontier" in nomi:
        from accounting import ModelRegistry
        from agent_factory import AgentFactory
        fabbrica = AgentFactory(ModelRegistry.from_file(Path("models.toml")), runs_root=args.out / "runs",
                                workspaces_root=args.out / "workspaces", budget_usd=None,
                                tools_builder=lambda percorso, **_: [])
        frontier_maker = frontier_gateway_maker(fabbrica, protocollo.frontier_model)
    try:
        stimatori = build_estimators(protocollo, nomi, liquid_key=os.environ.get("LIQUID_API_KEY"),
                                     make_frontier_gateway=frontier_maker)
    except ValueError as errore:
        print(f"errore: {errore}", file=sys.stderr)
        return 2
    esito = run_evaluation(
        esempi, stimatori, {n: ripetizioni[n] for n in stimatori}, args.out / "results.jsonl",
        workers=protocollo.workers, max_total_usd=tetto,
        reserve_per_call_usd=protocollo.reserve_per_call_usd,
        on_progress=lambda n, fatti, tot: print(f"  {n}: {fatti}/{tot}") if fatti % 50 == 0 else None)
    print(json.dumps(dataclasses.asdict(esito), indent=2))
    print(_scrivi_rapporto(args.dataset, args.out / "results.jsonl", args.protocol, args.out, sample_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
