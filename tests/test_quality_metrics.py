"""Le metriche dell'esperimento M2b.5, verificate su valori calcolati a mano.

Nota di design (tesi):
    Le formule sono scritte in Python standard (decisione D23: nessuna libreria
    nuova). Per questo i test sono il loro unico garante: ogni valore atteso
    qui e' calcolato a mano, e due vengono dalla prova reale del 14 ott 2026
    su 10 soluzioni di `is_prime` (5 giuste, 5 sbagliate) con d1 ospitato e
    `d1-3B` locale.
"""

import pytest

from quality.metrics import ReliabilityBin, auroc, brier, cluster_bootstrap_ci, ece, reliability_table

# Prova reale: probabilita' che la soluzione sia corretta, 10 casi (5 giuste, 5 sbagliate).
VERE = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
OSPITATO = [0.9883, 0.9929, 0.9724, 0.9933, 0.9627, 0.0132, 0.1128, 0.9526, 0.0023, 0.0016]
LOCALE = [0.8281, 0.7038, 0.5949, 0.7391, 0.7300, 0.3590, 0.8312, 0.8076, 0.3013, 0.1801]


# -- AUROC ---------------------------------------------------------------------

def test_auroc_di_un_ordine_perfetto_e_uno_e_di_uno_invertito_e_zero():
    assert auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert auroc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]) == 0.0


def test_auroc_conta_le_coppie_giuste():
    # positivi {0,9; 0,4}, negativi {0,8; 0,3}: 0,9>0,8 si', 0,9>0,3 si', 0,4>0,8 no, 0,4>0,3 si' = 3/4
    assert auroc([0.9, 0.8, 0.4, 0.3], [1, 0, 1, 0]) == 0.75


def test_auroc_con_punteggi_uguali_vale_mezzo():
    assert auroc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.5


def test_auroc_sulla_prova_reale_di_d1():
    assert auroc(OSPITATO, VERE) == 1.0                      # 25 coppie su 25
    assert auroc(LOCALE, VERE) == pytest.approx(16 / 25)     # il locale sbaglia 9 coppie


@pytest.mark.parametrize("punteggi, etichette", [
    ([0.9, 0.8], [1, 1]),            # nessun negativo
    ([0.9, 0.8], [0, 0]),            # nessun positivo
    ([], []),
    ([0.9, 0.1], [1]),               # lunghezze diverse
    ([0.9, 0.1], [1, 2]),            # etichetta non valida
])
def test_auroc_rifiuta_dati_che_non_permettono_la_misura(punteggi, etichette):
    with pytest.raises(ValueError):
        auroc(punteggi, etichette)


# -- Brier ---------------------------------------------------------------------

def test_brier_di_valori_noti():
    assert brier([0.9, 0.2], [1, 0]) == pytest.approx((0.1 ** 2 + 0.2 ** 2) / 2)
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert brier([0.5] * 4, [1, 0, 1, 0]) == 0.25


def test_brier_sulla_prova_reale_lo_sbaglio_sicuro_pesa_quasi_tutto():
    assert brier(OSPITATO, VERE) == pytest.approx(0.0923, abs=1e-4)
    assert brier(LOCALE, VERE) == pytest.approx(0.2018, abs=1e-4)
    # Il solo caso 7 (disse 0,9526, era sbagliata) vale 0,9074 di una somma di 0,9227.
    assert (0.9526 - 0) ** 2 == pytest.approx(0.9074, abs=1e-4)


@pytest.mark.parametrize("probabilita", [[1.2, 0.1], [-0.1, 0.5], [float("nan"), 0.5]])
def test_brier_rifiuta_probabilita_fuori_da_zero_uno(probabilita):
    with pytest.raises(ValueError):
        brier(probabilita, [1, 0])


# -- ECE e curva di affidabilita' --------------------------------------------------

def test_ece_e_zero_quando_il_dichiarato_coincide_con_il_reale():
    # dieci giudizi al 90% con nove giusti, dieci al 10% con uno giusto
    probabilita = [0.9] * 10 + [0.1] * 10
    etichette = [1] * 9 + [0] + [1] + [0] * 9
    assert ece(probabilita, etichette) == pytest.approx(0.0)


