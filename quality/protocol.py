"""Lettura e controllo del protocollo dell'esperimento (`quality/protocol.toml`)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Gli stimatori che l'esperimento sa costruire (i nomi che compaiono nei risultati).
ESTIMATORS = ("heuristic", "d1_hosted_plain", "d1_hosted_criteria", "d1_local_plain",
              "d1_local_criteria", "frontier")


@dataclass(frozen=True)
class Protocol:
    """Il protocollo, controllato."""

    state_template: str
    question: str
    criteria: tuple[str, str]
    frontier_model: str
    frontier_system: str
    frontier_user_template: str
    primary: str
    reference: str
    promising_lower_bound: float
    max_gap_to_reference: float
    negative_upper_bound: float
    repetitions_d1: int
    repetitions_frontier: int
    max_total_usd: float
    reserve_per_call_usd: float
    workers: int
    bootstrap_samples: int
    seed: int


def _sezione(dati: dict[str, Any], nome: str) -> dict[str, Any]:
    sezione = dati.get(nome)
    if not isinstance(sezione, dict):
        raise ValueError(f"nel protocollo manca la sezione [{nome}]")
    return sezione


def _campo(sezione: dict[str, Any], nome: str, tipo: type | tuple[type, ...], etichetta: str) -> Any:
    valore = sezione.get(nome)
    if isinstance(valore, bool) or not isinstance(valore, tipo):
        raise ValueError(f"nel protocollo [{etichetta}] manca `{nome}` o non e' del tipo giusto: {valore!r}")
    return valore


def load_protocol(path: Path) -> Protocol:
    """Legge il protocollo e lo controlla **prima** di qualunque spesa.

    Raises:
        ValueError: se manca una sezione o un campo, una soglia e' incoerente, un
            modello di testo ha segnaposto non ammessi o lo stimatore primario e'
            sconosciuto.
    """
    from quality.estimators import render_state          # per riusare il controllo dei segnaposto
    from quality.dataset import Example

    with path.open("rb") as file:
        dati = tomllib.load(file)
    stato, domanda = _sezione(dati, "state"), _sezione(dati, "question")
    frontier, decisione, corsa = _sezione(dati, "frontier"), _sezione(dati, "decision"), _sezione(dati, "run")

    p = Protocol(
        state_template=_campo(stato, "template", str, "state"),
        question=_campo(domanda, "text", str, "question"),
        criteria=(_campo(domanda, "criteria_true", str, "question"),
                  _campo(domanda, "criteria_false", str, "question")),
        frontier_model=_campo(frontier, "model", str, "frontier"),
        frontier_system=_campo(frontier, "system", str, "frontier"),
        frontier_user_template=_campo(frontier, "user_template", str, "frontier"),
        primary=_campo(decisione, "primary", str, "decision"),
        reference=_campo(decisione, "reference", str, "decision"),
        promising_lower_bound=float(_campo(decisione, "promising_lower_bound", (int, float), "decision")),
        max_gap_to_reference=float(_campo(decisione, "max_gap_to_reference", (int, float), "decision")),
        negative_upper_bound=float(_campo(decisione, "negative_upper_bound", (int, float), "decision")),
        repetitions_d1=_campo(corsa, "repetitions_d1", int, "run"),
        repetitions_frontier=_campo(corsa, "repetitions_frontier", int, "run"),
        max_total_usd=float(_campo(corsa, "max_total_usd", (int, float), "run")),
        reserve_per_call_usd=float(_campo(corsa, "reserve_per_call_usd", (int, float), "run")),
        workers=_campo(corsa, "workers", int, "run"),
        bootstrap_samples=_campo(corsa, "bootstrap_samples", int, "run"),
        seed=_campo(corsa, "seed", int, "run"),
    )
    for nome in ("promising_lower_bound", "negative_upper_bound"):
        if not 0.5 <= getattr(p, nome) <= 1.0:
            raise ValueError(f"{nome} deve stare fra 0,5 e 1, trovato {getattr(p, nome)}")
    if not 0.0 <= p.max_gap_to_reference <= 0.5:
        raise ValueError(f"max_gap_to_reference deve stare fra 0 e 0,5, trovato {p.max_gap_to_reference}")
    if p.negative_upper_bound > p.promising_lower_bound:
        raise ValueError("negative_upper_bound non puo' superare promising_lower_bound: le due zone si sovrapporrebbero")
    if p.max_total_usd <= 0 or p.reserve_per_call_usd < 0:
        raise ValueError("max_total_usd deve essere positivo e reserve_per_call_usd non negativo")
    for nome in ("repetitions_d1", "repetitions_frontier", "workers", "bootstrap_samples"):
        if getattr(p, nome) < 1:
            raise ValueError(f"{nome} deve essere almeno 1")
    if p.primary not in ESTIMATORS or p.reference not in ESTIMATORS:
        raise ValueError(f"primary e reference devono essere fra: {', '.join(ESTIMATORS)}")
    prova = Example("x", "x", "agente", "i", "s", 1)
    for modello in (p.state_template, p.frontier_user_template):
        render_state(modello, prova)                       # solleva ValueError("segnaposto ...")
    return p
