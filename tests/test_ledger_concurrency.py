"""M3.1b-a: il `RunLedger` resta coerente quando piu' thread lo scrivono insieme.

Oggi ogni ledger lo scrive un solo thread (il guardiano degli stalli chiude solo la
connessione), ma da M4 un ledger potra' essere condiviso: numeri di sequenza doppi o
righe mescolate renderebbero il dataset inutilizzabile.
"""

import json
import threading

from accounting.ledger import RunLedger
from accounting.record import UsageRecord

THREAD = 8
SCRITTURE = 50


def _record(i: int) -> UsageRecord:
    return UsageRecord(model="m", quantities={"input_tokens": i}, cost=0.001)


def _righe(path):
    # Ogni riga deve essere un JSON valido: una riga mescolata farebbe fallire `json.loads`.
    return [json.loads(riga) for riga in path.read_text(encoding="utf-8").splitlines()]


def _in_parallelo(funzione):
    via = threading.Barrier(THREAD)       # tutti partono insieme, per massimizzare le collisioni

    def corpo(t):
        via.wait()
        for i in range(SCRITTURE):
            funzione(t, i)

    thread = [threading.Thread(target=corpo, args=(t,)) for t in range(THREAD)]
    for x in thread:
        x.start()
    for x in thread:
        x.join()


def test_consumi_concorrenti_hanno_numeri_distinti_e_consecutivi_e_righe_intere(tmp_path):
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")

    _in_parallelo(lambda t, i: ledger.append_usage(_record(t * 1000 + i)))

    righe = _righe(ledger.run_dir / "usage.jsonl")
    assert len(righe) == THREAD * SCRITTURE
    assert sorted(r["sequence"] for r in righe) == list(range(1, THREAD * SCRITTURE + 1))
    # nessun consumo perso ne' duplicato
    assert sorted(r["record"]["quantities"]["input_tokens"] for r in righe) == sorted(
        t * 1000 + i for t in range(THREAD) for i in range(SCRITTURE))


def test_eventi_concorrenti_hanno_numeri_distinti_e_consecutivi_e_righe_intere(tmp_path):
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")

    _in_parallelo(lambda t, i: ledger.append_event("prova", {"t": t, "i": i}))

    righe = _righe(ledger.run_dir / "events.jsonl")
    assert len(righe) == THREAD * SCRITTURE
    assert sorted(r["sequence"] for r in righe) == list(range(1, THREAD * SCRITTURE + 1))


def test_la_numerazione_nel_file_segue_l_ordine_di_scrittura(tmp_path):
    """Numero e scrittura avvengono insieme: la riga n del file porta la sequenza n."""
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")

    _in_parallelo(lambda t, i: ledger.append_usage(_record(i)))

    sequenze = [r["sequence"] for r in _righe(ledger.run_dir / "usage.jsonl")]
    assert sequenze == list(range(1, THREAD * SCRITTURE + 1))


def test_close_durante_le_scritture_non_legge_righe_a_meta_e_conta_cio_che_c_era(tmp_path):
    """Il riepilogo deve contare esattamente le righe scritte prima della chiusura."""
    ledger = RunLedger(root=tmp_path, task="t", run_id="r")
    errori: list[BaseException] = []
    sommari: list[dict] = []
    smetti = threading.Event()

    def scrivi():
        while not smetti.is_set():
            ledger.append_usage(_record(1))

    scrittori = [threading.Thread(target=scrivi) for _ in range(4)]
    for s in scrittori:
        s.start()
    try:
        for _ in range(20):
            try:
                sommari.append(ledger.close(status="completed", iterations=1))
            except BaseException as e:   # un JSON a meta' qui darebbe JSONDecodeError
                errori.append(e)
    finally:
        smetti.set()
        for s in scrittori:
            s.join()

    assert errori == []
    conteggi = [s["usage_count"] for s in sommari]
    assert conteggi == sorted(conteggi)            # ogni chiusura vede almeno cio' che vedeva la prima
    for s in sommari:                              # totale coerente con il numero di righe viste
        assert abs(s["total_cost"] - 0.001 * s["usage_count"]) < 1e-9
