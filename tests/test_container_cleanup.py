"""Container orfani: rimozione alla fonte, attesa massima di un posto, pulizia all'avvio (R1.11).

Nota di design (tesi):
    Le prove con Docker vero del 24 ott hanno mostrato container rimasti vivi
    dopo un Ctrl+C, un `kill -9` o un tempo scaduto prima dell'avvio (`docker
    kill` non toglie un container «Created», e `--rm` non scatta). Tre rimedi:
    `docker rm -f` per nome su qualunque interruzione (anche `KeyboardInterrupt`);
    un'attesa massima per un posto della sandbox, che e' un guasto della
    macchina e non del modello; all'avvio di una campagna, la rimozione dei
    container `orc-*` piu' vecchi del loro tempo massimo (P19-D1: per eta', cosi'
    una campagna viva in un altro terminale non si tocca). Qui Docker e' finto.
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from executors.docker import ContainerLimiter, DockerExecutor, SandboxSlotTimeout, cleanup_orphans
from renderer import RenderError, evaluate_site, render_site
from task_model import VerificationError

ORA = datetime(2026, 10, 24, 22, 0, 0, tzinfo=timezone.utc)


# ── Rimozione alla fonte ───────────────────────────────────────────────────

def _esecutore_interrotto(monkeypatch, tmp_path, eccezione):
    viste: list[list[str]] = []

    def finto(argomenti, **kwargs):
        viste.append(list(argomenti))
        if argomenti[:2] == ["docker", "run"]:
            raise eccezione
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    return DockerExecutor(str(tmp_path / "w"), limiter=ContainerLimiter(1, tmp_path / "posti")), viste


def test_o1_un_ctrl_c_durante_docker_run_toglie_il_container_e_arriva_a_chi_chiama(tmp_path, monkeypatch):
    esecutore, viste = _esecutore_interrotto(monkeypatch, tmp_path, KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        esecutore.run("sleep 999")

    nome = viste[0][viste[0].index("--name") + 1]
    assert viste[1] == ["docker", "rm", "-f", nome]


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "start.sh").write_text("python3 -m http.server 8080\n")
    return ws


def _runner_interrotto(eccezione):
    chiamate: list[list[str]] = []

    def run(cmd, **kwargs) -> subprocess.CompletedProcess:
        chiamate.append(list(cmd))
        if cmd[:2] == ["docker", "run"]:
            raise eccezione
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run, chiamate


@pytest.mark.parametrize("funzione", ("render", "evaluate"))
@pytest.mark.parametrize("eccezione, attesa", [
    (KeyboardInterrupt(), KeyboardInterrupt),
    (subprocess.TimeoutExpired(["docker"], 1), RenderError),
])
def test_o2_renderer_e_script_tolgono_il_container_su_ogni_interruzione(tmp_path, funzione, eccezione, attesa):
    run, chiamate = _runner_interrotto(eccezione)
    script = tmp_path / "s.py"
    script.write_text("")

    with pytest.raises(attesa):
        if funzione == "render":
            render_site(_workspace(tmp_path), tmp_path / "out", runner=run)
        else:
            evaluate_site(_workspace(tmp_path), script, runner=run)

    nome = chiamate[0][chiamate[0].index("--name") + 1]
    assert chiamate[1][:4] == ["docker", "rm", "-f", nome]


# ── Attesa massima per un posto ────────────────────────────────────────────

def _occupa(posti: Path, rilascia: threading.Event, preso: threading.Event) -> None:
    with ContainerLimiter(1, posti).slot():
        preso.set()
        rilascia.wait(5)


def _descrittori_aperti() -> int:
    return len(os.listdir("/dev/fd"))


def test_o3_oltre_l_attesa_massima_e_un_guasto_della_macchina(tmp_path):
    posti = tmp_path / "posti"
    rilascia, preso = threading.Event(), threading.Event()
    filo = threading.Thread(target=_occupa, args=(posti, rilascia, preso))
    filo.start()
    preso.wait(5)
    try:
        prima = _descrittori_aperti()
        inizio = time.monotonic()
        with pytest.raises(SandboxSlotTimeout):
            with ContainerLimiter(1, posti, max_wait_s=0.2).slot():
                pass
        assert time.monotonic() - inizio < 0.5
        assert _descrittori_aperti() == prima
    finally:
        rilascia.set()
        filo.join()
    assert issubclass(SandboxSlotTimeout, VerificationError)


def test_o4_un_posto_liberato_prima_della_scadenza_fa_entrare(tmp_path):
    posti = tmp_path / "posti"
    rilascia, preso = threading.Event(), threading.Event()
    filo = threading.Thread(target=_occupa, args=(posti, rilascia, preso))
    filo.start()
    preso.wait(5)
    threading.Timer(0.1, rilascia.set).start()

    with ContainerLimiter(1, posti, max_wait_s=2).slot() as attesa:
        assert attesa >= 0.05
    filo.join()


def test_o5_attesa_massima_negativa_e_un_errore_prima_di_creare_la_cartella(tmp_path):
    with pytest.raises(ValueError):
        ContainerLimiter(1, tmp_path / "posti", max_wait_s=-1)
    assert not (tmp_path / "posti").exists()


# ── Pulizia all'avvio della campagna ───────────────────────────────────────

def _docker_finto(contenitori: list[tuple[str, str, datetime]], rm_fallisce: bool = False):
    """`docker ps -a` e `docker inspect` su un elenco (nome, stato, creato); registra le rimozioni."""
    tolti: list[str] = []

    def run(cmd, **kwargs):
        if cmd[:3] == ["docker", "ps", "-a"]:
            return NS(returncode=0, stderr="", stdout="".join(f"{n}\n" for n, _, _ in contenitori))
        if cmd[:2] == ["docker", "inspect"]:
            righe = [f"/{n}\t{s}\t{c.strftime('%Y-%m-%dT%H:%M:%S.123456789Z')}\n"
                     for n, s, c in contenitori if n in cmd]
            return NS(returncode=0, stderr="", stdout="".join(righe))
        if cmd[:3] == ["docker", "rm", "-f"]:
            if rm_fallisce:
                return NS(returncode=1, stderr="Error: busy", stdout="")
            tolti.append(cmd[3])
            return NS(returncode=0, stderr="", stdout="")
        raise AssertionError(cmd)

    return run, tolti


MASSIMI = {"orc-sandbox-": 60.0, "orc-renderer-": 240.0, "orc-eval-": 900.0}


def test_o6_si_tolgono_solo_i_container_oltre_il_tempo_massimo_piu_30_s():
    run, tolti = _docker_finto([
        ("orc-sandbox-vecchio", "running", ORA - timedelta(seconds=91)),
        ("orc-sandbox-giovane", "running", ORA - timedelta(seconds=89)),
        ("orc-eval-lungo", "running", ORA - timedelta(seconds=600)),
        ("orc-renderer-vecchio", "exited", ORA - timedelta(seconds=300)),
    ])

    assert cleanup_orphans(MASSIMI, runner=run, now=ORA) == ["orc-sandbox-vecchio", "orc-renderer-vecchio"]
    assert tolti == ["orc-sandbox-vecchio", "orc-renderer-vecchio"]


def test_o7_un_container_mai_partito_si_toglie_dopo_60_s():
    run, tolti = _docker_finto([
        ("orc-eval-fermo", "created", ORA - timedelta(seconds=61)),
        ("orc-eval-appena", "created", ORA - timedelta(seconds=10)),
    ])

    assert cleanup_orphans(MASSIMI, runner=run, now=ORA) == ["orc-eval-fermo"]


def test_o8_nomi_che_contengono_il_prefisso_senza_iniziare_con_esso_non_si_toccano():
    # Il filtro `name=` di Docker cerca la sottostringa: va ricontrollato l'inizio del nome.
    run, tolti = _docker_finto([("xorc-sandbox-altro", "running", ORA - timedelta(days=1)),
                                ("mio-orc-eval-1", "exited", ORA - timedelta(days=1))])

    assert cleanup_orphans(MASSIMI, runner=run, now=ORA) == []
    assert tolti == []


def test_o9_una_rimozione_fallita_e_un_avviso_non_un_errore(caplog):
    run, _ = _docker_finto([("orc-sandbox-x", "running", ORA - timedelta(hours=1))], rm_fallisce=True)

    assert cleanup_orphans(MASSIMI, runner=run, now=ORA) == []
    assert "orc-sandbox-x" in caplog.text


def test_o10_nessun_container_nessuna_ispezione():
    run, tolti = _docker_finto([])

    assert cleanup_orphans(MASSIMI, runner=run, now=ORA) == []


# ── Posti anche per renderer e script (R1.4, 26 ott) ───────────────────────
# Renderer e script lanciano container come la sandbox e pesano sulla stessa
# macchina: prendono un posto dello stesso limitatore, iniettabile come quello
# di `DockerExecutor` (di modulo se non dato).

def _chiama(funzione: str, tmp_path: Path, run, **kwargs):
    script = tmp_path / "s.py"
    script.write_text("")
    if funzione == "render":
        return render_site(_workspace(tmp_path), tmp_path / "out", runner=run, **kwargs)
    return evaluate_site(_workspace(tmp_path), script, runner=run, **kwargs)


def _posto_libero(posti: Path) -> bool:
    try:
        with ContainerLimiter(1, posti, max_wait_s=0).slot():
            return True
    except SandboxSlotTimeout:
        return False


@pytest.mark.parametrize("funzione", ("render", "evaluate"))
def test_o11_il_container_parte_dentro_un_posto_del_limitatore(tmp_path, funzione):
    posti = tmp_path / "posti"
    occupato_durante_run: list[bool] = []

    def run(cmd, **kwargs):
        if cmd[:2] == ["docker", "run"]:
            occupato_durante_run.append(not _posto_libero(posti))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(RenderError):        # nessun risultato scritto: guasto, ma dopo il run
        _chiama(funzione, tmp_path, run, limiter=ContainerLimiter(1, posti))

    assert occupato_durante_run == [True]
    assert _posto_libero(posti)             # rilasciato alla fine


@pytest.mark.parametrize("funzione", ("render", "evaluate"))
@pytest.mark.parametrize("eccezione", (KeyboardInterrupt(), subprocess.TimeoutExpired(["docker"], 1)))
def test_o12_il_posto_si_rilascia_anche_su_un_interruzione(tmp_path, funzione, eccezione):
    posti = tmp_path / "posti"
    run, _ = _runner_interrotto(eccezione)

    with pytest.raises((KeyboardInterrupt, RenderError)):
        _chiama(funzione, tmp_path, run, limiter=ContainerLimiter(1, posti))

    assert _posto_libero(posti)


@pytest.mark.parametrize("funzione", ("render", "evaluate"))
def test_o13_senza_posto_entro_l_attesa_massima_nessun_container_parte(tmp_path, funzione):
    posti = tmp_path / "posti"
    chiamate: list[list[str]] = []

    def run(cmd, **kwargs):
        chiamate.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    rilascia, preso = threading.Event(), threading.Event()
    filo = threading.Thread(target=_occupa, args=(posti, rilascia, preso))
    filo.start()
    preso.wait(5)
    try:
        with pytest.raises(SandboxSlotTimeout):
            _chiama(funzione, tmp_path, run, limiter=ContainerLimiter(1, posti, max_wait_s=0.1))
    finally:
        rilascia.set()
        filo.join()
    assert chiamate == []


@pytest.mark.parametrize("funzione", ("render", "evaluate"))
def test_o14_senza_limitatore_si_usa_quello_di_modulo(tmp_path, monkeypatch, funzione):
    import config
    from executors import docker
    monkeypatch.setattr(config, "DOCKER_MAX_CONCURRENT", 1)
    monkeypatch.setattr(config, "DOCKER_ATTESA_POSTO_MAX_S", 0.1)
    docker.reset_shared_limiter()
    chiamate: list[list[str]] = []

    def run(cmd, **kwargs):
        chiamate.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with docker.shared_limiter().slot():
        with pytest.raises(SandboxSlotTimeout):
            _chiama(funzione, tmp_path, run)
    assert chiamate == []


def test_o15_senza_start_sh_non_si_aspetta_un_posto(tmp_path):
    posti = tmp_path / "posti"
    ws = tmp_path / "vuoto"
    ws.mkdir()
    script = tmp_path / "s.py"
    script.write_text("")
    rilascia, preso = threading.Event(), threading.Event()
    filo = threading.Thread(target=_occupa, args=(posti, rilascia, preso))
    filo.start()
    preso.wait(5)
    try:
        limitatore = ContainerLimiter(1, posti, max_wait_s=0.1)
        assert render_site(ws, tmp_path / "out", limiter=limitatore).started is False
        assert evaluate_site(ws, script, limiter=limitatore).funziona == 0
    finally:
        rilascia.set()
        filo.join()


# ── Ctrl+C vero durante il rendering (R1.4, 26 ott) ────────────────────────

_INTEGRAZIONE = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION") or shutil.which("docker") is None,
    reason="serve Docker con l'immagine orc-renderer:r1: ORC_INTEGRATION=1")

_FIGLIO = """
import sys
from pathlib import Path
from executors.docker import ContainerLimiter
from renderer import evaluate_site, render_site
ws, out, posti, funzione = (Path(a) for a in sys.argv[1:5])
limitatore = ContainerLimiter(1, posti)
if funzione.name == "render":
    render_site(ws, out, start_timeout=120, limiter=limitatore)
