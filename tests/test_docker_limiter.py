"""M3.1b-c: limite ai container Docker contemporanei (scelta L, soluzione ibrida, fra processi).

Il limite riguarda una risorsa unica della macchina: per questo di default tutti gli
esecutori condividono una sola istanza di modulo, e i posti sono file bloccati con
`fcntl.flock`, cosi' il limite vale anche fra processi Python diversi (due campagne
lanciate da due terminali). Chi vuole puo' passare un limitatore proprio.
"""

import contextlib
import fcntl
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import config
from executors import docker as modulo
from executors.docker import ContainerLimiter, DockerExecutor

RADICE = Path(__file__).resolve().parent.parent


def _docker_lento(monkeypatch, durata=0.03):
    """`docker run` finto che conta quanti container sono vivi nello stesso istante."""
    stato = {"vivi": 0, "massimo": 0}
    lucchetto = threading.Lock()

    def finto(argomenti, **kwargs):
        with lucchetto:
            stato["vivi"] += 1
            stato["massimo"] = max(stato["massimo"], stato["vivi"])
        time.sleep(durata)
        with lucchetto:
            stato["vivi"] -= 1
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    return stato


def _lancia_in_parallelo(esecutori):
    thread = [threading.Thread(target=e.run, args=("true",)) for e in esecutori]
    for t in thread:
        t.start()
    for t in thread:
        t.join()


