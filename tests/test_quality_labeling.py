"""I mutanti nascono da soluzioni corrette e prendono l'etichetta dai test, eseguiti davvero.

Nota di design (tesi):
    L'etichetta di un mutante non la dice una persona ne' uno stimatore: la dicono i
    **test dell'esercizio**, gli stessi della campagna, eseguiti nella stessa sandbox.
    Quello che gira e' esattamente il codice che lo stimatore ha visto: se la
    formattazione o la normalizzazione cambiassero il comportamento, l'etichetta non
    corrisponderebbe all'esempio. Un mutante che i test non scoprono resta un
    esempio "corretto" (equivalente, o test deboli): e' un'informazione, non un errore.
"""

import subprocess
import threading

import pytest

from polyglot import Exercise, exercise_to_task
from quality.dataset import Example
from quality.labeling import label_mutants, make_mutant_examples

CODICE = "def misura(a, b):\n    if a < b:\n        return a + 1\n    return b\n"


def _esercizio(nome="due-secchi"):
    return Exercise(name=nome, instructions="Measure.", solution_files={"misura.py": "pass\n"},
                    test_files={"misura_test.py": "TEST ORIGINALI\n"}, reference_files={})


def _agente(run="r1", task="due-secchi", etichetta=1, codice=CODICE):
    return Example(f"agente:{run}", task, "agente", "Measure.", codice, etichetta, run)


# -- Da soluzioni corrette a mutanti -----------------------------------------------

def test_i_mutanti_nascono_solo_dalle_soluzioni_corrette():
    esempi = [_agente("r1", etichetta=1), _agente("r2", etichetta=0)]

    mutanti = make_mutant_examples(esempi, {"due-secchi": _esercizio()}, per_solution=3)

    assert mutanti and {m.base_run_id for m in mutanti} == {"r1"}


def test_ogni_mutante_porta_i_dati_dell_origine_e_nessuna_etichetta():
    (agente,) = [_agente()]

    mutanti = make_mutant_examples([agente], {"due-secchi": _esercizio()}, per_solution=3)

    for n, m in enumerate(mutanti):
        assert (m.origin, m.label, m.task_id, m.instructions) == ("mutante", None, "due-secchi", "Measure.")
        assert m.example_id == f"mutante:r1:{n}" and m.operator and m.line
        assert m.solution != agente.solution


def test_il_numero_di_mutanti_per_soluzione_e_limitato_e_il_campione_e_riproducibile():
    esercizi = {"due-secchi": _esercizio()}

    primo = make_mutant_examples([_agente()], esercizi, per_solution=2, seed=5)
    secondo = make_mutant_examples([_agente()], esercizi, per_solution=2, seed=5)

    assert len(primo) == 2 and primo == secondo


def test_le_soluzioni_a_piu_file_non_generano_mutanti():
    esercizio = Exercise("multi", "x", {"a.py": "", "b.py": ""}, {"t.py": ""}, {})
    agente = _agente(task="multi", codice="# FILE: a.py\nx = 1\n\n# FILE: b.py\ny = 2")

    assert make_mutant_examples([agente], {"multi": esercizio}) == []


# -- Etichettare con i test -------------------------------------------------------

class ShellFinta:
    """Registra cosa vede in ogni workspace e risponde secondo il codice che trova."""

    def __init__(self, esito=lambda codice: 1 if "<=" in codice else 0):
        self.chiamate, self.lock, self.esito = [], threading.Lock(), esito

    def __call__(self, workspace, comando):
        codice = (workspace / "misura.py").read_text()
        with self.lock:
            self.chiamate.append({"codice": codice, "test": (workspace / "misura_test.py").read_text(),
                                  "comando": comando, "esisteva": workspace.is_dir()})
        r = self.esito(codice)
        if isinstance(r, BaseException):
            raise r
        return r


def _mutante(n, codice):
    return Example(f"mutante:r1:{n}", "due-secchi", "mutante", "Measure.", codice, None, "r1", "compare", 2)


