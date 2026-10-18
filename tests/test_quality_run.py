"""Costruzione degli stimatori e riga di comando: niente sorprese di spesa."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from quality import run
from quality.dataset import Example, write_examples
from quality.estimators import D1Estimator, FrontierJudge, HeuristicEstimator
from quality.factory import ORDINE, build_estimators, frontier_gateway_maker
from quality.protocol import load_protocol

PERCORSO_PROTOCOLLO = Path(__file__).resolve().parents[1] / "quality" / "protocol.toml"
PROTOCOLLO = load_protocol(PERCORSO_PROTOCOLLO)


def test_gli_stimatori_si_costruiscono_nell_ordine_dal_piu_economico_al_piu_caro():
    nomi = ["frontier", "d1_hosted_plain", "heuristic", "d1_local_criteria"]

    stimatori = build_estimators(PROTOCOLLO, nomi, liquid_key="k", make_frontier_gateway=lambda: None)

    assert list(stimatori) == ["heuristic", "d1_local_criteria", "d1_hosted_plain", "frontier"]
    assert list(ORDINE)[-1] == "frontier"


def test_ogni_variante_di_d1_ha_il_suo_indirizzo_e_i_suoi_criteri():
    s = build_estimators(PROTOCOLLO, ["d1_local_plain", "d1_hosted_criteria"], liquid_key="chiave")

    assert isinstance(s["d1_local_plain"], D1Estimator) and isinstance(s["d1_hosted_criteria"], D1Estimator)
    assert s["d1_local_plain"]._url.startswith("http://127.0.0.1") and s["d1_local_plain"]._api_key is None
    assert s["d1_local_plain"]._criteria is None and s["d1_local_plain"]._model is None
    assert s["d1_hosted_criteria"]._url.startswith("https://api.liquid.ai")
    assert s["d1_hosted_criteria"]._api_key == "chiave" and s["d1_hosted_criteria"]._model == "d1"
    assert s["d1_hosted_criteria"]._criteria == PROTOCOLLO.criteria


def test_l_euristica_e_il_frontier_si_costruiscono():
    s = build_estimators(PROTOCOLLO, ["heuristic", "frontier"], make_frontier_gateway=lambda: None)

    assert isinstance(s["heuristic"], HeuristicEstimator) and isinstance(s["frontier"], FrontierJudge)


@pytest.mark.parametrize("nomi, kw, messaggio", [
    (["inventato"], {}, "sconosciuti"),
    (["d1_hosted_plain"], {}, "LIQUID_API_KEY"),
    (["frontier"], {}, "gateway"),
])
def test_richieste_incoerenti_sono_errori_prima_di_spendere(nomi, kw, messaggio):
    with pytest.raises(ValueError, match=messaggio):
        build_estimators(PROTOCOLLO, nomi, **kw)


def test_ogni_thread_del_frontier_chiede_il_suo_gateway_alla_fabbrica_con_il_modello_del_protocollo():
    viste = []

    class Fabbrica:
        registry = NS()

        def make_gateway(self, model, contabile, guardiano):
            viste.append((model, contabile, guardiano))
            return NS()

    gateway, contabile = frontier_gateway_maker(Fabbrica(), "opus-5-5")()

    assert viste[0][0] == "opus-5-5" and viste[0][1] is contabile and gateway is not None


# -- Riga di comando ------------------------------------------------------------------

def _dataset(tmp_path):
    esempi = [Example(f"e{i}", f"t{i // 2}", "agente", "istr", "def f():\n    pass" if i % 2 == 0 else "def f():\n    return 1",
                      i % 2) for i in range(6)]
    cartella = tmp_path / "ds"
    write_examples(cartella / "examples.jsonl", esempi)
    return cartella


def _nessuna_chiamata_vera(monkeypatch):
    """Rende impossibile, in un test, costruire stimatori a pagamento o leggere le chiavi vere."""
    def vietato(*a, **kw):
        raise AssertionError("un test non deve costruire stimatori, fabbriche o leggere il .env")

    monkeypatch.setattr(run, "build_estimators", vietato)
    monkeypatch.setattr("config.load_environment", vietato)
    monkeypatch.setattr("agent_factory.AgentFactory", vietato)


def _nessuna_chiamata_vera_tranne_euristica(monkeypatch):
    """Per i test che usano solo l'euristica: nessun `.env` letto e nessuna fabbrica costruita."""
    def vietato(*a, **kw):
        raise AssertionError("un test non deve leggere il .env ne' costruire fabbriche")

    monkeypatch.setattr("config.load_environment", vietato)
    monkeypatch.setattr("agent_factory.AgentFactory", vietato)