def _posto_occupato(cartella: Path, indice: int = 0) -> bool:
    """Guarda dall'esterno, con un descrittore proprio, se il posto e' bloccato."""
    fd = os.open(cartella / f"slot-{indice}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)                 # chiudere rilascia anche il lock appena preso
    return False


class EventiFinti:
    def __init__(self):
        self.eventi = []

    def append_event(self, event_type, details):
        self.eventi.append((event_type, details))


# -- il limitatore da solo --------------------------------------------------

@pytest.mark.parametrize("valore", [0, -1])
def test_un_limite_non_positivo_e_un_errore_e_non_crea_la_cartella(tmp_path, valore):
    with pytest.raises(ValueError):
        ContainerLimiter(valore, tmp_path / "posti")
    assert not (tmp_path / "posti").exists()


def test_il_posto_viene_rilasciato_anche_su_eccezione(tmp_path):
    limitatore = ContainerLimiter(1, tmp_path)
    with pytest.raises(RuntimeError):
        with limitatore.slot():
            assert _posto_occupato(tmp_path)
            raise RuntimeError("boom")
    assert not _posto_occupato(tmp_path)


def test_il_posto_restituisce_quanto_si_e_aspettato(tmp_path):
    limitatore = ContainerLimiter(1, tmp_path, poll_s=0.01)
    with limitatore.slot() as attesa:
        assert attesa < 0.05                       # posto libero: nessuna attesa

    preso = threading.Event()

    def tieni():
        with limitatore.slot():
            preso.set()
            time.sleep(0.2)

    t = threading.Thread(target=tieni)
    t.start()
    preso.wait()
    with limitatore.slot() as attesa:
        assert attesa >= 0.1
    t.join()


# -- dentro l'esecutore -----------------------------------------------------

def test_dieci_esecuzioni_con_limite_tre_non_superano_mai_tre(tmp_path, monkeypatch):
    stato = _docker_lento(monkeypatch)
    limitatore = ContainerLimiter(3, tmp_path / "posti", poll_s=0.005)
    esecutori = [DockerExecutor(str(tmp_path / f"w{i}"), limiter=limitatore) for i in range(10)]

    _lancia_in_parallelo(esecutori)

    assert stato["massimo"] == 3        # mai oltre il limite, e il limite viene davvero raggiunto


def test_due_limitatori_sulla_stessa_cartella_condividono_i_posti(tmp_path, monkeypatch):
    """E' cio' che fa valere il limite fra processi: i posti sono i file, non l'oggetto."""
    stato = _docker_lento(monkeypatch)
    a = ContainerLimiter(2, tmp_path / "posti", poll_s=0.005)
    b = ContainerLimiter(2, tmp_path / "posti", poll_s=0.005)
    esecutori = [DockerExecutor(str(tmp_path / f"w{i}"), limiter=(a if i % 2 else b)) for i in range(8)]

    _lancia_in_parallelo(esecutori)

    assert stato["massimo"] == 2


def test_il_limite_vale_fra_processi_python_diversi(tmp_path):
    """Tre processi veri, un posto solo: i loro intervalli non si sovrappongono mai."""
    codice = (
        "import sys, time\n"
        "from executors.docker import ContainerLimiter\n"
        "with ContainerLimiter(1, sys.argv[1], poll_s=0.01).slot():\n"
        "    inizio = time.time(); time.sleep(0.25); fine = time.time()\n"
        "print(inizio, fine)\n"
    )
    processi = [subprocess.Popen([sys.executable, "-c", codice, str(tmp_path / "posti")],
                                 cwd=RADICE, stdout=subprocess.PIPE, text=True)
                for _ in range(3)]
    intervalli = sorted(tuple(map(float, p.communicate(timeout=30)[0].split())) for p in processi)

    assert all(p.returncode == 0 for p in processi)
    for (_, fine), (inizio, _) in zip(intervalli, intervalli[1:]):
        assert inizio >= fine


def test_il_posto_si_rilascia_se_docker_solleva(tmp_path, monkeypatch):
    def rotto(argomenti, **kwargs):
        raise OSError("docker assente")

    monkeypatch.setattr("executors.docker.subprocess.run", rotto)
    esecutore = DockerExecutor(str(tmp_path / "w"), limiter=ContainerLimiter(1, tmp_path / "posti"))

    with pytest.raises(OSError):
        esecutore.run("true")
    assert not _posto_occupato(tmp_path / "posti")


def test_il_posto_si_rilascia_allo_scadere_del_tempo_e_solo_dopo_il_kill(tmp_path, monkeypatch):
    """Il container deve essere fermo prima che il suo posto torni libero."""
    posti = tmp_path / "posti"
    visto_durante_il_kill = []

    def finto(argomenti, **kwargs):
        if argomenti[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argomenti, 1)
        visto_durante_il_kill.append(_posto_occupato(posti))
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    esecutore = DockerExecutor(str(tmp_path / "w"), limiter=ContainerLimiter(1, posti))

    with pytest.raises(subprocess.TimeoutExpired):
        esecutore.run("while true; do :; done")

    assert visto_durante_il_kill == [True]
    assert not _posto_occupato(posti)


def test_il_kill_ha_un_tempo_massimo_di_dieci_secondi(tmp_path, monkeypatch):
    tempi = []

    def finto(argomenti, **kwargs):
        if argomenti[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argomenti, 1)
        tempi.append(kwargs.get("timeout"))
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    with pytest.raises(subprocess.TimeoutExpired):
        DockerExecutor(str(tmp_path / "w")).run("sleep 999")

    assert tempi == [10]


# -- tempo in coda nel ledger -----------------------------------------------

def test_un_attesa_lunga_diventa_un_evento_nel_ledger(tmp_path, monkeypatch):
    _docker_lento(monkeypatch, durata=0.3)
    limitatore = ContainerLimiter(1, tmp_path / "posti", poll_s=0.01)
    eventi = EventiFinti()
    secondo = DockerExecutor(str(tmp_path / "b"), limiter=limitatore, event_sink=eventi)

    # Il primo usa la stessa cartella dei posti (quindi gli stessi posti) e avvisa
    # quando ne ha preso uno.
    preso = threading.Event()

    class LimitatoreCheAvvisa(ContainerLimiter):
        """Avvisa quando il primo ha davvero il posto: niente `sleep` sperando che basti."""

        @contextlib.contextmanager
        def slot(self):
            with super().slot() as valore:
                preso.set()
                yield valore

    primo = DockerExecutor(str(tmp_path / "a"),
                           limiter=LimitatoreCheAvvisa(1, tmp_path / "posti", poll_s=0.01))
    t = threading.Thread(target=primo.run, args=("true",))
    t.start()
    assert preso.wait(5)            # il primo ha il posto
    secondo.run("true")
    t.join()

    assert len(eventi.eventi) == 1
    tipo, dettagli = eventi.eventi[0]
    assert tipo == "sandbox_wait"
    assert dettagli["max_concurrent"] == 1
    assert 0.1 <= dettagli["wait_s"] < 1.0


def test_un_attesa_breve_non_scrive_nulla(tmp_path, monkeypatch):
    _docker_lento(monkeypatch, durata=0.0)
    eventi = EventiFinti()

    DockerExecutor(str(tmp_path / "w"), event_sink=eventi).run("true")

    assert eventi.eventi == []


# -- istanza unica di modulo (parte "ibrida") -------------------------------

def test_senza_limitatore_gli_esecutori_condividono_quello_di_modulo(tmp_path):
    a = DockerExecutor(str(tmp_path / "a"))
    b = DockerExecutor(str(tmp_path / "b"))

    assert a.limiter is b.limiter is modulo.shared_limiter()


def test_un_limitatore_passato_ha_la_precedenza_su_quello_di_modulo(tmp_path):
    proprio = ContainerLimiter(2, tmp_path / "posti")

    assert DockerExecutor(str(tmp_path / "w"), limiter=proprio).limiter is proprio


def test_il_limitatore_di_modulo_usa_valore_e_cartella_della_configurazione(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DOCKER_MAX_CONCURRENT", 2)
    monkeypatch.setattr(config, "DOCKER_SLOTS_DIR", str(tmp_path / "posti-config"))
    modulo.reset_shared_limiter()

    limitatore = modulo.shared_limiter()

    assert limitatore.max_concurrent == 2
    assert limitatore.slots_dir == tmp_path / "posti-config"


def test_valori_predefiniti():
    assert config.DOCKER_MAX_CONCURRENT == 6       # scelto da Vincenzo il 17 ott (era 4)


def test_la_cartella_predefinita_dei_posti_e_fuori_dal_progetto_e_da_runs():
    # Il conftest la sposta in una cartella temporanea: qui si guarda il valore scritto nel file.
    import re
    trovato = re.search(r'^DOCKER_SLOTS_DIR = "([^"]+)"', (RADICE / "config.py").read_text(),
                        re.MULTILINE)
    assert trovato is not None
    originale = trovato.group(1)
    assert originale.startswith("~/")
    assert "runs" not in originale.split("/")


def test_azzerare_il_limitatore_di_modulo_ne_crea_uno_nuovo():
    vecchio = modulo.shared_limiter()
    modulo.reset_shared_limiter()

    assert modulo.shared_limiter() is not vecchio


def test_il_limitatore_di_modulo_regge_anche_se_creato_da_molti_thread_insieme():
    visti = []
    thread = [threading.Thread(target=lambda: visti.append(modulo.shared_limiter())) for _ in range(20)]
    for t in thread:
        t.start()
    for t in thread:
        t.join()

    assert len({id(x) for x in visti}) == 1


def test_senza_limitatore_il_comportamento_di_run_non_cambia(tmp_path, monkeypatch):
    visti = []
    monkeypatch.setattr("executors.docker.subprocess.run",
                        lambda a, **k: visti.append(list(a)) or NS(stdout="ok", stderr="", returncode=0))

    risultato = DockerExecutor(str(tmp_path / "w")).run("true")

    assert risultato == {"stdout": "ok", "stderr": "", "exit_code": 0}
    assert len(visti) == 1 and visti[0][:2] == ["docker", "run"]


# -- rilievi della revisione del 17 ott -------------------------------------

def _descrittori_aperti() -> int:
    return len(os.listdir("/dev/fd"))


def test_un_errore_inatteso_di_flock_non_lascia_descrittori_aperti(tmp_path, monkeypatch):
    import errno
    limitatore = ContainerLimiter(2, tmp_path / "posti")

    def rotto(fd, operazione):
        raise OSError(errno.ENOLCK, "lock non supportati su questo disco")

    monkeypatch.setattr("executors.docker.fcntl.flock", rotto)
    prima = _descrittori_aperti()
    with pytest.raises(OSError):
        with limitatore.slot():
            pass

    assert _descrittori_aperti() == prima


def test_se_annotare_l_attesa_fallisce_il_comando_parte_lo_stesso(tmp_path, monkeypatch, caplog):
    """L'annotazione e' un dato secondario: non deve impedire il lavoro dell'agente."""
    visti = _docker_lento(monkeypatch, durata=0.0)

    class SinkRotto:
        def append_event(self, event_type, details):
            raise RuntimeError("ledger non scrivibile")

    class LimitatoreLento(ContainerLimiter):
        @contextlib.contextmanager
        def slot(self):
            yield 5.0                 # come se avesse aspettato 5 s

    limitatore = LimitatoreLento(1, tmp_path / "posti")
    esecutore = DockerExecutor(str(tmp_path / "w"), limiter=limitatore, event_sink=SinkRotto())

    with caplog.at_level("WARNING"):
        risultato = esecutore.run("true")

    assert risultato["exit_code"] == 0
    assert visti["massimo"] == 1      # il docker run e' partito
    assert "sandbox_wait" in caplog.text
