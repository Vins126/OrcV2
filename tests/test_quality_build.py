"""Il dataset completo: soluzioni degli agenti, mutanti ed etichette, con un riepilogo da controllare."""

import json
import threading
from pathlib import Path

import pytest

from polyglot import Exercise
from quality.build import build_dataset
from quality.dataset import read_examples

CODICE = "def misura(a, b):\n    if a < b:\n        return a + 1\n    return b\n"


def _esercizio():
    return Exercise("due-secchi", "Measure.", {"misura.py": "pass\n"}, {"misura_test.py": "TEST\n"}, {})


def _manifesto(tmp_path):
    righe: list[dict] = [{"environment": {"image": "x"}}]
    for rep, ok in ((1, True), (2, True), (3, False)):
        ws = tmp_path / "ws" / f"a{rep}"
        ws.mkdir(parents=True)
        (ws / "misura.py").write_text(CODICE)
        righe.append({"task_id": "due-secchi", "rep": rep, "run_id": f"r{rep}", "workspace": str(ws),
                      "status": "completed", "success": ok, "verified": ok, "total_cost": 0.0})
    percorso = tmp_path / "campagna.jsonl"
    percorso.write_text("\n".join(json.dumps(r) for r in righe) + "\n")
    return percorso


class Shell:
    """Una shell finta: i test falliscono se il codice contiene `<=` o `a + 2`."""

    def __init__(self):
        self.lock, self.chiamate = threading.Lock(), 0

    def __call__(self, workspace, comando):
        codice = (workspace / "misura.py").read_text()
        with self.lock:
            self.chiamate += 1
        return 1 if ("<=" in codice or "a + 2" in codice) else 0


def _costruisci(tmp_path, **kwargs):
    kwargs.setdefault("per_solution", 3)
    return build_dataset(_manifesto(tmp_path), {"due-secchi": _esercizio()}, tmp_path / "out", seed=1,
                         workers=2, shell=Shell(), workspace_root=tmp_path / "tmp", **kwargs)


def test_il_dataset_ha_le_soluzioni_degli_agenti_piu_i_mutanti_etichettati(tmp_path):
    riepilogo = _costruisci(tmp_path)

    esempi = read_examples(tmp_path / "out" / "examples.jsonl")
    assert {e.origin for e in esempi} == {"agente", "mutante"}
    assert all(e.label in (0, 1) for e in esempi)
    assert riepilogo["esempi"] == len(esempi)
    # tre soluzioni degli agenti (due giuste, una sbagliata); i mutanti nascono solo dalle due giuste
    assert sum(e.origin == "agente" for e in esempi) == 3
    assert {e.base_run_id for e in esempi if e.origin == "mutante"} == {"r1", "r2"}
    assert sum(e.origin == "mutante" for e in esempi) == 6               # 3 per soluzione corretta


def test_il_riepilogo_dice_cio_che_serve_per_fidarsi_delle_misure(tmp_path):
    riepilogo = _costruisci(tmp_path)

    assert riepilogo["esercizi"] == 1
    assert riepilogo["per_origine_ed_etichetta"]["agente:corretto"] == 2
    assert riepilogo["per_origine_ed_etichetta"]["agente:sbagliato"] == 1
    assert sum(riepilogo["mutanti_per_operatore"].values()) == 6
    assert riepilogo["scartati_dalle_run"] == {} and riepilogo["mutanti_scaduti_di_tempo"] == 0
    assert json.loads((tmp_path / "out" / "summary.json").read_text()) == riepilogo


def test_non_si_sovrascrive_un_dataset_esistente(tmp_path):
    _costruisci(tmp_path)

    with pytest.raises(FileExistsError):
        _costruisci(tmp_path)


def test_lo_stesso_seme_da_lo_stesso_dataset(tmp_path):
    _costruisci(tmp_path / "uno")
    _costruisci(tmp_path / "due")

    uno = (tmp_path / "uno" / "out" / "examples.jsonl").read_text()
    due = (tmp_path / "due" / "out" / "examples.jsonl").read_text()
    assert uno.replace(str(tmp_path / "uno"), "") == due.replace(str(tmp_path / "due"), "")