def test_evaluate_con_l_euristica_scrive_i_risultati_e_il_rapporto(tmp_path, capsys, monkeypatch):
    # L'euristica non ha bisogno di chiavi: il `.env` non si legge (se si leggesse, il test fallirebbe).
    monkeypatch.setattr("config.load_environment", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("il .env non va letto per l'euristica")))

    codice = run.main(["evaluate", "--dataset", str(_dataset(tmp_path)), "--out", str(tmp_path / "out"),
                       "--protocol", str(PERCORSO_PROTOCOLLO), "--only", "heuristic"])

    assert codice == 0
    righe = (tmp_path / "out" / "results.jsonl").read_text().splitlines()
    assert len(righe) == 6 and json.loads(righe[0])["estimator"] == "heuristic"
    assert (tmp_path / "out" / "report.md").exists() and (tmp_path / "out" / "report.json").exists()
    assert "Verdetto" in capsys.readouterr().out


def test_il_frontier_non_parte_senza_conferma_e_mostra_il_preventivo(tmp_path, capsys, monkeypatch):
    # Se la guardia si rompesse, il test deve fallire SENZA fare nessuna chiamata vera.
    _nessuna_chiamata_vera(monkeypatch)

    codice = run.main(["evaluate", "--dataset", str(_dataset(tmp_path)), "--out", str(tmp_path / "out"),
                       "--protocol", str(PERCORSO_PROTOCOLLO), "--only", "frontier"])

    errore = capsys.readouterr()
    assert codice == 2 and "PREVENTIVO" in errore.out and "CALCOLATI" in errore.out and "--yes" in errore.err
    assert not (tmp_path / "out" / "results.jsonl").exists()


def test_il_frontier_non_e_fra_gli_stimatori_di_default():
    parser_default = "heuristic,d1_local_plain,d1_local_criteria,d1_hosted_plain,d1_hosted_criteria"

    # 0,0207 e' il costo medio OSSERVATO su 17 giudizi (14 ott 2026): la stima iniziale (0,007) era sbagliata
    assert "frontier" not in parser_default and run.COSTO_STIMATO_FRONTIER_USD == 0.0207


def test_un_protocollo_non_valido_e_un_errore_prima_di_tutto(tmp_path, capsys, monkeypatch):
    _nessuna_chiamata_vera(monkeypatch)
    cattivo = tmp_path / "p.toml"
    cattivo.write_text("[state]\n")

    codice = run.main(["evaluate", "--dataset", str(_dataset(tmp_path)), "--protocol", str(cattivo),
                       "--out", str(tmp_path / "out")])

    assert codice == 2 and "protocollo" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


# -- Campione, tetto e sottoinsieme (D28) ------------------------------------------------

def _dataset_grande(tmp_path, n=40):
    esempi = [Example(f"e{i:02d}", f"t{i % 8}", "agente" if i % 3 else "mutante", "istr",
                      "def f():\n    pass" if i % 2 else "def f():\n    return 1", i % 2) for i in range(n)]
    cartella = tmp_path / "ds"
    write_examples(cartella / "examples.jsonl", esempi)
    return cartella


def test_con_sample_si_giudicano_solo_gli_esempi_del_campione_e_si_registra_quali(tmp_path, monkeypatch):
    _nessuna_chiamata_vera_tranne_euristica(monkeypatch)

    codice = run.main(["evaluate", "--dataset", str(_dataset_grande(tmp_path)), "--out", str(tmp_path / "out"),
                       "--protocol", str(PERCORSO_PROTOCOLLO), "--only", "heuristic",
                       "--sample", "10", "--sample-seed", "3"])

    assert codice == 0
    campione = json.loads((tmp_path / "out" / "sample.json").read_text())
    assert campione["n"] == 10 and campione["seed"] == 3 and len(campione["example_ids"]) == 10
    giudicati = {json.loads(r)["example_id"] for r in (tmp_path / "out" / "results.jsonl").read_text().splitlines()}
    assert giudicati == set(campione["example_ids"])