def test_ece_misura_lo_scarto_pesato_per_quanti_giudizi_ci_sono():
    # al 90% solo sei giusti su dieci (scarto 0,30), al 10% uno su dieci (scarto 0): (0,30 + 0)/2
    probabilita = [0.9] * 10 + [0.1] * 10
    etichette = [1] * 6 + [0] * 4 + [1] + [0] * 9
    assert ece(probabilita, etichette) == pytest.approx(0.15)


def test_i_giudizi_a_zero_e_a_uno_cadono_nel_primo_e_nell_ultimo_gruppo():
    tabella = reliability_table([0.0, 1.0], [0, 1], bins=10)

    assert (tabella[0].count, tabella[-1].count) == (1, 1)
    assert sum(g.count for g in tabella) == 2


def test_la_curva_di_affidabilita_riporta_conteggi_e_medie():
    tabella = reliability_table([0.91, 0.95, 0.12], [1, 0, 0], bins=10)

    ultimo = tabella[-1]
    assert isinstance(ultimo, ReliabilityBin)
    assert (ultimo.low, ultimo.high, ultimo.count) == (0.9, 1.0, 2)
    assert ultimo.mean_probability == pytest.approx(0.93)
    assert ultimo.fraction_positive == 0.5


@pytest.mark.parametrize("gruppi", [0, -3])
def test_i_gruppi_devono_essere_almeno_uno(gruppi):
    with pytest.raises(ValueError):
        ece([0.5], [1], bins=gruppi)


# -- Intervalli per cluster ---------------------------------------------------------

def _dati_a_blocchi():
    """Sei esercizi, ognuno con un positivo e un negativo: l'ordine e' perfetto in ogni blocco."""
    punteggi, etichette, cluster = [], [], []
    for i in range(6):
        punteggi += [0.9, 0.1]
        etichette += [1, 0]
        cluster += [f"e{i}"] * 2
    return punteggi, etichette, cluster


def test_con_un_ordine_perfetto_in_ogni_blocco_l_intervallo_e_un_punto():
    punteggi, etichette, cluster = _dati_a_blocchi()

    basso, alto, validi = cluster_bootstrap_ci(auroc, punteggi, etichette, cluster, n_boot=200)

    assert (basso, alto, validi) == (1.0, 1.0, 200)


def test_l_intervallo_e_riproducibile_con_lo_stesso_seme():
    punteggi = [0.9, 0.2, 0.7, 0.6, 0.8, 0.3, 0.5, 0.4]
    etichette = [1, 0, 1, 0, 1, 0, 1, 0]
    cluster = ["a", "a", "b", "b", "c", "c", "d", "d"]

    primo = cluster_bootstrap_ci(auroc, punteggi, etichette, cluster, n_boot=300, seed=1)
    secondo = cluster_bootstrap_ci(auroc, punteggi, etichette, cluster, n_boot=300, seed=1)

    assert primo == secondo
    assert 0.0 <= primo[0] <= primo[1] <= 1.0


def test_si_ricampionano_interi_blocchi_e_si_contano_quelli_che_non_servono_alla_misura():
    # Il blocco A ha solo positivi, il blocco B solo negativi: un ricampionamento AA o BB non ha
    # entrambe le classi e non si puo' misurare; AB e BA si'.
    punteggi, etichette, cluster = [0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0], ["A", "A", "B", "B"]

    _, _, validi = cluster_bootstrap_ci(auroc, punteggi, etichette, cluster, n_boot=400, seed=3)

    assert 0 < validi < 400


def test_senza_nessun_ricampionamento_valido_e_un_errore():
    with pytest.raises(ValueError):
        cluster_bootstrap_ci(auroc, [0.9, 0.8], [1, 1], ["a", "b"], n_boot=20)


def test_auroc_dai_ranghi_coincide_con_il_conto_delle_coppie_su_dati_casuali():
    """Il calcolo veloce (ranghi) deve dare lo stesso numero di quello ovvio (tutte le coppie)."""
    import random
    rng = random.Random(7)
    for _ in range(25):
        n = rng.randrange(6, 60)
        punteggi = [round(rng.random(), 1) for _ in range(n)]       # arrotondati: molti parimerito
        etichette = [rng.randrange(2) for _ in range(n)]
        if len(set(etichette)) < 2:
            continue
        pos = [s for s, e in zip(punteggi, etichette) if e]
        neg = [s for s, e in zip(punteggi, etichette) if not e]
        a_coppie = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg) / (len(pos) * len(neg))
        assert auroc(punteggi, etichette) == pytest.approx(a_coppie)
