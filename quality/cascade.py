"""Cascata di giudici: uno stimatore economico decide i casi sicuri, quello costoso i dubbi.

Analisi esplorativa fatta sui dati dell'esperimento M2b.5 (via libera esplicito di Vincenzo,
fuori dalla regola di arresto). Nessuna chiamata a pagamento: usa i giudizi gia' raccolti.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from quality.dataset import Example
from quality.evaluate import Judgment


@dataclass(frozen=True)
class Case:
    """Un esempio con il punteggio dello stimatore economico e di quello costoso.

    Attributes:
        example_id: l'esempio.
        task_id: l'esercizio (blocco per la validazione).
        label: 1 se la soluzione e' corretta, 0 se sbagliata.
        cheap: punteggio dello stimatore economico (media delle ripetizioni valide).
        strong: punteggio dello stimatore costoso.
    """

    example_id: str
    task_id: str
    label: int
    cheap: float
    strong: float


@dataclass(frozen=True)
class Outcome:
    """Cosa fa una politica su un insieme di casi.

    Attributes:
        n: casi.
        escalated: frazione passata allo stimatore costoso.
        false_accept: quota di soluzioni sbagliate accettate (l'errore pericoloso); `None` se non ce ne sono.
        false_reject: quota di soluzioni corrette scartate; `None` se non ce ne sono.
        balanced_error: media dei due errori (le classi pesano uguale).
        accuracy: quota di decisioni giuste.
    """

    n: int
    escalated: float
    false_accept: float | None
    false_reject: float | None
    balanced_error: float
    accuracy: float


@dataclass(frozen=True)
class Thresholds:
    """Sotto `low` (compreso) si rifiuta, da `high` (compreso) in su si accetta, in mezzo si passa al costoso."""

    low: float
    high: float


#: Tutte le soglie: con `low=-1` e `high=2` si passa sempre al costoso.
ALWAYS_ESCALATE = Thresholds(-1.0, 2.0)


@dataclass(frozen=True)
class CvResult:
    """L'esito della validazione per blocchi di esercizi.

    Attributes:
        cascade: la cascata, con soglie scelte sui blocchi di addestramento e valutata su quelli esclusi.
        strong_alone: lo stimatore costoso da solo.
        cheap_alone: lo stimatore economico da solo, con la sua soglia migliore scelta allo stesso modo.
        thresholds_per_fold: le soglie scelte in ogni blocco (per vedere se sono stabili).
        folds: quanti blocchi.
    """

    cascade: Outcome
    strong_alone: Outcome
    cheap_alone: Outcome
    thresholds_per_fold: list[Thresholds] = field(default_factory=list)
    folds: int = 0


def cases_from(examples: Sequence[Example], judgments: Sequence[Judgment], cheap: str, strong: str,
               only_examples: Sequence[str] | None = None) -> list[Case]:
    """I casi per cui **entrambi** gli stimatori hanno almeno un giudizio valido (media delle ripetizioni)."""
    medie: dict[str, dict[str, list[float]]] = {cheap: {}, strong: {}}
    for g in judgments:
        if g.estimator in medie and g.probability is not None:
            medie[g.estimator].setdefault(g.example_id, []).append(g.probability)
    ammessi = set(only_examples) if only_examples is not None else None
    casi = []
    for e in examples:
        if e.label is None or (ammessi is not None and e.example_id not in ammessi):
            continue
        if e.example_id in medie[cheap] and e.example_id in medie[strong]:
            casi.append(Case(
                e.example_id, e.task_id, e.label,
                sum(medie[cheap][e.example_id]) / len(medie[cheap][e.example_id]),
                sum(medie[strong][e.example_id]) / len(medie[strong][e.example_id])))
    return casi


def _decide(caso: Case, soglie: Thresholds, soglia_costoso: float) -> tuple[bool, int]:
    """(passato al costoso?, accettato?): sotto `low` si rifiuta, da `high` in su si accetta, in mezzo si chiede."""
    if caso.cheap <= soglie.low:
        return False, 0
    if caso.cheap >= soglie.high:
        return False, 1
    return True, int(caso.strong >= soglia_costoso)


def _esito(casi: Sequence[Case], decisioni: Sequence[tuple[bool, int]]) -> Outcome:
    if not casi:
        raise ValueError("nessun caso da valutare")
    sbagliati = [d for c, d in zip(casi, decisioni) if c.label == 0]
    corretti = [d for c, d in zip(casi, decisioni) if c.label == 1]
    fa = sum(a for _, a in sbagliati) / len(sbagliati) if sbagliati else None
    fr = sum(1 - a for _, a in corretti) / len(corretti) if corretti else None
    errori = [x for x in (fa, fr) if x is not None]
    return Outcome(
        n=len(casi), escalated=sum(e for e, _ in decisioni) / len(casi),
        false_accept=fa, false_reject=fr, balanced_error=sum(errori) / len(errori),
        accuracy=sum(a == c.label for c, (_, a) in zip(casi, decisioni)) / len(casi))


def evaluate_policy(cases: Sequence[Case], thresholds: Thresholds, strong_threshold: float = 0.5) -> Outcome:
    """Applica la politica a cascata ai casi e misura le decisioni.

    Raises:
        ValueError: se non ci sono casi.
    """
    return _esito(cases, [_decide(c, thresholds, strong_threshold) for c in cases])


def sweep(cases: Sequence[Case], grid: Sequence[float], strong_threshold: float = 0.5) -> list[tuple[Thresholds, Outcome]]:
    """Tutte le coppie di soglie `low <= high` della griglia, con il loro esito (descrittivo, non selezione)."""
    punti = sorted(grid)
    return [(Thresholds(lo, hi), evaluate_policy(cases, Thresholds(lo, hi), strong_threshold))
            for i, lo in enumerate(punti) for hi in punti[i:]]


def _sceglie_soglie(train: Sequence[Case], griglia: Sequence[float], tolleranza: float,
                    soglia_costoso: float) -> Thresholds:
    """Le soglie con meno richieste al costoso fra quelle che non peggiorano l'errore piu' della tolleranza."""
    limite = evaluate_policy(train, ALWAYS_ESCALATE, soglia_costoso).balanced_error + tolleranza + 1e-12
    candidati = [(o.escalated, o.balanced_error, t.low, t.high, t)
                 for t, o in sweep(train, griglia, soglia_costoso) if o.balanced_error <= limite]
    if not candidati:
        return ALWAYS_ESCALATE
    migliore = min(candidati, key=lambda c: c[:4])
    return ALWAYS_ESCALATE if migliore[0] >= 1.0 - 1e-12 else migliore[4]


def cross_validate(cases: Sequence[Case], *, folds: int = 5, seed: int = 0, tolerance: float = 0.02,
                   grid: Sequence[float] | None = None, strong_threshold: float = 0.5) -> CvResult:
    """Sceglie le soglie sui blocchi di addestramento e le valuta su quelli esclusi, per esercizi interi.

    Gli esercizi si dividono in `folds` blocchi (mescolati con il seme). Per ogni blocco le
    soglie si scelgono **sugli altri**: meno richieste al costoso possibile, purche' l'errore
    bilanciato non superi quello del costoso da solo di piu' di `tolerance`. Si valutano sul
    blocco escluso, e le decisioni di tutti i blocchi si raccolgono: ogni caso e' giudicato
    una volta, con soglie che non l'hanno mai visto. Lo stesso vale per lo stimatore
    economico da solo, con la sua soglia migliore.

    Raises:
        ValueError: se i blocchi sono meno di 2 o piu' degli esercizi.
    """
    if folds < 2:
        raise ValueError(f"servono almeno 2 blocchi, non {folds}")
    esercizi = sorted({c.task_id for c in cases})
    if folds > len(esercizi):
        raise ValueError(f"{folds} blocchi ma solo {len(esercizi)} esercizi")
    griglia = sorted(grid) if grid is not None else [i / 20 for i in range(21)]
    ordine = esercizi[:]
    random.Random(seed).shuffle(ordine)
    blocco = {t: i % folds for i, t in enumerate(ordine)}
    decisioni_cascata: dict[str, tuple[bool, int]] = {}
    decisioni_economico: dict[str, tuple[bool, int]] = {}
    soglie_per_blocco: list[Thresholds] = []
    for k in range(folds):
        train = [c for c in cases if blocco[c.task_id] != k]
        test = [c for c in cases if blocco[c.task_id] == k]
        soglie = _sceglie_soglie(train, griglia, tolerance, strong_threshold)
        soglie_per_blocco.append(soglie)
        migliore_t = min(griglia, key=lambda t: (evaluate_policy(train, Thresholds(t, t), strong_threshold)
                                                 .balanced_error, t))
        for c in test:
            decisioni_cascata[c.example_id] = _decide(c, soglie, strong_threshold)
            decisioni_economico[c.example_id] = _decide(c, Thresholds(migliore_t, migliore_t), strong_threshold)
    return CvResult(
        cascade=_esito(cases, [decisioni_cascata[c.example_id] for c in cases]),
        strong_alone=evaluate_policy(cases, ALWAYS_ESCALATE, strong_threshold),
        cheap_alone=_esito(cases, [decisioni_economico[c.example_id] for c in cases]),
        thresholds_per_fold=soglie_per_blocco, folds=folds)


@dataclass(frozen=True)
class CostModel:
    """Costo e durata di un giudizio, per esempio (nell'economico, tutte le ripetizioni)."""

    cheap_usd: float
    strong_usd: float
    cheap_latency_s: float
    strong_latency_s: float


@dataclass(frozen=True)
class Row:
    """Una riga del confronto: una politica, le sue decisioni in numeri e il suo costo."""

    name: str
    outcome: Outcome
    cost_usd: float
    latency_s: float
    n_wrong: int
    n_correct: int
    false_accepts: int | None
    false_rejects: int | None


def analyze(cases: Sequence[Case], costs: CostModel, *, seed: int = 0,
            tolerances: Sequence[float] = (0.02,), grid: Sequence[float] | None = None,
            folds: int = 5) -> list[Row]:
    """Il costoso da solo, l'economico da solo e una cascata per ogni tolleranza, tutti validati."""
    n_wrong = sum(c.label == 0 for c in cases)
    n_correct = len(cases) - n_wrong

    def riga(nome: str, esito: Outcome, costo: float, latenza: float) -> Row:
        return Row(nome, esito, costo, latenza, n_wrong, n_correct,
                   None if esito.false_accept is None else round(esito.false_accept * n_wrong),
                   None if esito.false_reject is None else round(esito.false_reject * n_correct))

    risultati = [(t, cross_validate(cases, folds=folds, seed=seed, tolerance=t, grid=grid)) for t in tolerances]
    primo = risultati[0][1]
    righe = [
        riga("costoso da solo", primo.strong_alone, costs.strong_usd, costs.strong_latency_s),
        riga("economico da solo", primo.cheap_alone, costs.cheap_usd, costs.cheap_latency_s),
    ]
    for t, cv in risultati:
        esc = cv.cascade.escalated
        righe.append(riga(f"cascata (tolleranza {t:.2f})", cv.cascade,
                          costs.cheap_usd + esc * costs.strong_usd,
                          costs.cheap_latency_s + esc * costs.strong_latency_s))
    return righe


def render_cascade_markdown(rows: Sequence[Row], preregistered_tolerance: float) -> str:
    """La tabella del confronto, con i conteggi e l'avvertenza sulla tolleranza fissata prima."""
    n_wrong, n_correct = rows[0].n_wrong, rows[0].n_correct

    def conta(x: int | None, tot: int) -> str:
        return "n/d" if x is None else f"{x}/{tot}"

    righe = [
        "## Cascata di giudici: l'economico decide i casi sicuri, il costoso i dubbi",
        "",
        f"Esempi: {n_wrong + n_correct} ({n_wrong} sbagliati, {n_correct} corretti). Le soglie si scelgono sui "
        "blocchi di addestramento (esercizi interi) e si valutano su quelli esclusi: ogni esempio e' giudicato "
        "con soglie che non l'hanno mai visto.",
        "",
        "| Politica | Richieste al costoso | Sbagliate accettate | Corrette scartate | Errore bilanciato | "
        "Costo per esempio | Latenza media |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        righe.append(
            f"| {r.name} | {r.outcome.escalated:.0%} | {conta(r.false_accepts, n_wrong)} | "
            f"{conta(r.false_rejects, n_correct)} | {r.outcome.balanced_error:.3f} | ${r.cost_usd:.5f} | "
            f"{r.latency_s:.2f} s |")
    righe += [
        "",
        f"La tolleranza fissata prima di guardare i numeri e' **{preregistered_tolerance:.2f}** "
        "(errore bilanciato non oltre quello del costoso da solo piu' la tolleranza). Le altre righe sono "
        "una sensibilita', non una scelta.",
        "",
        "Note: i conteggi sono piccoli (decine di esempi per classe): un esempio in piu' o in meno sposta le "
        "percentuali di piu' punti. \"Sbagliate accettate\" e' l'errore pericoloso. L'analisi e' esplorativa, "
        "su un solo dominio, e fuori dalla regola di arresto dell'esperimento (via libera esplicito).",
    ]
    return "\n".join(righe) + "\n"