def test_il_tetto_da_riga_di_comando_prevale_su_quello_del_protocollo_senza_toccarlo(tmp_path, monkeypatch):
    viste = {}
    monkeypatch.setattr(run, "run_evaluation", lambda *a, **kw: viste.update(kw) or run.EvaluationSummary(
        calls={}, errors={}, skipped_done=0, cost_usd=0.0, stopped_by_budget=False))
    _nessuna_chiamata_vera_tranne_euristica(monkeypatch)

    run.main(["evaluate", "--dataset", str(_dataset_grande(tmp_path)), "--out", str(tmp_path / "out"),
              "--protocol", str(PERCORSO_PROTOCOLLO), "--only", "heuristic", "--max-total-usd", "7.5"])

    assert viste["max_total_usd"] == 7.5 and PROTOCOLLO.max_total_usd == 4.0


def test_il_preventivo_del_frontier_conta_i_giudizi_del_campione_e_il_costo_osservato(tmp_path, capsys, monkeypatch):
    _nessuna_chiamata_vera(monkeypatch)

    run.main(["evaluate", "--dataset", str(_dataset_grande(tmp_path)), "--out", str(tmp_path / "out"),
              "--protocol", str(PERCORSO_PROTOCOLLO), "--only", "frontier", "--sample", "10"])

    uscita = capsys.readouterr().out
    assert "10 giudizi" in uscita and "0.0207" in uscita and "CALCOLATI" in uscita


def test_il_rapporto_puo_essere_calcolato_sugli_stessi_esempi_di_un_campione(tmp_path, capsys, monkeypatch):
    _nessuna_chiamata_vera_tranne_euristica(monkeypatch)
    dataset = _dataset_grande(tmp_path)
    run.main(["evaluate", "--dataset", str(dataset), "--out", str(tmp_path / "out"), "--protocol",
              str(PERCORSO_PROTOCOLLO), "--only", "heuristic"])
    campione = tmp_path / "out" / "sample.json"
    ids = [f"e{i:02d}" for i in range(0, 40, 4)]
    campione.write_text(json.dumps({"n": 10, "seed": 0, "example_ids": ids}))

    codice = run.main(["report", "--dataset", str(dataset), "--out", str(tmp_path / "out"),
                       "--protocol", str(PERCORSO_PROTOCOLLO), "--subset", str(campione)])

    assert codice == 0 and "10 esempi" in capsys.readouterr().out


def test_cascade_scrive_la_tabella_dai_giudizi_gia_raccolti_senza_nessuna_chiamata(tmp_path, capsys, monkeypatch):
    _nessuna_chiamata_vera(monkeypatch)
    from quality.evaluate import Judgment
    esempi = [Example(f"e{i:02d}", f"t{i // 4}", "mutante", "istr", "x", i % 2) for i in range(40)]
    cartella = tmp_path / "ds"
    write_examples(cartella / "examples.jsonl", esempi)
    out = tmp_path / "out"
    out.mkdir()
    righe = []
    for e in esempi:
        vero = 0.9 if e.label else 0.1
        righe.append(Judgment(e.example_id, "d1_hosted_plain", 1, vero if e.example_id < "e30" else 0.5, None, 0.00002, 0.2, 100))
        righe.append(Judgment(e.example_id, "frontier", 1, vero, None, 0.02, 7.0, None))
    (out / "results.jsonl").write_text("\n".join(json.dumps(j.__dict__) for j in righe) + "\n")

    codice = run.main(["cascade", "--dataset", str(cartella), "--out", str(out)])

    uscita = capsys.readouterr().out
    assert codice == 0 and (out / "cascade.md").exists() and (out / "cascade.json").exists()
    assert "costoso da solo" in uscita and "cascata (tolleranza 0.02)" in uscita


def test_cascade_senza_esempi_giudicati_da_entrambi_e_un_errore(tmp_path, capsys, monkeypatch):
    _nessuna_chiamata_vera(monkeypatch)
    cartella = _dataset(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "results.jsonl").write_text("")

    assert run.main(["cascade", "--dataset", str(cartella), "--out", str(out)]) == 2
