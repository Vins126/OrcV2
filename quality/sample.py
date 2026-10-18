"""Un campione stratificato e riproducibile del dataset, per limitare la spesa del giudice costoso."""

import random
from collections.abc import Sequence

from quality.dataset import Example


def stratified_sample(examples: Sequence[Example], n: int, seed: int = 0) -> list[Example]:
    """Un campione di `n` esempi con le classi bilanciate e gli esempi rari sempre dentro.

    Criterio (scelto prima di vedere i risultati del giudice costoso): meta' corretti e
    meta' sbagliati, perche' la precisione dell'AUROC dipende dal numero di coppie
    (corretti x sbagliati) ed e' massima a classi bilanciate. Per ogni classe si prende
    **tutto** lo strato piu' piccolo (i mutanti equivalenti fra i corretti, le soluzioni
    sbagliate degli agenti fra gli sbagliati: servono ai due controlli) e il resto dallo
    strato grande, a caso con il seme. L'ordine del risultato e' quello del dataset.

    Args:
        examples: il dataset, con le etichette.
        n: quanti esempi; se supera il dataset si restituisce tutto.
        seed: il seme: stesso seme, stesso campione.

    Raises:
        ValueError: se `n` non e' positivo o ci sono esempi senza etichetta.
    """
    if n < 1:
        raise ValueError(f"n deve essere almeno 1, non {n}")
    if any(e.label is None for e in examples):
        raise ValueError("tutti gli esempi devono avere l'etichetta: il campione la usa per bilanciare")
    if n >= len(examples):
        return list(examples)
    rng = random.Random(seed)
    positivi = [e for e in examples if e.label == 1]
    negativi = [e for e in examples if e.label == 0]
    n_pos = min(n // 2, len(positivi))
    n_neg = min(n - n_pos, len(negativi))
    n_pos = min(n - n_neg, len(positivi))          # se i negativi non bastano, il resto va ai positivi
    scelti = {e.example_id for e in _prendi(positivi, n_pos, rng) + _prendi(negativi, n_neg, rng)}
    return [e for e in examples if e.example_id in scelti]


def _prendi(classe: list[Example], k: int, rng: random.Random) -> list[Example]:
    """`k` esempi di una classe: tutto lo strato (per origine) piu' piccolo, il resto da quello grande."""
    per_origine: dict[str, list[Example]] = {}
    for e in classe:
        per_origine.setdefault(e.origin, []).append(e)
    strati = sorted(per_origine.values(), key=len)
    if len(strati) == 1:
        return rng.sample(strati[0], min(k, len(strati[0])))
    piccolo, grande = strati[0], strati[-1]
    if k <= len(piccolo):
        return rng.sample(piccolo, k)
    return list(piccolo) + rng.sample(grande, min(k - len(piccolo), len(grande)))
