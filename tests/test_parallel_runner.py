"""L'esecutore concorrente: ordine, concorrenza vera, errori isolati, partenze governate.

Nota di design (tesi):
    L'esecutore non ha una coda propria: il gruppo di thread ne ha gia' una (i
    lavori in piu' aspettano che un operaio si liberi). Quello che l'esecutore
    aggiunge e' **chi decide quando un lavoro parte**. Le partenze le governa il
    thread principale, uno alla volta, tramite `admit`: cosi' chi tiene i conti
    (la spesa, i lavori in volo) li aggiorna da un solo thread, senza lock.
"""

import threading
import time

import pytest

from parallel_runner import Admission, run_parallel

# Il fixture di altri moduli puo' sostituire `time.sleep`: la pausa vera si cattura qui.
dormi = time.sleep


def test_i_risultati_tornano_nell_ordine_di_partenza_anche_se_finiscono_al_contrario():
    ritardi = {0: 0.3, 1: 0.15, 2: 0.0}

    esiti = run_parallel([0, 1, 2], lambda j: (dormi(ritardi[j]), j * 10)[1], max_workers=3)

    assert [e.index for e in esiti] == [0, 1, 2]
    assert [e.result for e in esiti] == [0, 10, 20]


def test_i_lavori_girano_davvero_insieme():
    """La barriera si supera solo se tre lavori sono in corso nello stesso istante."""
    barriera = threading.Barrier(3)

    def lavoro(j):
        barriera.wait(timeout=5)
        return j

    esiti = run_parallel([0, 1, 2], lavoro, max_workers=3)

    assert all(e.error is None for e in esiti)


def test_non_ci_sono_mai_piu_lavori_contemporanei_di_max_workers():
    lock, stato = threading.Lock(), {"attivi": 0, "massimo": 0}

    def lavoro(_j):
        with lock:
            stato["attivi"] += 1
            stato["massimo"] = max(stato["massimo"], stato["attivi"])
        dormi(0.05)
        with lock:
            stato["attivi"] -= 1

    run_parallel(list(range(8)), lavoro, max_workers=3)

    assert stato["massimo"] == 3


def test_con_un_solo_operaio_i_lavori_girano_uno_alla_volta_e_in_ordine():
    visti = []

    run_parallel([0, 1, 2, 3], lambda j: visti.append(j), max_workers=1)

    assert visti == [0, 1, 2, 3]


def test_un_errore_in_un_lavoro_non_ferma_gli_altri():
    def lavoro(j):
        if j == 1:
            raise ValueError("guasto")
        return j

    esiti = run_parallel([0, 1, 2], lavoro, max_workers=2)

    assert [e.result for e in esiti] == [0, None, 2]
    assert isinstance(esiti[1].error, ValueError)
    assert all(e.started for e in esiti)


@pytest.mark.parametrize("n", [0, -1])
def test_un_numero_di_operai_non_valido_e_un_errore_prima_di_ogni_effetto(n):
    chiamate = []

    with pytest.raises(ValueError, match="max_workers"):
        run_parallel([1, 2], chiamate.append, max_workers=n)

    assert chiamate == []


def test_senza_lavori_il_risultato_e_vuoto():
    assert run_parallel([], lambda j: j, max_workers=4) == []


def test_con_piu_operai_che_lavori_va_bene():
    assert [e.result for e in run_parallel([1, 2], lambda j: j + 1, max_workers=10)] == [2, 3]


# -- Chi governa le partenze ----------------------------------------------------

def test_admit_e_on_done_girano_sul_thread_principale():
    thread_admit, thread_done = set(), set()

    def admit(_job, _in_volo):
        thread_admit.add(threading.current_thread())
        return Admission.START

    def on_done(_esito):
        thread_done.add(threading.current_thread())

    run_parallel([0, 1, 2], lambda j: j, max_workers=2, admit=admit, on_done=on_done)

    principale = threading.current_thread()
    assert thread_admit == {principale} and thread_done == {principale}


