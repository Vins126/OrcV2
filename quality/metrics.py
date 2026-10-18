"""Metriche per stimatori di probabilita': AUROC, Brier, ECE e intervalli per cluster."""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ReliabilityBin:
    """Un gruppo della curva di affidabilita'.

    Attributes:
        low: estremo inferiore dell'intervallo di probabilita' del gruppo.
        high: estremo superiore.
        count: quanti giudizi cadono nel gruppo.
        mean_probability: probabilita' media dichiarata nel gruppo.
        fraction_positive: frazione di esempi davvero positivi nel gruppo.
    """

    low: float
    high: float
    count: int
    mean_probability: float
    fraction_positive: float


def _controlla(valori: Sequence[float], etichette: Sequence[int]) -> None:
    """Rifiuta dati che non permettono nessuna misura: vuoti, disallineati, etichette non 0/1."""
    if len(valori) != len(etichette):
        raise ValueError(f"{len(valori)} valori e {len(etichette)} etichette: devono essere uguali")
    if not valori:
        raise ValueError("nessun dato")
    if any(e not in (0, 1) for e in etichette):
        raise ValueError("le etichette devono essere 0 (sbagliata) o 1 (corretta)")
    if any(not isfinite(v) for v in valori):
        raise ValueError("i valori devono essere numeri finiti")


def _controlla_probabilita(probabilita: Sequence[float]) -> None:
    if any(not isfinite(p) or p < 0.0 or p > 1.0 for p in probabilita):
        raise ValueError("le probabilita' devono stare fra 0 e 1")


def auroc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Probabilita' che un esempio positivo prenda un punteggio piu' alto di uno negativo.

    Si calcola dai ranghi (la statistica di Mann-Whitney), cosi' costa n log n e
    non n^2: serve perche' il ricampionamento la ripete migliaia di volte. A
    punteggi uguali il rango e' la media, cioe' la coppia vale mezzo.

    Raises:
        ValueError: se mancano esempi di una delle due classi, le lunghezze
            differiscono o le etichette non sono 0 o 1.
    """
    _controlla(scores, labels)
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("servono esempi di entrambe le classi per misurare l'AUROC")
    ordine = sorted(range(len(scores)), key=lambda i: scores[i])
    ranghi = [0.0] * len(scores)
    i = 0
    while i < len(ordine):
        j = i
        while j + 1 < len(ordine) and scores[ordine[j + 1]] == scores[ordine[i]]:
            j += 1
        medio = (i + j) / 2 + 1                      # ranghi da 1; parimerito = media
        for k in range(i, j + 1):
            ranghi[ordine[k]] = medio
        i = j + 1
    somma_pos = sum(r for r, e in zip(ranghi, labels) if e == 1)
    return (somma_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def brier(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    """Media di (probabilita' - realta')^2: 0 e' perfetto, dire sempre 0,5 da' 0,25.

    Punisce molto chi e' sicuro e sbaglia: dire 0,95 su una soluzione sbagliata
    costa 0,90 da solo.

    Raises:
        ValueError: se una probabilita' e' fuori da [0, 1] o i dati non sono validi.
    """
    _controlla(probabilities, labels)
    _controlla_probabilita(probabilities)
    return sum((p - e) ** 2 for p, e in zip(probabilities, labels)) / len(labels)


def reliability_table(probabilities: Sequence[float], labels: Sequence[int],
                      bins: int = 10) -> list[ReliabilityBin]:
    """Raggruppa i giudizi per probabilita' dichiarata e confronta con la realta'.

    I gruppi sono `bins` intervalli uguali di [0, 1]; 1,0 cade nell'ultimo. Un
    gruppo vuoto ha conteggio 0 e medie 0: non si usa nel calcolo dell'ECE.

    Raises:
        ValueError: se `bins` e' minore di uno o i dati non sono validi.
    """
    if bins < 1:
        raise ValueError(f"bins deve essere almeno 1, non {bins}")
    _controlla(probabilities, labels)
    _controlla_probabilita(probabilities)
    gruppi: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, e in zip(probabilities, labels):
        gruppi[min(int(p * bins), bins - 1)].append((p, e))
    tabella = []
    for k, g in enumerate(gruppi):
        n = len(g)
        tabella.append(ReliabilityBin(
            low=k / bins, high=(k + 1) / bins, count=n,
            mean_probability=sum(p for p, _ in g) / n if n else 0.0,
            fraction_positive=sum(e for _, e in g) / n if n else 0.0))
    return tabella


def ece(probabilities: Sequence[float], labels: Sequence[int], bins: int = 10) -> float:
    """Errore di calibrazione atteso: media pesata degli scarti fra dichiarato e reale.

    In ogni gruppo si confronta la probabilita' media dichiarata con la frazione
    di positivi veri; gli scarti si pesano per quanti giudizi ci sono. Con pochi
    esempi e' una stima rumorosa: va letta insieme al numero di esempi.
    """
    tabella = reliability_table(probabilities, labels, bins)
    totale = len(labels)
    return sum(g.count / totale * abs(g.mean_probability - g.fraction_positive)
               for g in tabella if g.count)


def cluster_bootstrap_ci(
    statistic: Callable[[Sequence[float], Sequence[int]], float],
    scores: Sequence[float], labels: Sequence[int], clusters: Sequence[str], *,
    n_boot: int = 2000, seed: int = 0, alpha: float = 0.05,
) -> tuple[float, float, int]:
    """Intervallo di confidenza percentile, ricampionando interi cluster (per esempio esercizi).

    Le soluzioni dello stesso esercizio (le ripetizioni degli agenti e i loro
    mutanti) non sono indipendenti: ricampionare i singoli esempi darebbe un
    intervallo troppo stretto. Si ricampionano invece gli **esercizi** interi, con
    reinserimento. Un ricampionamento in cui manca una delle due classi non si puo'
    misurare e si scarta (e si conta).

    Args:
        statistic: la misura da stimare, per esempio `auroc`; solleva `ValueError`
            se il ricampionamento non la permette.
        scores: punteggi o probabilita'.
        labels: etichette 0/1.
        clusters: a quale blocco appartiene ogni esempio.
        n_boot: quanti ricampionamenti.
        seed: seme: stesso seme, stesso intervallo.
        alpha: 0,05 per un intervallo al 95%.

    Returns:
        (limite inferiore, limite superiore, ricampionamenti validi).

    Raises:
        ValueError: se i dati non sono validi o nessun ricampionamento e' valido.
    """
    _controlla(scores, labels)
    if len(clusters) != len(labels):
        raise ValueError("un cluster per ogni esempio")
    if n_boot < 1 or not 0.0 < alpha < 1.0:
        raise ValueError("n_boot deve essere almeno 1 e alpha fra 0 e 1")
    per_cluster: dict[str, list[int]] = {}
    for i, c in enumerate(clusters):
        per_cluster.setdefault(c, []).append(i)
    nomi = sorted(per_cluster)
    rng = random.Random(seed)
    valori: list[float] = []
    for _ in range(n_boot):
        scelti = [nomi[rng.randrange(len(nomi))] for _ in nomi]
        indici = [i for c in scelti for i in per_cluster[c]]
        try:
            valori.append(statistic([scores[i] for i in indici], [labels[i] for i in indici]))
        except ValueError:
            continue
    if not valori:
        raise ValueError("nessun ricampionamento valido: mancano esempi di una classe")
    valori.sort()
    basso = valori[int(alpha / 2 * len(valori))]
    alto = valori[min(len(valori) - 1, int((1 - alpha / 2) * len(valori)))]
    return basso, alto, len(valori)
