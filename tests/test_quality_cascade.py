"""La cascata di giudici: decisioni, soglie scelte senza imbrogliare, costo.

Nota di design (tesi):
    L'AUROC non si puo' usare per una cascata: i punteggi dell'economico e del costoso hanno
    scale diverse. Si misurano **decisioni**: quante soluzioni sbagliate si accettano (l'errore
    pericoloso), quante corrette si scartano, quante richieste vanno al costoso. Le soglie si
    scelgono sui blocchi di addestramento e si valutano su esercizi mai visti: con 190 esempi,
    sceglierle sugli stessi dati darebbe un risultato ottimistico.
"""

import pytest

from quality.cascade import (ALWAYS_ESCALATE, Case, Outcome, Thresholds, cases_from, cross_validate,
                             evaluate_policy, sweep)
from quality.dataset import Example
from quality.evaluate import Judgment


def _casi_facili_e_difficili(n_task=10):
    """Per esercizio: 2 casi che l'economico vede bene e 2 dubbi; il costoso e' sempre perfetto."""
    casi = []
    for t in range(n_task):
        casi.append(Case(f"f1_{t}", f"t{t}", 1, 0.95, 0.99))        # corretto e ovvio
        casi.append(Case(f"f0_{t}", f"t{t}", 0, 0.05, 0.01))        # sbagliato e ovvio
        casi.append(Case(f"d1_{t}", f"t{t}", 1, 0.45, 0.97))        # corretto ma dubbio: l'economico lo vede male
        casi.append(Case(f"d0_{t}", f"t{t}", 0, 0.55, 0.03))        # sbagliato ma dubbio
    return casi


# -- Una politica ----------------------------------------------------------------------

def test_passando_sempre_al_costoso_si_ottengono_le_sue_decisioni():
    esito = evaluate_policy(_casi_facili_e_difficili(), ALWAYS_ESCALATE)

    assert isinstance(esito, Outcome)
    assert (esito.escalated, esito.false_accept, esito.false_reject, esito.accuracy) == (1.0, 0.0, 0.0, 1.0)


def test_senza_mai_passare_al_costoso_si_ottengono_le_decisioni_dell_economico():
    esito = evaluate_policy(_casi_facili_e_difficili(), Thresholds(0.5, 0.5))

    # a soglia 0,5: i dubbi sbagliati (0,55) si accettano, i dubbi corretti (0,45) si scartano
    assert esito.escalated == 0.0
    assert esito.false_accept == pytest.approx(0.5) and esito.false_reject == pytest.approx(0.5)
    assert esito.balanced_error == pytest.approx(0.5) and esito.accuracy == pytest.approx(0.5)


def test_la_cascata_chiede_al_costoso_solo_i_dubbi_e_raggiunge_la_sua_qualita():
    esito = evaluate_policy(_casi_facili_e_difficili(), Thresholds(0.2, 0.8))

    assert esito.escalated == pytest.approx(0.5)                     # i due casi dubbi su quattro
    assert (esito.false_accept, esito.false_reject, esito.accuracy) == (0.0, 0.0, 1.0)


def test_i_bordi_delle_soglie_decidono_senza_passare_al_costoso():
    casi = [Case("a", "t", 1, 0.8, 0.0), Case("b", "t", 0, 0.2, 1.0)]

    esito = evaluate_policy(casi, Thresholds(0.2, 0.8))

    assert esito.escalated == 0.0 and esito.accuracy == 1.0          # 0,8 accetta, 0,2 rifiuta


def test_senza_casi_e_un_errore():
    with pytest.raises(ValueError):
        evaluate_policy([], ALWAYS_ESCALATE)


def test_con_una_sola_classe_l_errore_dell_altra_non_si_misura_ma_non_cade_tutto():
    esito = evaluate_policy([Case("a", "t", 1, 0.9, 0.9), Case("b", "t", 1, 0.1, 0.8)], ALWAYS_ESCALATE)

    assert esito.false_accept is None and esito.false_reject == 0.0 and esito.balanced_error == 0.0


