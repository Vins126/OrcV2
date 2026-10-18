"""Il campione per il giudice costoso: bilanciato, riproducibile, con gli esempi rari sempre dentro.

Nota di design (tesi):
    Il giudice frontier costa circa 20 millesimi di dollaro a giudizio, tre volte la stima
    iniziale (il modello ragiona, e la richiesta scrive in cache): giudicare tutti i 498
    esempi costerebbe circa 9-10 dollari. Si giudica un campione e **tutti gli stimatori si
    confrontano sugli stessi esempi**. Il criterio (classi bilanciate, strati rari sempre
    dentro) e' scritto qui, prima di vedere i giudizi del frontier.
"""

import pytest

from quality.dataset import Example
from quality.sample import stratified_sample


def _dataset():
    """Come il dataset vero in piccolo: pochi sbagliati fra gli agenti, pochi mutanti equivalenti."""
    esempi = []
    for i in range(30):
        esempi.append(Example(f"ac{i}", f"t{i % 6}", "agente", "i", f"a{i}", 1, f"r{i}"))
    for i in range(3):
        esempi.append(Example(f"aw{i}", f"t{i}", "agente", "i", f"w{i}", 0, f"r{i}"))
    for i in range(8):
        esempi.append(Example(f"mc{i}", f"t{i % 6}", "mutante", "i", f"c{i}", 1, f"r{i}", "compare", 1))
    for i in range(90):
        esempi.append(Example(f"mw{i}", f"t{i % 6}", "mutante", "i", f"m{i}", 0, f"r{i}", "constant", 1))
    return esempi


def _conta(campione, origine, etichetta):
    return sum(e.origin == origine and e.label == etichetta for e in campione)


def test_il_campione_ha_la_dimensione_chiesta_e_le_classi_bilanciate():
    campione = stratified_sample(_dataset(), 40, seed=1)

    assert len(campione) == 40
    assert sum(e.label == 1 for e in campione) == 20 and sum(e.label == 0 for e in campione) == 20


def test_gli_strati_rari_ci_sono_sempre_tutti():
    campione = stratified_sample(_dataset(), 40, seed=1)

    assert _conta(campione, "agente", 0) == 3            # tutte le soluzioni sbagliate degli agenti
    assert _conta(campione, "mutante", 1) == 8           # tutti i mutanti equivalenti
    assert _conta(campione, "agente", 1) == 12 and _conta(campione, "mutante", 0) == 17


def test_stesso_seme_stesso_campione_seme_diverso_campione_diverso():
    primo = stratified_sample(_dataset(), 40, seed=3)

    assert primo == stratified_sample(_dataset(), 40, seed=3)
    assert {e.example_id for e in primo} != {e.example_id for e in stratified_sample(_dataset(), 40, seed=4)}


def test_nessun_doppione_e_l_ordine_e_quello_del_dataset():
    dataset = _dataset()
    campione = stratified_sample(dataset, 40, seed=2)

    ids = [e.example_id for e in campione]
    assert len(set(ids)) == 40
    assert ids == [e.example_id for e in dataset if e.example_id in set(ids)]


def test_con_n_piu_grande_del_dataset_si_restituisce_tutto():
    assert len(stratified_sample(_dataset(), 10_000)) == len(_dataset())


def test_con_n_piccolo_resta_valido_e_bilanciato():
    campione = stratified_sample(_dataset(), 6, seed=0)

    assert len(campione) == 6 and sum(e.label == 1 for e in campione) == 3


def test_se_una_classe_e_piccola_si_prende_tutta_e_il_resto_va_all_altra():
    dataset = [e for e in _dataset() if e.label == 0 or e.origin == "mutante"]      # niente agenti corretti
    dataset = [e for e in dataset if not (e.label == 1 and e.origin == "mutante") or e.example_id in ("mc0", "mc1")]

    campione = stratified_sample(dataset, 30, seed=1)

    assert sum(e.label == 1 for e in campione) == 2 and len(campione) == 30


@pytest.mark.parametrize("n", [0, -5])
def test_n_non_positivo_e_un_errore(n):
    with pytest.raises(ValueError):
        stratified_sample(_dataset(), n)


def test_un_esempio_senza_etichetta_e_un_errore():
    with pytest.raises(ValueError, match="etichetta"):
        stratified_sample([Example("x", "t", "mutante", "i", "s", None)], 1)
