"""Dal dataset e dai giudizi al rapporto: metriche per stimatore e verdetto secondo la regola di D21."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from quality.dataset import Example
from quality.evaluate import Judgment
from quality.metrics import ReliabilityBin, auroc, brier, cluster_bootstrap_ci, ece, reliability_table
from quality.protocol import Protocol


@dataclass(frozen=True)
class EstimatorReport:
    """Le misure di uno stimatore.

    Attributes:
        name: nome dello stimatore.
        n_examples: esempi del dataset.
        n_scored: esempi con almeno un giudizio valido (sono quelli su cui si misura).
        n_failed_judgments: giudizi senza risposta valida (contati, mai trattati come risposte).
        repetitions: ripetizioni massime viste per esempio.
        auroc: capacita' di ordinare giuste e sbagliate; `None` se manca una classe.
        auroc_low: limite inferiore dell'intervallo al 95% (blocchi: gli esercizi).
        auroc_high: limite superiore.
        brier: errore dei numeri.
        ece: errore di calibrazione grezzo (nessuna calibrazione applicata).
        reliability: la curva di affidabilita'.
        auroc_mutants: AUROC solo sui mutanti (descrittivo).
        auroc_agents: AUROC solo sulle soluzioni degli agenti (descrittivo: i negativi sono pochi).
        cost_usd: spesa totale dello stimatore.
        cost_per_1000: costo ogni 1000 giudizi.
        mean_latency_s: durata media di un giudizio.
        repeatability: scarto medio fra la piu' alta e la piu' bassa fra le ripetizioni
            dello stesso esempio; `None` con una sola ripetizione.
        auroc_origin_control: controllo **esplorativo** (D27), che non decide il verdetto.
            Fra le sole soluzioni corrette, AUROC degli originali degli agenti contro i mutanti
            equivalenti: 0,5 se lo stimatore non distingue l'origine, piu' alto se parte del
            segnale complessivo e' il riconoscimento del codice mutato e non della correttezza.
    """

    name: str
    n_examples: int
    n_scored: int
    n_failed_judgments: int
    repetitions: int
    auroc: float | None
    auroc_low: float | None
    auroc_high: float | None
    brier: float | None
    ece: float | None
    reliability: list[ReliabilityBin] = field(default_factory=list)
    auroc_mutants: float | None = None
    auroc_agents: float | None = None
    cost_usd: float = 0.0
    cost_per_1000: float = 0.0
    mean_latency_s: float = 0.0
    repeatability: float | None = None
    auroc_origin_control: float | None = None


@dataclass(frozen=True)
class Decision:
    """Il verdetto della regola di D21, con il motivo in parole."""

    verdict: str          # promettente | negativo | inconcludente | non_valutabile
    reason: str


@dataclass(frozen=True)
class Report:
    """Il rapporto completo."""

    dataset: dict[str, int]
    estimators: dict[str, EstimatorReport]
    decision: Decision


def decide(primary: EstimatorReport | None, reference: EstimatorReport | None,
           protocol: Protocol) -> Decision:
    """Applica la regola scritta prima dei risultati (D21).

    *Promettente*: limite inferiore dell'AUROC del primario >= `promising_lower_bound` e
    AUROC non oltre `max_gap_to_reference` sotto quello del riferimento.
    *Negativo*: limite superiore <= `negative_upper_bound` (anche nel caso migliore e'
    debole). Altrimenti *inconcludente*. Senza misure valide, *non valutabile*.

    Le due zone non si sovrappongono: se il limite inferiore e' alto, il superiore lo e' di piu'.
    """
    if (primary is None or primary.auroc is None or primary.auroc_low is None
            or primary.auroc_high is None):
        return Decision("non_valutabile", "mancano le misure valide dello stimatore primario")
    if primary.auroc_high <= protocol.negative_upper_bound:
        return Decision("negativo", (
            f"anche nel caso migliore l'AUROC ({primary.auroc_high:.2f}) non supera "
            f"{protocol.negative_upper_bound:.2f}"))
    if primary.auroc_low < protocol.promising_lower_bound:
        return Decision("inconcludente", (
            f"il limite inferiore dell'AUROC ({primary.auroc_low:.2f}) e' sotto "
            f"{protocol.promising_lower_bound:.2f}, ma il superiore ({primary.auroc_high:.2f}) "
            f"e' sopra {protocol.negative_upper_bound:.2f}"))
    if reference is None or reference.auroc is None:
        return Decision("non_valutabile", "manca il riferimento: non si puo' controllare lo scarto")
    scarto = round(reference.auroc - primary.auroc, 9)
    if scarto > protocol.max_gap_to_reference:
        return Decision("inconcludente", (
            f"il limite inferiore ({primary.auroc_low:.2f}) e' sufficiente, ma l'AUROC e' "
            f"{scarto:.2f} sotto il riferimento (massimo ammesso {protocol.max_gap_to_reference:.2f})"))
    return Decision("promettente", (
        f"limite inferiore {primary.auroc_low:.2f} >= {protocol.promising_lower_bound:.2f} e "
        f"scarto dal riferimento {max(scarto, 0.0):.2f} <= {protocol.max_gap_to_reference:.2f}"))


def _auroc_o_none(probabilita: list[float], etichette: list[int]) -> float | None:
    try:
        return auroc(probabilita, etichette)
    except ValueError:
        return None


def _report_stimatore(nome: str, esempi: Sequence[Example], tutte: list[Judgment],
                      ultime: list[Judgment], protocol: Protocol,
                      costo_totale: float | None = None) -> EstimatorReport:
    per_id = {e.example_id: e for e in esempi}
    valide: dict[str, list[float]] = {}
    for g in ultime:
        if g.probability is not None and g.example_id in per_id and per_id[g.example_id].label is not None:
            valide.setdefault(g.example_id, []).append(g.probability)
    ids = sorted(valide)
    medie = [sum(valide[i]) / len(valide[i]) for i in ids]
    etichette = [int(per_id[i].label or 0) for i in ids]
    blocchi = [per_id[i].task_id for i in ids]
    mutante = [per_id[i].origin == "mutante" for i in ids]

    punto = _auroc_o_none(medie, etichette)
    basso = alto = None
    if punto is not None:
        try:
            basso, alto, _ = cluster_bootstrap_ci(
                auroc, medie, etichette, blocchi, n_boot=protocol.bootstrap_samples, seed=protocol.seed)
        except ValueError:
            pass
    pm = [p for p, m in zip(medie, mutante) if m]
    em = [e for e, m in zip(etichette, mutante) if m]
    pa = [p for p, m in zip(medie, mutante) if not m]
    ea = [e for e, m in zip(etichette, mutante) if not m]
    # Controllo di origine: fra i soli corretti, originali degli agenti contro mutanti equivalenti.
    originali = [p for p, i in zip(medie, ids) if per_id[i].label == 1 and per_id[i].origin == "agente"]
    equivalenti = [p for p, i in zip(medie, ids) if per_id[i].label == 1 and per_id[i].origin == "mutante"]
    controllo = (_auroc_o_none(originali + equivalenti, [1] * len(originali) + [0] * len(equivalenti))
                 if originali and equivalenti else None)
    ripetizioni = max((g.rep for g in ultime), default=0)
    scarti = [max(v) - min(v) for v in valide.values() if len(v) >= 2]
    costo_misura = sum(g.cost_usd for g in tutte)
    # `costo_totale` e' tutto cio' che lo stimatore ha speso, anche fuori dal sottoinsieme e per giudizi rifatti
    costo = costo_totale if costo_totale is not None else costo_misura
    return EstimatorReport(
        name=nome, n_examples=len(esempi), n_scored=len(ids),
        n_failed_judgments=sum(g.probability is None for g in ultime), repetitions=ripetizioni,
        auroc=punto, auroc_low=basso, auroc_high=alto,
        brier=brier(medie, etichette) if ids else None, ece=ece(medie, etichette) if ids else None,
        reliability=reliability_table(medie, etichette) if ids else [],
        auroc_mutants=_auroc_o_none(pm, em) if pm else None,
        auroc_agents=_auroc_o_none(pa, ea) if pa else None,
        cost_usd=costo, cost_per_1000=costo_misura / len(ultime) * 1000 if ultime else 0.0,
        mean_latency_s=sum(g.latency_s for g in ultime) / len(ultime) if ultime else 0.0,
        repeatability=sum(scarti) / len(scarti) if scarti else None,
        auroc_origin_control=controllo)


def build_report(examples: Sequence[Example], judgments: Sequence[Judgment],
                 protocol: Protocol, *, only_examples: Collection[str] | None = None) -> Report:
    """Calcola le misure di ogni stimatore presente nei giudizi e applica la regola.

    Se lo stesso giudizio (esempio, stimatore, ripetizione) compare piu' volte, per
    le misure vale l'ultimo; per il **costo** contano tutti, perche' i soldi sono stati
    spesi comunque. Le misure si fanno sulla media delle ripetizioni valide di ogni esempio.
    """
    costi: dict[str, float] = {}
    for g in judgments:
        costi[g.estimator] = costi.get(g.estimator, 0.0) + g.cost_usd
    if only_examples is not None:
        ids = set(only_examples)
        examples = [e for e in examples if e.example_id in ids]
        if not examples:
            raise ValueError("il sottoinsieme non contiene nessun esempio del dataset")
        judgments = [g for g in judgments if g.example_id in ids]
    per_stimatore: dict[str, list[Judgment]] = {}
    for g in judgments:
        per_stimatore.setdefault(g.estimator, []).append(g)
    stimatori: dict[str, EstimatorReport] = {}
    for nome, tutte in per_stimatore.items():
        ultime = list({(g.example_id, g.rep): g for g in tutte}.values())      # l'ultimo vince
        stimatori[nome] = _report_stimatore(nome, examples, tutte, ultime, protocol, costi[nome])
    dataset = {
        "esempi": len(examples), "esercizi": len({e.task_id for e in examples}),
        "agenti_corretti": sum(e.origin == "agente" and e.label == 1 for e in examples),
        "agenti_sbagliati": sum(e.origin == "agente" and e.label == 0 for e in examples),
        "mutanti_corretti": sum(e.origin == "mutante" and e.label == 1 for e in examples),
        "mutanti_sbagliati": sum(e.origin == "mutante" and e.label == 0 for e in examples),
        "sottoinsieme": int(only_examples is not None),
    }
    return Report(dataset=dataset, estimators=stimatori,
                  decision=decide(stimatori.get(protocol.primary), stimatori.get(protocol.reference), protocol))


def _f(valore: float | None, cifre: int = 2) -> str:
    return "n/d" if valore is None else f"{valore:.{cifre}f}"


def render_markdown(report: Report, protocol: Protocol) -> str:
    """Il rapporto come tabella leggibile, in linguaggio neutro."""
    d = report.dataset
    righe = [
        "## Misura degli stimatori di qualita'",
        "",
        f"Esempi: {d['esempi']} in {d['esercizi']} esercizi. Soluzioni degli agenti: "
        f"{d['agenti_corretti']} corrette, {d['agenti_sbagliati']} sbagliate. Mutanti: "
        f"{d['mutanti_corretti']} corretti (equivalenti per i test), {d['mutanti_sbagliati']} sbagliati.",
        *([f"**Tutti gli stimatori sono misurati sugli stessi esempi: un sottoinsieme di {d['esempi']} esempi "
           f"(campione bilanciato, scelto con un seme fisso).** I costi riportati sono invece tutto cio' che e' stato speso.", ""]
          if d.get("sottoinsieme") else []),
        "",
        "| Stimatore | Giudicati | Falliti | AUROC [IC 95%] | Mutanti | Agenti | Brier | ECE (grezzo) "
        "| Costo / 1000 | Latenza media | Ripetibilita' | Origine (esplorativo) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report.estimators.values():
        intervallo = f"{_f(r.auroc)} [{_f(r.auroc_low)}, {_f(r.auroc_high)}]"
        righe.append(
            f"| {r.name} | {r.n_scored}/{r.n_examples} | {r.n_failed_judgments} | {intervallo} | "
            f"{_f(r.auroc_mutants)} | {_f(r.auroc_agents)} | {_f(r.brier, 3)} | {_f(r.ece, 3)} | "
            f"${r.cost_per_1000:.4f} | {r.mean_latency_s:.2f} s | {_f(r.repeatability, 3)} | "
            f"{_f(r.auroc_origin_control)} |")
    righe += [
        "",
        f"**Regola decisa prima dei risultati.** Stimatore primario `{protocol.primary}`, riferimento "
        f"`{protocol.reference}`. Promettente: limite inferiore dell'AUROC >= {protocol.promising_lower_bound:.2f} "
        f"e AUROC non oltre {protocol.max_gap_to_reference:.2f} sotto il riferimento. Negativo: limite "
        f"superiore <= {protocol.negative_upper_bound:.2f}.",
        "",
        f"**Verdetto: {report.decision.verdict}.** {report.decision.reason}.",
        "",
        "Note: gli intervalli ricampionano gli esercizi interi; ECE e Brier sono grezzi (nessuna calibrazione); "
        "le colonne Mutanti e Agenti sono descrittive (i negativi fra gli agenti sono pochi). La colonna "
        "Origine e' un controllo esplorativo che non decide il verdetto: fra le sole soluzioni corrette, AUROC "
        "degli originali degli agenti contro i mutanti equivalenti (0,50 = lo stimatore non distingue l'origine; "
        "piu' alto = parte del segnale complessivo e' il riconoscimento del codice mutato).",
    ]
    return "\n".join(righe) + "\n"