# -- Descrizione di tutte le soglie ----------------------------------------------------

def test_lo_sweep_elenca_le_coppie_ordinate_e_include_i_due_estremi():
    griglia = [0.0, 0.5, 1.0]

    righe = sweep(_casi_facili_e_difficili(), griglia)

    coppie = {(s.low, s.high) for s, _ in righe}
    assert all(lo <= hi for lo, hi in coppie) and (0.0, 1.0) in coppie and (0.5, 0.5) in coppie
    assert len(righe) == 6                                           # (3 scelte di lo) x (hi >= lo) = 3+2+1


# -- Validazione per blocchi di esercizi -----------------------------------------------

def test_la_validazione_sceglie_soglie_che_risparmiano_il_costoso_senza_perdere_qualita():
    cv = cross_validate(_casi_facili_e_difficili(), folds=5, seed=0, tolerance=0.02,
                        grid=[i / 20 for i in range(21)])

    assert cv.strong_alone.balanced_error == 0.0
    assert cv.cascade.balanced_error <= cv.strong_alone.balanced_error + 0.02
    assert cv.cascade.escalated < 0.75                               # chiede al costoso meno di sempre
    assert cv.cascade.n == 40 and cv.folds == 5 and len(cv.thresholds_per_fold) == 5


def test_ogni_esercizio_sta_in_un_solo_blocco_e_il_risultato_e_riproducibile():
    casi = _casi_facili_e_difficili()

    primo = cross_validate(casi, folds=5, seed=1, grid=[0.0, 0.25, 0.5, 0.75, 1.0])
    secondo = cross_validate(casi, folds=5, seed=1, grid=[0.0, 0.25, 0.5, 0.75, 1.0])

    assert primo == secondo
    assert primo.cascade.n == len(casi)                              # ogni caso e' valutato una volta, mai in addestramento


def test_se_nessuna_soglia_rispetta_la_tolleranza_si_passa_sempre_al_costoso():
    # L'economico e' del tutto sbagliato: nessuna scorciatoia e' sicura.
    casi = []
    for t in range(10):
        casi += [Case(f"a{t}", f"t{t}", 1, 0.05, 0.95), Case(f"b{t}", f"t{t}", 0, 0.95, 0.05)]

    cv = cross_validate(casi, folds=5, seed=0, tolerance=0.0, grid=[0.0, 0.25, 0.5, 0.75, 1.0])

    assert cv.cascade.escalated == 1.0 and cv.cascade.balanced_error == 0.0
    assert all(t == ALWAYS_ESCALATE for t in cv.thresholds_per_fold)


def test_il_confronto_con_l_economico_da_solo_usa_la_sua_soglia_migliore_scelta_allo_stesso_modo():
    cv = cross_validate(_casi_facili_e_difficili(), folds=5, seed=0, grid=[i / 20 for i in range(21)])

    assert cv.cheap_alone.escalated == 0.0
    assert cv.cheap_alone.balanced_error > cv.strong_alone.balanced_error     # senza il costoso si sbaglia di piu'


@pytest.mark.parametrize("folds", [1, 0])
def test_troppo_pochi_blocchi_e_un_errore(folds):
    with pytest.raises(ValueError):
        cross_validate(_casi_facili_e_difficili(), folds=folds)


def test_piu_blocchi_degli_esercizi_e_un_errore():
    with pytest.raises(ValueError, match="esercizi"):
        cross_validate([Case("a", "t0", 1, 0.9, 0.9), Case("b", "t0", 0, 0.1, 0.1)], folds=5)


# -- Dai giudizi ai casi -----------------------------------------------------------------

def _es():
    return [Example("a", "t1", "agente", "i", "x", 1), Example("b", "t1", "mutante", "i", "y", 0),
            Example("c", "t2", "mutante", "i", "z", 0)]


def _g(id_, nome, p, rep=1):
    return Judgment(id_, nome, rep, p, None if p is not None else "HTTP 500", 0.0, 0.1, None)


