"""Il rapporto: le misure per stimatore e la regola di D21 applicata come scritta.

Nota di design (tesi):
    La regola e' stata fissata **prima** dei risultati: *promettente* se il limite inferiore
    dell'intervallo al 95% dell'AUROC del primario e' >= 0,70 e il suo AUROC non e' oltre 0,10
    sotto quello del riferimento; *negativo* se il limite superiore e' <= 0,65; altrimenti
    *inconcludente*. I test provano ogni zona e i bordi, perche' e' qui che una regola scritta
    bene puo' essere applicata male senza che nessuno se ne accorga.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from quality.dataset import Example
from quality.evaluate import Judgment
from quality.protocol import load_protocol
from quality.report import Decision, EstimatorReport, build_report, decide, render_markdown

PROTOCOLLO = replace(load_protocol(Path("quality/protocol.toml")), bootstrap_samples=200)


def _esempi(n_task=10):
    """Per ogni esercizio: una soluzione di agente corretta, due mutanti sbagliati e uno equivalente."""
    esempi = []
    for t in range(n_task):
        esempi.append(Example(f"a{t}", f"t{t}", "agente", "i", "x", 1, f"r{t}"))
        esempi += [Example(f"m{t}_{k}", f"t{t}", "mutante", "i", f"x{k}", 0 if k < 2 else 1, f"r{t}", "compare", 1)
                   for k in range(3)]
    return esempi


def _giudizi(esempi, nome, p, rep=1, costo=0.0, latenza=0.1):
    return [Judgment(e.example_id, nome, rep, p(e), None if p(e) is not None else "HTTP 500", costo, latenza, 100)
            for e in esempi]


def _rapporto(nome, p, **kw):
    esempi = _esempi()
    return build_report(esempi, _giudizi(esempi, nome, p, **kw), PROTOCOLLO).estimators[nome]


# -- Le misure -----------------------------------------------------------------------

def test_uno_stimatore_perfetto_ordina_bene_e_ha_un_intervallo_che_e_un_punto():
    r = _rapporto("perfetto", lambda e: 0.9 if e.label else 0.1)

    assert r.auroc == 1.0 and (r.auroc_low, r.auroc_high) == (1.0, 1.0)
    assert r.brier == pytest.approx(0.01)
    assert r.ece == pytest.approx(0.1)                 # dice 0,9 e 0,1 ma ha ragione al 100%: scarto 0,1
    assert (r.n_examples, r.n_scored, r.n_failed_judgments) == (40, 40, 0)


def test_uno_stimatore_senza_opinione_vale_mezzo():
    r = _rapporto("moneta", lambda e: 0.5)

    assert r.auroc == 0.5 and r.brier == 0.25


def test_i_giudizi_senza_risposta_non_sono_risposte_si_contano_a_parte():
    r = _rapporto("a", lambda e: None if e.example_id.startswith("m0_") else (0.9 if e.label else 0.1))

    assert r.n_failed_judgments == 3 and r.n_scored == 37 and r.n_examples == 40
    assert r.auroc == 1.0


def test_con_piu_ripetizioni_si_mediano_e_si_misura_quanto_variano():
    esempi = _esempi()
    giudizi = []
    for rep, delta in ((1, -0.1), (2, 0.0), (3, 0.1)):
        giudizi += _giudizi(esempi, "s", lambda e, d=delta: (0.8 if e.label else 0.2) + d, rep=rep)

    r = build_report(esempi, giudizi, PROTOCOLLO).estimators["s"]

    assert r.repetitions == 3 and r.repeatability == pytest.approx(0.2)    # alta - bassa = 0,2
    assert r.auroc == 1.0 and r.brier == pytest.approx(0.04)               # sulla media (0,8 / 0,2)


def test_se_lo_stesso_giudizio_compare_due_volte_vale_l_ultimo():
    esempi = _esempi(2)
    vecchi = [Judgment(e.example_id, "s", 1, None, "HTTP 500", 0.0, 0.1, None) for e in esempi]
    nuovi = _giudizi(esempi, "s", lambda e: 0.9 if e.label else 0.1)

    r = build_report(esempi, vecchi + nuovi, PROTOCOLLO).estimators["s"]

    assert r.n_failed_judgments == 0 and r.n_scored == 8


def test_si_misura_anche_solo_sui_mutanti_e_solo_sugli_agenti():
    # Giudica bene i mutanti e male gli agenti.
    r = _rapporto("s", lambda e: (0.9 if e.label else 0.1) if e.origin == "mutante" else 0.5)

    assert r.auroc_mutants == 1.0
    assert r.auroc_agents is None          # nei dati sintetici gli agenti sono tutti corretti: manca una classe


def test_costo_e_latenza_si_sommano_e_si_riportano_ogni_mille_giudizi():
    r = _rapporto("s", lambda e: 0.5, costo=0.002, latenza=0.5)

    assert r.cost_usd == pytest.approx(0.08) and r.cost_per_1000 == pytest.approx(2.0)
    assert r.mean_latency_s == pytest.approx(0.5)


def test_senza_una_delle_due_classi_l_auroc_non_si_misura_ma_non_cade_tutto():
    esempi = [e for e in _esempi() if e.label == 1]

    r = build_report(esempi, _giudizi(esempi, "s", lambda e: 0.9), PROTOCOLLO).estimators["s"]

    assert r.auroc is None and r.auroc_low is None and r.brier == pytest.approx(0.01)


# -- La regola di D21 ----------------------------------------------------------------

def _er(nome, auroc, low, high):
    return EstimatorReport(nome, 10, 10, 0, 1, auroc, low, high, 0.1, 0.1)


@pytest.mark.parametrize("p, r, atteso", [
    ((0.85, 0.75, 0.93), (0.90, 0.85, 0.95), "promettente"),
    ((0.80, 0.70, 0.90), (0.90, 0.80, 0.97), "promettente"),         # bordi: limite 0,70 e scarto 0,10 esatti
    ((0.78, 0.74, 0.90), (0.92, 0.85, 0.97), "inconcludente"),        # lo scarto dal riferimento e' 0,14
    ((0.80, 0.69, 0.90), (0.90, 0.80, 0.97), "inconcludente"),        # il limite inferiore e' sotto 0,70
    ((0.55, 0.45, 0.65), (0.90, 0.80, 0.97), "negativo"),             # il limite superiore e' 0,65 esatto
    ((0.60, 0.40, 0.90), (0.90, 0.80, 0.97), "inconcludente"),        # incerto, non debole
])
def test_la_regola_nelle_sue_zone_e_ai_bordi(p, r, atteso):
    d = decide(_er("d1_hosted_plain", *p), _er("frontier", *r), PROTOCOLLO)

    assert isinstance(d, Decision) and d.verdict == atteso and d.reason


def test_senza_il_riferimento_si_puo_dire_negativo_ma_non_promettente():
    debole = decide(_er("d1_hosted_plain", 0.55, 0.45, 0.62), None, PROTOCOLLO)
    forte = decide(_er("d1_hosted_plain", 0.90, 0.85, 0.95), None, PROTOCOLLO)

    assert debole.verdict == "negativo"
    assert forte.verdict == "non_valutabile" and "riferimento" in forte.reason


def test_senza_misure_del_primario_non_si_decide():
    assert decide(None, _er("frontier", 0.9, 0.8, 0.95), PROTOCOLLO).verdict == "non_valutabile"
    assert decide(_er("d1_hosted_plain", None, None, None), _er("frontier", 0.9, 0.8, 0.95),
                  PROTOCOLLO).verdict == "non_valutabile"


def test_il_rapporto_applica_la_regola_al_primario_e_al_riferimento_del_protocollo():
    esempi = _esempi()
    giudizi = (_giudizi(esempi, "d1_hosted_plain", lambda e: 0.9 if e.label else 0.1)
               + _giudizi(esempi, "frontier", lambda e: 0.95 if e.label else 0.05)
               + _giudizi(esempi, "d1_hosted_criteria", lambda e: 0.5))

    rapporto = build_report(esempi, giudizi, PROTOCOLLO)

    assert rapporto.decision.verdict == "promettente"
    assert set(rapporto.estimators) == {"d1_hosted_plain", "frontier", "d1_hosted_criteria"}
    assert rapporto.dataset["esempi"] == 40 and rapporto.dataset["esercizi"] == 10


def test_il_markdown_riporta_stimatori_numeri_e_verdetto():
    esempi = _esempi()
    giudizi = (_giudizi(esempi, "d1_hosted_plain", lambda e: 0.9 if e.label else 0.1)
               + _giudizi(esempi, "frontier", lambda e: 0.95 if e.label else 0.05))

    testo = render_markdown(build_report(esempi, giudizi, PROTOCOLLO), PROTOCOLLO)

    for atteso in ("d1_hosted_plain", "frontier", "AUROC", "Brier", "ECE", "promettente", "1.00"):
        assert atteso in testo


# -- Controllo di origine (esplorativo, D27) -----------------------------------------

def test_il_controllo_di_origine_confronta_originali_e_mutanti_equivalenti_fra_i_soli_corretti():
    """Se lo stimatore da' di piu' agli originali che ai mutanti equivalenti, parte del segnale e' l'origine."""
    r = _rapporto("s", lambda e: 0.9 if e.origin == "agente" else (0.7 if e.label else 0.2))

    assert r.auroc_origin_control == 1.0


def test_senza_effetto_origine_il_controllo_vale_mezzo():
    r = _rapporto("s", lambda e: 0.8 if e.label else 0.2)

    assert r.auroc_origin_control == 0.5


def test_il_controllo_non_si_misura_senza_mutanti_equivalenti():
    esempi = [e for e in _esempi() if not (e.origin == "mutante" and e.label == 1)]

    r = build_report(esempi, _giudizi(esempi, "s", lambda e: 0.9 if e.label else 0.1), PROTOCOLLO).estimators["s"]

    assert r.auroc_origin_control is None


def test_il_markdown_dichiara_che_il_controllo_di_origine_e_esplorativo_e_non_decide():
    esempi = _esempi()
    giudizi = _giudizi(esempi, "d1_hosted_plain", lambda e: 0.9 if e.label else 0.1)

    testo = render_markdown(build_report(esempi, giudizi, PROTOCOLLO), PROTOCOLLO)

    assert "Origine" in testo and "esplorativ" in testo and "non decide" in testo


# -- Confronto sugli stessi esempi (D28) -------------------------------------------

def test_con_un_sottoinsieme_si_misura_solo_su_quegli_esempi_ma_il_costo_resta_tutto():
    esempi = _esempi()
    sottoinsieme = {e.example_id for e in esempi if e.task_id in ("t0", "t1", "t2")}
    giudizi = _giudizi(esempi, "s", lambda e: 0.9 if e.label else 0.1, costo=0.01)

    r = build_report(esempi, giudizi, PROTOCOLLO, only_examples=sottoinsieme).estimators["s"]

    assert r.n_examples == len(sottoinsieme) == 12 and r.n_scored == 12
    assert r.cost_usd == pytest.approx(0.40)                 # tutto cio' che e' stato speso, 40 giudizi
    assert r.cost_per_1000 == pytest.approx(10.0)            # ma ogni mille giudizi si misura sul sottoinsieme


def test_un_giudizio_fuori_dal_sottoinsieme_non_entra_nelle_misure():
    esempi = _esempi()
    sottoinsieme = {e.example_id for e in esempi if e.task_id == "t0"}
    dentro = _giudizi([e for e in esempi if e.task_id == "t0"], "s", lambda e: 0.9 if e.label else 0.1)
    fuori = _giudizi([e for e in esempi if e.task_id != "t0"], "s", lambda e: 0.5)

    r = build_report(esempi, dentro + fuori, PROTOCOLLO, only_examples=sottoinsieme).estimators["s"]

    assert r.auroc == 1.0 and r.n_scored == 4


def test_il_markdown_dice_che_e_un_sottoinsieme_comune():
    esempi = _esempi()
    sottoinsieme = {e.example_id for e in esempi if e.task_id in ("t0", "t1")}
    giudizi = _giudizi(esempi, "d1_hosted_plain", lambda e: 0.9 if e.label else 0.1)

    testo = render_markdown(build_report(esempi, giudizi, PROTOCOLLO, only_examples=sottoinsieme), PROTOCOLLO)

    assert "stessi esempi" in testo and "8 esempi" in testo


def test_un_sottoinsieme_senza_nessun_esempio_e_un_errore():
    esempi = _esempi()

    with pytest.raises(ValueError, match="sottoinsieme"):
        build_report(esempi, _giudizi(esempi, "s", lambda e: 0.5), PROTOCOLLO, only_examples={"non-esiste"})