def test_l_etichetta_viene_dai_test_eseguiti_sul_codice_esatto_che_lo_stimatore_ha_visto(tmp_path):
    giusto = _mutante(0, CODICE.replace("a + 1", "a + 1  "))      # nessun guasto vero: i test passano
    rotto = _mutante(1, CODICE.replace("a < b", "a <= b"))
    shell = ShellFinta()

    esito = label_mutants([giusto, rotto], {"due-secchi": _esercizio()}, shell=shell, workers=2,
                          workspace_root=tmp_path / "w")

    # exit code 0 = test passati = soluzione corretta = etichetta 1; diverso da 0 = sbagliata = 0
    etichette = {e.example_id: e.label for e in esito.examples}
    assert etichette["mutante:r1:0"] == 1 and etichette["mutante:r1:1"] == 0
    assert {c["codice"] for c in shell.chiamate} == {giusto.solution, rotto.solution}


def test_il_workspace_ha_i_test_originali_e_il_comando_e_quello_di_verifica_della_campagna(tmp_path):
    shell = ShellFinta()
    esercizio = _esercizio()

    label_mutants([_mutante(0, CODICE)], {"due-secchi": esercizio}, shell=shell, workers=1,
                  workspace_root=tmp_path / "w")

    (chiamata,) = shell.chiamate
    assert chiamata["test"] == "TEST ORIGINALI\n"
    assert chiamata["comando"] == exercise_to_task(esercizio).verify


def test_i_workspace_temporanei_si_cancellano_a_fine_lavoro(tmp_path):
    radice = tmp_path / "w"

    label_mutants([_mutante(0, CODICE), _mutante(1, CODICE)], {"due-secchi": _esercizio()},
                  shell=ShellFinta(), workers=2, workspace_root=radice)

    assert not radice.exists() or list(radice.iterdir()) == []


def test_un_mutante_che_non_finisce_in_tempo_ha_etichetta_zero_e_si_conta(tmp_path):
    shell = ShellFinta(esito=lambda codice: subprocess.TimeoutExpired("pytest", 60))

    esito = label_mutants([_mutante(0, CODICE)], {"due-secchi": _esercizio()}, shell=shell, workers=1,
                          workspace_root=tmp_path / "w")

    assert [e.label for e in esito.examples] == [0] and esito.timeouts == 1 and esito.errors == []


def test_un_guasto_dell_ambiente_lascia_il_mutante_senza_etichetta_e_non_ferma_gli_altri(tmp_path):
    def esito(codice):
        return OSError("docker spento") if "a + 1" in codice else 1

    mutanti = [_mutante(0, CODICE), _mutante(1, CODICE.replace("a + 1", "a + 2"))]

    risultato = label_mutants(mutanti, {"due-secchi": _esercizio()}, shell=ShellFinta(esito), workers=2,
                              workspace_root=tmp_path / "w")

    etichette = {e.example_id: e.label for e in risultato.examples}
    assert etichette["mutante:r1:0"] is None and etichette["mutante:r1:1"] == 0
    assert risultato.errors == [("mutante:r1:0", "OSError")]


def test_i_mutanti_tornano_nell_ordine_ricevuto_con_piu_operai(tmp_path):
    mutanti = [_mutante(i, CODICE.replace("a + 1", f"a + {i + 2}")) for i in range(8)]

    esito = label_mutants(mutanti, {"due-secchi": _esercizio()}, shell=ShellFinta(), workers=4,
                          workspace_root=tmp_path / "w")

    assert [e.example_id for e in esito.examples] == [m.example_id for m in mutanti]


def test_un_esempio_che_non_e_un_mutante_non_si_tocca(tmp_path):
    agente = _agente()
    shell = ShellFinta()

    esito = label_mutants([agente], {"due-secchi": _esercizio()}, shell=shell, workers=1,
                          workspace_root=tmp_path / "w")

    assert esito.examples == [agente] and shell.chiamate == []