def test_admit_riceve_il_numero_di_lavori_in_volo():
    visti = []

    def admit(_job, in_volo):
        visti.append(in_volo)
        return Admission.START

    run_parallel(list(range(4)), lambda _j: dormi(0.05), max_workers=2, admit=admit)

    assert visti[0] == 0 and max(visti) <= 1       # prima di partire ce ne sono al massimo uno


def test_stop_ferma_le_nuove_partenze_ma_non_i_lavori_in_corso():
    avviati = []

    def admit(_job, _in_volo):
        if len(avviati) >= 3:
            return Admission.STOP
        avviati.append(1)
        return Admission.START

    esiti = run_parallel(list(range(5)), lambda j: j, max_workers=2, admit=admit)

    assert [e.started for e in esiti] == [True, True, True, False, False]
    assert [e.result for e in esiti[:3]] == [0, 1, 2]


def test_wait_aspetta_che_un_lavoro_in_volo_finisca_e_poi_richiede():
    """Con `WAIT` finche' c'e' un lavoro in volo i lavori vanno uno alla volta, ma partono tutti."""
    lock, stato = threading.Lock(), {"attivi": 0, "massimo": 0}

    def admit(_job, in_volo):
        return Admission.WAIT if in_volo >= 1 else Admission.START

    def lavoro(_j):
        with lock:
            stato["attivi"] += 1
            stato["massimo"] = max(stato["massimo"], stato["attivi"])
        dormi(0.03)
        with lock:
            stato["attivi"] -= 1

    esiti = run_parallel(list(range(4)), lavoro, max_workers=3, admit=admit)

    assert stato["massimo"] == 1 and all(e.started for e in esiti)


def test_wait_senza_lavori_in_volo_equivale_a_stop_e_non_si_blocca():
    esiti = run_parallel([0, 1], lambda j: j, max_workers=2, admit=lambda _j, _n: Admission.WAIT)

    assert [e.started for e in esiti] == [False, False]


def test_on_done_riceve_un_esito_per_ogni_lavoro_avviato_e_nessuno_per_gli_altri():
    visti = []

    def admit(job, _in_volo):
        return Admission.START if job < 2 else Admission.STOP

    run_parallel(list(range(4)), lambda j: j, max_workers=1, admit=admit, on_done=visti.append)

    assert sorted(e.index for e in visti) == [0, 1]


# -- rilievi della revisione del 17 ott -------------------------------------

def test_se_on_done_solleva_le_run_in_volo_finiscono_e_arrivano_tutte_a_on_done():
    """Ogni run partita deve arrivare a `on_done` (che scrive il manifesto), poi l'errore risale."""
    viste: list[int] = []

    def on_done(esito):
        viste.append(esito.index)
        if esito.index == 0:
            raise OSError("manifesto non scrivibile")

    ritardi = {0: 0.0, 1: 0.2, 2: 0.2}
    with pytest.raises(OSError):
        run_parallel([0, 1, 2], lambda j: dormi(ritardi[j]), max_workers=3, on_done=on_done)

    assert sorted(viste) == [0, 1, 2]


def test_un_interruzione_durante_l_attesa_non_fa_partire_altro_e_registra_le_run_in_volo(monkeypatch):
    import parallel_runner
    viste: list[int] = []
    vero_wait = parallel_runner.wait
    chiamate = {"n": 0}

    def wait_interrotto(*a, **k):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            raise KeyboardInterrupt         # come un Ctrl+C mentre si aspetta
        return vero_wait(*a, **k)

    monkeypatch.setattr(parallel_runner, "wait", wait_interrotto)
    with pytest.raises(KeyboardInterrupt):
        run_parallel(list(range(5)), lambda j: dormi(0.1), max_workers=2,
                     on_done=lambda e: viste.append(e.index))

    assert sorted(viste) == [0, 1]          # le due in volo sono registrate, nessuna nuova e' partita