else:
    evaluate_site(ws, Path(sys.argv[5]), start_timeout=120, limiter=limitatore)
"""


def _container(prefisso: str) -> set[str]:
    uscita = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"],
                            capture_output=True, text=True, check=True).stdout
    return {n for n in uscita.split() if n.startswith(prefisso)}


@_INTEGRAZIONE
@pytest.mark.parametrize("funzione, prefisso", [("render", "orc-renderer-"), ("evaluate", "orc-eval-")])
def test_i10_un_ctrl_c_vero_a_meta_toglie_il_container(tmp_path, funzione, prefisso):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "start.sh").write_text("sleep 600\n")          # la porta non si apre mai: il container resta vivo
    # uno script con passi: con uno script vuoto la valutazione finisce senza avviare il sito
    script = Path(__file__).resolve().parent / "fixtures" / "valutazione" / "script_items.py"
    prima = _container(prefisso)
    radice = Path(__file__).resolve().parent.parent
    figlio = subprocess.Popen(
        [sys.executable, "-c", _FIGLIO, str(ws), str(tmp_path / "out"), str(tmp_path / "posti"),
         funzione, str(script)], cwd=radice, start_new_session=True)
    try:
        nuovi: set[str] = set()
        scadenza = time.monotonic() + 60
        while not nuovi and time.monotonic() < scadenza:
            time.sleep(0.5)
            nuovi = _container(prefisso) - prima
        assert nuovi, "il container non e' mai comparso"
        time.sleep(2)                                    # il container sta davvero girando
        assert figlio.poll() is None, "il processo e' finito prima del Ctrl+C"
        os.killpg(figlio.pid, signal.SIGINT)                # come Ctrl+C: a tutto il gruppo, docker compreso
        figlio.wait(60)
    finally:
        if figlio.poll() is None:
            figlio.kill()
    assert figlio.returncode != 0
    assert not (nuovi & _container(prefisso))
    assert _posto_libero(tmp_path / "posti")
