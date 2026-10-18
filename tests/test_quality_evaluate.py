"""L'esecutore: un giudizio per riga, riprendibile, con un tetto di spesa che vale per tutto l'esperimento.

Nota di design (tesi):
    L'esecuzione costa denaro (il giudice frontier) e puo' fermarsi a meta' (rete, tetto,
    Mac che si spegne). Per questo ogni giudizio si scrive appena arriva, e rilanciando
    l'esecuzione non si rifa' cio' che c'e' gia': non si paga due volte lo stesso
    giudizio. Il tetto di spesa conta anche quello gia' speso nelle esecuzioni precedenti.
    Le righe le scrive un solo thread, il principale, come nella campagna parallela.
"""

import json
import threading

import pytest

from budget_guard import BudgetExceeded
from quality.dataset import Example
from quality.estimators import Estimate
from quality.evaluate import Judgment, read_judgments, run_evaluation


def _esempi(n=6):
    return [Example(f"e{i}", f"t{i // 2}", "agente", "istr", "x = 1", i % 2) for i in range(n)]


class Finto:
    """Uno stimatore finto: conta le chiamate (per thread sicuro) e risponde come gli si dice."""

    def __init__(self, name, costo=0.0, risposta=lambda e: 0.5, solleva=None):
        self.name, self.costo, self.risposta, self.solleva = name, costo, risposta, solleva
        self.chiamate, self.lock = [], threading.Lock()

    def estimate(self, example):
        with self.lock:
            self.chiamate.append(example.example_id)
        if self.solleva and self.solleva(example):
            raise BudgetExceeded("tetto")
        p = self.risposta(example)
        if p is None:
            return Estimate(None, self.costo, 0.01, error="HTTP 500")
        return Estimate(p, self.costo, 0.01, input_tokens=100)


def _corri(tmp_path, stimatori, rip=None, **kw):
    kw.setdefault("workers", 3)
    rip = rip or {nome: 1 for nome in stimatori}
    return run_evaluation(_esempi(), stimatori, rip, tmp_path / "r.jsonl", **kw)


def test_un_giudizio_per_esempio_stimatore_e_ripetizione(tmp_path):
    finto = Finto("a", costo=0.001)

    esito = _corri(tmp_path, {"a": finto}, {"a": 2})

    giudizi = read_judgments(tmp_path / "r.jsonl")
    assert len(giudizi) == 12 and esito.calls == {"a": 12} and esito.errors == {"a": 0}
    assert {(g.example_id, g.rep) for g in giudizi} == {(f"e{i}", r) for i in range(6) for r in (1, 2)}
    assert esito.cost_usd == pytest.approx(0.012)
    assert isinstance(giudizi[0], Judgment) and giudizi[0].input_tokens == 100


def test_le_righe_sono_json_validi_anche_con_molti_operai(tmp_path):
    _corri(tmp_path, {"a": Finto("a")}, {"a": 5}, workers=6)

    righe = (tmp_path / "r.jsonl").read_text().splitlines()
    assert len(righe) == 30 and all(json.loads(r)["estimator"] == "a" for r in righe)


def test_rilanciando_non_si_rifa_e_non_si_ripaga_cio_che_c_e_gia(tmp_path):
    primo, secondo = Finto("a", costo=0.01), Finto("a", costo=0.01)

    _corri(tmp_path, {"a": primo})
    esito = _corri(tmp_path, {"a": secondo})

    assert secondo.chiamate == [] and esito.calls == {"a": 0} and esito.skipped_done == 6
    assert esito.cost_usd == pytest.approx(0.06)          # la spesa precedente conta


def test_i_giudizi_senza_risposta_valida_si_riprovano_alla_ripresa(tmp_path):
    cattivo = Finto("a", risposta=lambda e: None if e.example_id == "e2" else 0.5)
    _corri(tmp_path, {"a": cattivo})
    buono = Finto("a")

    esito = _corri(tmp_path, {"a": buono})

    assert buono.chiamate == ["e2"] and esito.calls == {"a": 1}
    ultimi = {g.example_id: g for g in read_judgments(tmp_path / "r.jsonl")}
    assert ultimi["e2"].probability == 0.5 and ultimi["e2"].error is None      # vale l'ultimo


def test_gli_errori_si_contano_senza_fermare_gli_altri(tmp_path):
    finto = Finto("a", risposta=lambda e: None if e.example_id in ("e0", "e1") else 0.5)

    esito = _corri(tmp_path, {"a": finto})

    assert esito.calls == {"a": 6} and esito.errors == {"a": 2}
    assert sorted(g.error for g in read_judgments(tmp_path / "r.jsonl") if g.error) == ["HTTP 500"] * 2


def test_il_tetto_di_spesa_ferma_le_partenze_e_lo_dice(tmp_path):
    finto = Finto("a", costo=0.05)

    esito = _corri(tmp_path, {"a": finto}, workers=1, max_total_usd=0.12)

    assert len(finto.chiamate) == 3                       # 0, 0,05, 0,10 < 0,12; a 0,15 si ferma
    assert esito.stopped_by_budget and esito.cost_usd == pytest.approx(0.15)


def test_la_prenotazione_conta_i_giudizi_in_volo(tmp_path):
    """Tetto 0,05 e 0,02 prenotati per giudizio: mai piu' di tre insieme."""
    lock, stato = threading.Lock(), {"attivi": 0, "massimo": 0}

    class Lento(Finto):
        def estimate(self, example):
            with lock:
                stato["attivi"] += 1
                stato["massimo"] = max(stato["massimo"], stato["attivi"])
            import time
            time.sleep(0.03)
            with lock:
                stato["attivi"] -= 1
            return super().estimate(example)

    _corri(tmp_path, {"a": Lento("a")}, workers=5, max_total_usd=0.05, reserve_per_call_usd=0.02)

    assert stato["massimo"] == 3


def test_un_ordine_di_fermarsi_dello_stimatore_ferma_i_giudizi_successivi(tmp_path):
    finto = Finto("a", costo=0.01, solleva=lambda e: e.example_id == "e1")

    esito = _corri(tmp_path, {"a": finto}, workers=1)

    assert esito.stopped_by_budget
    assert {g.example_id for g in read_judgments(tmp_path / "r.jsonl")} == {"e0"}


def test_gli_stimatori_gratuiti_vanno_prima_cosi_il_tetto_non_li_affama(tmp_path):
    gratis, caro = Finto("gratis"), Finto("caro", costo=1.0)

    _corri(tmp_path, {"gratis": gratis, "caro": caro}, workers=1, max_total_usd=0.5)

    assert len(gratis.chiamate) == 6 and len(caro.chiamate) == 1


def test_senza_file_i_giudizi_sono_vuoti(tmp_path):
    assert read_judgments(tmp_path / "non-c-e.jsonl") == []


def test_un_numero_di_operai_non_valido_e_un_errore(tmp_path):
    with pytest.raises(ValueError):
        _corri(tmp_path, {"a": Finto("a")}, workers=0)
