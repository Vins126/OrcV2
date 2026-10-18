"""I mutanti: errori da manuale introdotti in una soluzione corretta.

Nota di design (tesi):
    Un mutante e' una soluzione sbagliata **fabbricata**: l'etichetta (sbagliata) non
    la dice una persona ma i test, eseguiti dopo. I guasti sono quelli tipici di chi
    programma: un confronto invertito, un limite spostato di uno, un `+` al posto di
    un `-`, una condizione negata. Sono meno naturali degli errori di un modello, e
    la tesi lo dichiara come limite. Esempio dalla prova del 14 ott 2026: il caso 6 di
    `is_prime`, `range(2, int(n ** 0.5))` al posto di `range(2, int(n ** 0.5) + 1)`.
"""

import ast

import pytest

from quality.mutants import Mutant, generate_mutants, normalize

PRIMO = """
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True
"""


def _sorgenti(mutanti):
    return {m.source for m in mutanti}


def _con_operatore(mutanti, nome):
    return [m for m in mutanti if m.operator == nome]


def test_il_confronto_si_inverte_e_il_limite_si_sposta():
    mutanti = generate_mutants(PRIMO)

    assert normalize(PRIMO).replace("n < 2", "n <= 2") in _sorgenti(mutanti)
    assert normalize(PRIMO).replace("n % i == 0", "n % i != 0") in _sorgenti(mutanti)


def test_togliere_il_piu_uno_dal_limite_e_un_mutante():
    """E' l'errore di una unita' sul limite: il caso 6 della prova su `is_prime`."""
    mutanti = generate_mutants(PRIMO)

    assert normalize(PRIMO).replace("int(n ** 0.5) + 1", "int(n ** 0.5) + 0") in _sorgenti(mutanti)


def test_un_operatore_aritmetico_si_scambia():
    mutanti = generate_mutants("def f(a, b):\n    return a + b\n")

    assert "def f(a, b):\n    return a - b" in _sorgenti(_con_operatore(mutanti, "arithmetic"))


def test_una_condizione_si_nega_e_un_and_diventa_or():
    mutanti = generate_mutants("def f(a, b):\n    if a and b:\n        return 1\n    return 0\n")

    sorgenti = _sorgenti(_con_operatore(mutanti, "boolean"))
    assert any("a or b" in s for s in sorgenti)
    assert any("not (a and b)" in s or "not a and b" in s for s in sorgenti)


def test_un_ritorno_si_altera():
    mutanti = generate_mutants("def f(a):\n    return a * 2\n")

    assert any("return None" in m.source for m in _con_operatore(mutanti, "return"))


def test_ogni_mutante_e_codice_valido_diverso_dall_originale_e_senza_doppioni():
    mutanti = generate_mutants(PRIMO)

    assert len(mutanti) >= 8
    originale = normalize(PRIMO)
    assert all(m.source != originale for m in mutanti)
    assert len(_sorgenti(mutanti)) == len(mutanti)
    for m in mutanti:
        ast.parse(m.source)                    # solleva se non e' Python valido


def test_ogni_mutante_porta_la_riga_e_il_tipo_del_guasto():
    mutanti = generate_mutants(PRIMO)

    assert all(isinstance(m, Mutant) and m.line >= 1 for m in mutanti)
    assert {m.operator for m in mutanti} == {"compare", "arithmetic", "constant", "boolean", "return"}


def test_stringhe_e_docstring_non_si_toccano():
    mutanti = generate_mutants('def f():\n    """Restituisce 3."""\n    return "x" + "y"\n')

    assert mutanti
    assert all("Restituisce 3." in m.source for m in mutanti)            # la docstring resta
    for m in mutanti:
        if m.operator != "return":                                       # `return None` toglie le stringhe
            assert "'x'" in m.source and "'y'" in m.source


def test_con_lo_stesso_seme_si_ottiene_lo_stesso_campione():
    primo = generate_mutants(PRIMO, seed=3, max_mutants=5)
    secondo = generate_mutants(PRIMO, seed=3, max_mutants=5)

    assert primo == secondo and len(primo) == 5


def test_il_campione_rispetta_il_massimo_e_non_inventa_mutanti():
    tutti = generate_mutants(PRIMO)
    campione = generate_mutants(PRIMO, seed=1, max_mutants=4)

    assert len(campione) == 4 and set(campione) <= set(tutti)
    assert len(generate_mutants(PRIMO, max_mutants=10_000)) == len(tutti)


def test_la_normalizzazione_e_idempotente_e_toglie_i_commenti():
    sporco = "def f(a):   # commento\n    return   a+1\n"

    assert normalize(sporco) == "def f(a):\n    return a + 1"
    assert normalize(normalize(sporco)) == normalize(sporco)


@pytest.mark.parametrize("codice", ["def f(:\n", "x = = 1", "for"])
def test_codice_non_valido_e_un_errore_parlante(codice):
    with pytest.raises(ValueError, match="Python"):
        generate_mutants(codice)
    with pytest.raises(ValueError, match="Python"):
        normalize(codice)


def test_una_funzione_senza_nulla_da_mutare_non_da_mutanti():
    assert generate_mutants("x = 'testo'\n") == []