def test_i_casi_hanno_la_media_delle_ripetizioni_valide_e_solo_gli_esempi_giudicati_da_entrambi():
    giudizi = [_g("a", "d1", 0.8), _g("a", "d1", 0.6, rep=2), _g("a", "op", 0.9),
               _g("b", "d1", 0.2), _g("b", "op", 0.1),
               _g("c", "d1", 0.3)]                                  # `c` non e' stato giudicato dal costoso

    casi = cases_from(_es(), giudizi, "d1", "op")

    assert {c.example_id for c in casi} == {"a", "b"}
    a = next(c for c in casi if c.example_id == "a")
    assert (a.task_id, a.label, a.cheap, a.strong) == ("t1", 1, pytest.approx(0.7), 0.9)


def test_i_giudizi_senza_risposta_non_contano_e_si_puo_limitare_a_un_sottoinsieme():
    giudizi = [_g("a", "d1", None), _g("a", "op", 0.9), _g("b", "d1", 0.2), _g("b", "op", 0.1),
               _g("c", "d1", 0.3), _g("c", "op", 0.2)]

    assert {c.example_id for c in cases_from(_es(), giudizi, "d1", "op")} == {"b", "c"}
    assert {c.example_id for c in cases_from(_es(), giudizi, "d1", "op", only_examples=["c"])} == {"c"}


# -- Il confronto di costo -----------------------------------------------------------

from quality.cascade import CostModel, analyze, render_cascade_markdown  # noqa: E402


def _costi():
    return CostModel(cheap_usd=0.00007, strong_usd=0.0206, cheap_latency_s=0.22, strong_latency_s=7.7)


def test_il_costo_della_cascata_e_quello_dell_economico_piu_la_quota_passata_al_costoso():
    righe = analyze(_casi_facili_e_difficili(), _costi(), seed=0, tolerances=(0.02,),
                    grid=[i / 20 for i in range(21)])

    cascata = next(r for r in righe if r.name.startswith("cascata"))
    assert cascata.cost_usd == pytest.approx(0.00007 + cascata.outcome.escalated * 0.0206)
    assert cascata.latency_s == pytest.approx(0.22 + cascata.outcome.escalated * 7.7)


def test_i_due_confronti_hanno_il_loro_costo():
    righe = analyze(_casi_facili_e_difficili(), _costi(), seed=0, tolerances=(0.02,),
                    grid=[i / 20 for i in range(21)])

    costoso = next(r for r in righe if r.name == "costoso da solo")
    economico = next(r for r in righe if r.name == "economico da solo")
    assert costoso.cost_usd == 0.0206 and economico.cost_usd == 0.00007
    assert costoso.outcome.escalated == 1.0 and economico.outcome.escalated == 0.0


def test_ogni_tolleranza_ha_la_sua_riga_e_i_conteggi_sono_interi():
    casi = _casi_facili_e_difficili()

    righe = analyze(casi, _costi(), seed=0, tolerances=(0.0, 0.02, 0.05), grid=[i / 20 for i in range(21)])

    assert [r.name for r in righe if r.name.startswith("cascata")] == [
        "cascata (tolleranza 0.00)", "cascata (tolleranza 0.02)", "cascata (tolleranza 0.05)"]
    r = righe[0]
    assert r.n_wrong == 20 and r.n_correct == 20
    assert r.false_accepts == round((r.outcome.false_accept or 0) * 20)


def test_il_markdown_mostra_conteggi_costi_e_dichiara_che_la_tolleranza_fissata_e_0_02():
    righe = analyze(_casi_facili_e_difficili(), _costi(), seed=0, tolerances=(0.0, 0.02, 0.05),
                    grid=[i / 20 for i in range(21)])

    testo = render_cascade_markdown(righe, preregistered_tolerance=0.02)

    for atteso in ("costoso da solo", "economico da solo", "cascata (tolleranza 0.02)", "fissata prima",
                   "sensibilita", "/20"):
        assert atteso in testo
