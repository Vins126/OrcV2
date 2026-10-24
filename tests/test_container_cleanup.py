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
import subprocess
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
