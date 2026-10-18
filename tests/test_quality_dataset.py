"""Dal manifesto di una campagna agli esempi da giudicare.

Nota di design (tesi):
    Lo stimatore vede **istruzioni e codice**, mai i test ne' il loro esito (decisione
    D20). L'etichetta viene da `success` del manifesto: incarico completato **e**
    verifica con exit 0, la stessa definizione di `f` della campagna. Una run che non
    diventa un esempio resta nell'elenco degli scartati con il suo motivo.
"""

import json
import os
from pathlib import Path

import pytest

from polyglot import Exercise, load_exercises
from quality.dataset import Example, build_agent_examples, read_examples, solution_text, write_examples


def _esercizio(nome="due-secchi", istruzioni="Measure exactly N litres.", file="due_secchi.py"):
    return Exercise(name=nome, instructions=istruzioni, solution_files={file: "def misura():\n    pass\n"},
                    test_files={f"{file[:-3]}_test.py": "SECRET TEST"}, reference_files={})


def _riga(tmp_path, task="due-secchi", rep=1, run="r1", success=True, status="completed",
          codice="def misura():  # commento\n    return 4\n", file="due_secchi.py", scrivi=True):
    workspace = tmp_path / "ws" / f"{task}-{rep}"
    if scrivi:
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / file).write_text(codice)
        (workspace / f"{file[:-3]}_test.py").write_text("SECRET TEST\nassert misura() == 4\n")
    return {"task_id": task, "rep": rep, "run_id": run, "agent_id": f"a-{run}", "model": "m",
            "workspace": str(workspace), "status": status, "verified": success, "success": success,
            "total_cost": 0.01, "error_type": None}


def _manifesto(tmp_path, righe):
    percorso = tmp_path / "campagna.jsonl"
    percorso.write_text("\n".join(json.dumps(r) for r in [{"environment": {"image": "x"}}, *righe]) + "\n")
    return percorso


def test_una_run_diventa_un_esempio_con_istruzioni_codice_ed_etichetta(tmp_path):
    manifesto = _manifesto(tmp_path, [_riga(tmp_path, success=True)])

    esempi, scartati = build_agent_examples(manifesto, {"due-secchi": _esercizio()})

    assert scartati == []
    (e,) = esempi
    assert (e.example_id, e.task_id, e.origin, e.label) == ("agente:r1", "due-secchi", "agente", 1)
    assert e.instructions == "Measure exactly N litres."
    assert e.solution == "def misura():\n    return 4"          # normalizzato: senza il commento
    assert e.base_run_id == "r1" and e.operator is None


def test_una_run_fallita_ha_etichetta_zero_anche_se_l_incarico_e_finito_male(tmp_path):
    righe = [_riga(tmp_path, run="r1", success=False, status="completed"),
             _riga(tmp_path, rep=2, run="r2", success=False, status="max_iterations")]

    esempi, _ = build_agent_examples(_manifesto(tmp_path, righe), {"due-secchi": _esercizio()})

    assert [e.label for e in esempi] == [0, 0]


def test_lo_stimatore_non_vede_mai_i_test(tmp_path):
    manifesto = _manifesto(tmp_path, [_riga(tmp_path)])

    (e,), _ = build_agent_examples(manifesto, {"due-secchi": _esercizio()})

    testo = json.dumps(e.__dict__)
    assert "SECRET TEST" not in testo and "assert misura()" not in testo


@pytest.mark.parametrize("stato", ["build_failed", "setup_failed"])
def test_i_guasti_della_campagna_non_sono_esempi_e_restano_elencati(tmp_path, stato):
    riga = _riga(tmp_path, success=False, status=stato, scrivi=False)

    esempi, scartati = build_agent_examples(_manifesto(tmp_path, [riga]), {"due-secchi": _esercizio()})

    assert esempi == []
    assert [(s.task_id, s.reason) for s in scartati] == [("due-secchi", "guasto_della_campagna")]


def test_una_soluzione_mancante_un_esercizio_sconosciuto_e_codice_non_valido_si_scartano_col_motivo(tmp_path):
    righe = [_riga(tmp_path, run="r1", scrivi=False),
             _riga(tmp_path, task="altro", run="r2"),
             _riga(tmp_path, rep=3, run="r3", codice="def f(:\n")]

    esempi, scartati = build_agent_examples(_manifesto(tmp_path, righe), {"due-secchi": _esercizio()})

    assert esempi == []
    assert {(s.run_id, s.reason) for s in scartati} == {
        ("r1", "soluzione_mancante"), ("r2", "esercizio_sconosciuto"), ("r3", "non_valida")}


def test_con_piu_file_ognuno_ha_la_sua_intestazione_in_ordine_stabile():
    testo = solution_text({"b.py": "y = 2\n", "a.py": "x = 1  # uno\n"})

    assert testo == "# FILE: a.py\nx = 1\n\n# FILE: b.py\ny = 2"


def test_con_un_solo_file_non_c_e_intestazione():
    assert solution_text({"a.py": "x = 1\n"}) == "x = 1"


def test_gli_esempi_si_scrivono_e_si_rileggono_identici(tmp_path):
    esempi = [Example("agente:r1", "t", "agente", "istr", "x = 1", 1, "r1"),
              Example("mutante:r1:0", "t", "mutante", "istr", "x = 2", None, "r1", "constant", 3)]
    percorso = tmp_path / "out" / "esempi.jsonl"

    write_examples(percorso, esempi)

    assert read_examples(percorso) == esempi


@pytest.mark.skipif(
    not (os.environ.get("ORC_INTEGRATION") and Path("runs/campaigns/m2s-m3-completa.jsonl").exists()
         and Path("campaigns/data/polyglot-python").is_dir()),
    reason="dati veri: ORC_INTEGRATION=1, la campagna M3 in runs/ e gli esercizi scaricati")
def test_sulla_campagna_vera_di_m3_ci_sono_102_esempi_di_cui_3_sbagliati():
    esercizi = {e.name: e for e in load_exercises(Path("campaigns/data/polyglot-python"))}

    esempi, scartati = build_agent_examples(Path("runs/campaigns/m2s-m3-completa.jsonl"), esercizi)

    assert scartati == []
    assert len(esempi) == 102 and sum(e.label == 0 for e in esempi) == 3
    assert len({e.task_id for e in esempi}) == 34
