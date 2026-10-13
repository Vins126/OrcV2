"""Prova reale sui 34 esercizi: lo scheletro fallisce, la soluzione passa.

Non gira nella suite normale: servono Docker acceso, l'immagine `orc-sandbox` e
i dati scaricati (`python campaign.py fetch-polyglot`). Si lancia di proposito:

    ORC_INTEGRATION=1 venv/bin/python -m pytest -q tests/test_polyglot_integration.py

Senza questa prova, `f` potrebbe misurare un errore del test e non del modello:
se un esercizio non passasse nemmeno con la sua soluzione, o passasse senza
alcun lavoro, ogni fallimento (o successo) osservato non direbbe niente.
"""

import os
from pathlib import Path

import pytest

import config
from executors.docker import DockerExecutor
from polyglot import exercise_to_task, load_exercises

DATI = Path("campaigns/data/polyglot-python")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ORC_INTEGRATION") and DATI.is_dir()),
    reason="prova con Docker e dati scaricati: ORC_INTEGRATION=1 e `campaign.py fetch-polyglot`")


def _prepara(tmp_path, esercizio, *, soluzione_giusta):
    task = exercise_to_task(esercizio)
    for percorso, contenuto in task.files.items():
        destinazione = tmp_path / percorso
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        destinazione.write_text(contenuto)
    if soluzione_giusta:
        # La soluzione di riferimento prende il posto dello scheletro.
        (nome_stub,) = esercizio.solution_files
        (tmp_path / nome_stub).write_text(esercizio.reference_files[".meta/example.py"])
    return task


def _verifica(tmp_path, task):
    ex = DockerExecutor(str(tmp_path), image=config.DOCKER_IMAGE, network="none")
    return ex.run(task.verify)


ESERCIZI = load_exercises(DATI) if DATI.is_dir() else []


@pytest.mark.parametrize("esercizio", ESERCIZI, ids=lambda e: e.name)
def test_p4_lo_scheletro_fallisce_e_la_soluzione_di_riferimento_passa(tmp_path, esercizio):
    task = _prepara(tmp_path / "scheletro", esercizio, soluzione_giusta=False)
    assert _verifica(tmp_path / "scheletro", task)["exit_code"] != 0, "passa senza lavoro"

    task = _prepara(tmp_path / "soluzione", esercizio, soluzione_giusta=True)
    esito = _verifica(tmp_path / "soluzione", task)
    assert esito["exit_code"] == 0, esito["stdout"][-600:]


def test_p4b_un_conftest_che_fa_saltare_tutto_non_vale_come_successo(tmp_path):
    esercizio = next(e for e in ESERCIZI if e.name == "wordy")
    task = _prepara(tmp_path, esercizio, soluzione_giusta=False)
    (tmp_path / "conftest.py").write_text(
        "import pytest\n@pytest.fixture(autouse=True)\ndef _salta():\n    pytest.skip('trucco')\n")

    assert _verifica(tmp_path, task)["exit_code"] != 0


def test_p4c_un_pytest_py_nel_workspace_non_aggira_la_verifica(tmp_path):
    esercizio = next(e for e in ESERCIZI if e.name == "wordy")
    task = _prepara(tmp_path, esercizio, soluzione_giusta=False)       # scheletro: non risolve nulla
    (tmp_path / "pytest.py").write_text("import sys\nsys.exit(0)\n")
    (tmp_path / "_pytest").mkdir()
    (tmp_path / "_pytest" / "__init__.py").write_text("raise SystemExit(0)\n")

    assert _verifica(tmp_path, task)["exit_code"] != 0


def test_p4d_i_file_estranei_nel_workspace_non_rompono_una_soluzione_giusta(tmp_path):
    esercizio = next(e for e in ESERCIZI if e.name == "wordy")
    task = _prepara(tmp_path, esercizio, soluzione_giusta=True)
    (tmp_path / "appunti.txt").write_text("note dell'agente")
    (tmp_path / "pytest.py").write_text("import sys\nsys.exit(1)\n")      # e' ostile anche al contrario

    assert _verifica(tmp_path, task)["exit_code"] == 0
