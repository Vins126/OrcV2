"""L'esecutore Docker compone il comando `docker run` e la rete e' un parametro.

Nota di design (tesi):
    Finora la composizione del comando `docker run` non aveva nessun test: la si
    provava solo con le run vere. Qui `subprocess.run` e' sostituito da un finto
    che registra gli argomenti, quindi i test non richiedono Docker acceso.

    La rete e' una proprieta' dell'agente per tutta la sua vita: `none` e' la
    base delle misure (ambiente chiuso e ripetibile), `bridge` e' la condizione
    "con internet". Qualunque altro valore e' un errore, perche' `host` o una
    rete con nome aprirebbero la sandbox verso la macchina o verso altri
    container senza che nessuno l'abbia deciso.
"""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import campaign
from campaign import CampaignError
from executors.docker import DockerExecutor
from tools import build_default_tools


@pytest.fixture
def chiamate(monkeypatch):
    """Registra gli argomenti di ogni `subprocess.run` fatto dall'esecutore."""
    viste: list[list[str]] = []

    def finto(argomenti, **kwargs):
        viste.append(list(argomenti))
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    return viste


def _valore_dopo(argomenti: list[str], opzione: str) -> str:
    return argomenti[argomenti.index(opzione) + 1]


# ── N1-N3: il parametro di rete ───────────────────────────────────────────

def test_n1_senza_parametro_la_rete_e_none(tmp_path, chiamate):
    DockerExecutor(str(tmp_path)).run("true")

    assert _valore_dopo(chiamate[0], "--network") == "none"


def test_n2_con_bridge_il_comando_passa_bridge(tmp_path, chiamate):
    DockerExecutor(str(tmp_path), network="bridge").run("true")

    assert _valore_dopo(chiamate[0], "--network") == "bridge"


def test_n2b_la_rete_non_allenta_le_altre_protezioni(tmp_path, chiamate):
    """Con `bridge` ogni altra protezione del comando resta com'e'."""
    DockerExecutor(str(tmp_path), network="bridge", memory="256m", pids_limit="64").run("true")

    comando = chiamate[0]
    assert "--rm" in comando
    assert "--read-only" in comando
    assert _valore_dopo(comando, "--tmpfs") == "/tmp"
    assert _valore_dopo(comando, "--memory") == "256m"
    assert _valore_dopo(comando, "--pids-limit") == "64"
    assert "ORC_RUN_AS=1000:1000" in comando     # l'utente finale resta 1000: vedi N9
    assert _valore_dopo(comando, "--workdir") == "/workspace"


@pytest.mark.parametrize("valore", ["host", "container:altro", "rete-mia", "", "NONE"])
def test_n3_una_rete_non_ammessa_e_un_errore_prima_di_toccare_il_disco(tmp_path, chiamate, valore):
    cartella = tmp_path / "ws"

    with pytest.raises(ValueError, match="rete"):
        DockerExecutor(str(cartella), network=valore)

    assert not cartella.exists()      # nessuna cartella orfana
    assert chiamate == []             # nessuna chiamata a Docker


# ── N4: build_default_tools propaga la rete ───────────────────────────────

class EsecutoreFinto:
    """Sostituisce `DockerExecutor` e conserva gli argomenti ricevuti."""

    visti: list[dict] = []

    def __init__(self, workspace, **kwargs):
        EsecutoreFinto.visti.append(kwargs)

    def run(self, command):
        return {"stdout": "", "stderr": "", "exit_code": 0}


@pytest.fixture
def esecutore_finto(monkeypatch):
    EsecutoreFinto.visti = []
    monkeypatch.setattr("tools.DockerExecutor", EsecutoreFinto)
    return EsecutoreFinto


def test_n4_i_tool_di_default_hanno_rete_none(tmp_path, esecutore_finto):
    build_default_tools(str(tmp_path / "a"))

    assert esecutore_finto.visti[0]["network"] == "none"


def test_n4b_i_tool_ricevono_la_rete_richiesta(tmp_path, esecutore_finto):
    build_default_tools(str(tmp_path / "a"), network="bridge")

    assert esecutore_finto.visti[0]["network"] == "bridge"


# ── N5: la campagna: rete per gli agenti, mai per la verifica ─────────────

def test_n5_il_costruttore_di_tool_della_campagna_usa_la_rete_scelta(tmp_path, esecutore_finto):
    campaign.tools_builder_for("bridge")(str(tmp_path / "a"))

    assert esecutore_finto.visti[0]["network"] == "bridge"


def test_n5b_la_verifica_gira_senza_rete(tmp_path, monkeypatch):
    visti = []

    class Finto:
        def __init__(self, workspace, **kwargs):
            visti.append(kwargs)

        def run(self, command):
            return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr("campaign.DockerExecutor", Finto)

    campaign.shell_docker(tmp_path, "true")

    assert visti[0]["network"] == "none"


def test_n5c_da_main_la_rete_va_agli_agenti_e_la_verifica_resta_senza(tmp_path, monkeypatch, esecutore_finto):
    """Il collegamento che conta: `--network bridge` arriva ai tool degli agenti,
    mentre `shell` (setup e verifica) resta `shell_docker`, che e' fisso a `none`."""
    viste = {}
    monkeypatch.setattr(campaign, "run_campaign", lambda *a, **kw: viste.update(kw) or [])

    class FabbricaRegistrata:
        def __init__(self, *a, **kw):
            viste["fabbrica"] = kw

    monkeypatch.setattr(campaign, "AgentFactory", FabbricaRegistrata)

    codice = campaign.main(
        ["run", "--network", "bridge", "--budget-usd", "0.01", "--max-total-usd", "1.0",
         "--campaign-id", "x"], dotenv_path=tmp_path / ".env")

    assert codice == 0
    assert viste["shell"] is campaign.shell_docker
    assert viste["environment"]["network"] == "bridge"
    viste["fabbrica"]["tools_builder"](str(tmp_path / "ws"))
    assert esecutore_finto.visti[0]["network"] == "bridge"


# ── N6: l'ambiente si scrive in testa al manifesto ────────────────────────

def test_n6_l_ambiente_descrive_immagine_e_rete():
    ambiente = campaign.sandbox_environment(
        "orc-sandbox:m2s4", "bridge", inspect=lambda immagine: "sha256:abc123")

    assert ambiente == {"image": "orc-sandbox:m2s4", "image_id": "sha256:abc123",
                        "network": "bridge"}


def test_n6b_la_prima_riga_del_manifesto_e_l_ambiente_e_il_report_la_ignora(tmp_path):
    from accounting import ModelRegistry
    ambiente = {"image": "orc-sandbox:m2s4", "image_id": "sha256:abc", "network": "none"}
    fabbrica = NS(build=lambda role: (_ for _ in ()).throw(RuntimeError("niente")))

    campaign.run_campaign(
        fabbrica, [campaign.Task(id="t", prompt="p", verify="true")], role="worker",
        repetitions=1, campaign_id="c1", campaigns_dir=tmp_path / "campagne",
        shell=lambda ws, cmd: 0, environment=ambiente)

    import json
    righe = [json.loads(r) for r in (tmp_path / "campagne" / "c1.jsonl").read_text().splitlines()]
    assert righe[0] == {"environment": ambiente}

    esito = campaign.report(tmp_path / "campagne" / "c1.jsonl", tmp_path / "runs",
                            ModelRegistry.from_file("models.toml"))
    assert esito.excluded_runs == 1       # la riga `build_failed`, non l'ambiente
    assert esito.runs == 0


# ── N7: l'immagine deve esistere prima di costruire agenti ────────────────

def test_n7_immagine_assente_e_un_errore_parlante_con_il_comando_per_costruirla():
    with pytest.raises(CampaignError, match="orc-sandbox:m2s4") as errore:
        campaign.ensure_image_available("orc-sandbox:m2s4", inspect=lambda immagine: None)

    assert "docker build" in str(errore.value)


def test_n7b_immagine_presente_non_da_errore():
    campaign.ensure_image_available("orc-sandbox:m2s4", inspect=lambda immagine: "sha256:abc")


# ── Casi limite: immagine, HOME, ambiente ──────────────────────────────────

def test_r1_immagine_assente_da_la_causa_giusta_e_non_tocca_ne_env_ne_cartelle(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("executors.docker.image_id", lambda image: None)

    codice = campaign.main(
        ["run", "--budget-usd", "0.01", "--max-total-usd", "1.0", "--campaign-id", "x"],
        dotenv_path=tmp_path / ".env")

    assert codice == 2
    assert "docker build" in capsys.readouterr().err


def test_r1b_ripetizioni_zero_da_errore_per_le_ripetizioni(tmp_path, capsys):
    codice = campaign.main(
        ["run", "--repetitions", "0", "--budget-usd", "0.01", "--max-total-usd", "1.0",
         "--campaign-id", "x"], dotenv_path=tmp_path / ".env")

    assert codice == 2
    assert "repetitions" in capsys.readouterr().err


def test_r3_il_dockerfile_da_all_utente_senza_nome_una_home_scrivibile():
    """L'utente 1000 non esiste nell'immagine: senza `HOME` Docker usa `/`, che
    in sola lettura fa fallire npm e pip. Controllo statico: la prova vera e'
    manuale (installare un pacchetto dalla rete `bridge`)."""
    testo = Path("docker/sandbox.Dockerfile").read_text()

    assert "ENV HOME=/tmp" in testo
    assert "npm_config_cache=/tmp/" in testo
    assert "PIP_CACHE_DIR=/tmp/" in testo


def test_r6_il_file_dei_task_non_dice_piu_che_la_sandbox_non_ha_python():
    testo = Path("campaigns/m2s4a.toml").read_text().lower()

    assert "non ha python" not in testo


# ── Controllo dell'immagine nei due punti d'ingresso ──────────────────────

def test_ensure_image_assente_solleva_un_errore_con_il_comando_per_costruirla():
    from executors.docker import SandboxImageMissing, ensure_image

    with pytest.raises(SandboxImageMissing, match="orc-sandbox:m2s4") as errore:
        ensure_image("orc-sandbox:m2s4", inspect=lambda immagine: None)

    assert "docker build" in str(errore.value)


def test_main_py_non_parte_se_l_immagine_manca_e_non_crea_cartelle(tmp_path, monkeypatch, capsys):
    """Deve fermarsi PER L'IMMAGINE: senza chiavi nel `.env` finto fallirebbe anche
    per altro, quindi si controlla il messaggio e non solo il codice di uscita."""
    from main import main
    monkeypatch.setattr("executors.docker.image_id", lambda image: None)
    runs = tmp_path / "runs"

    with pytest.raises(SystemExit) as uscita:
        main(["--runs-dir", str(runs), "--workspace", str(tmp_path / "ws"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert "docker build" in capsys.readouterr().err
    assert not runs.exists()
    assert not (tmp_path / "ws").exists()


# ── N9: sotto bridge il firewall dell'immagine isola la macchina e la LAN ─

def _permessi_aggiunti(comando: list[str]) -> list[str]:
    return sorted(comando[i + 1] for i, voce in enumerate(comando) if voce == "--cap-add")


def test_n9_con_bridge_il_container_ha_solo_i_permessi_che_servono_al_firewall(tmp_path, chiamate):
    """Parte come amministratore per applicare le regole; poi l'entrypoint scende
    a utente 1000 senza permessi. Qui si prova cio' che lo permette: tutti i
    permessi tolti, meno i quattro che servono, e l'utente finale dichiarato."""
    DockerExecutor(str(tmp_path), network="bridge").run("true")

    comando = chiamate[0]
    assert _valore_dopo(comando, "--cap-drop") == "ALL"
    assert _permessi_aggiunti(comando) == ["NET_ADMIN", "SETGID", "SETPCAP", "SETUID"]
    assert _valore_dopo(comando, "--user") == "0:0"
    assert "ORC_FIREWALL=1" in comando
    assert "ORC_RUN_AS=1000:1000" in comando


def test_n9b_con_none_nessun_permesso_in_piu_e_nessun_firewall(tmp_path, chiamate):
    DockerExecutor(str(tmp_path)).run("true")

    comando = chiamate[0]
    assert "--cap-add" not in comando
    assert "--cap-drop" not in comando
    assert _valore_dopo(comando, "--user") == "1000:1000"
    assert not any(voce.startswith("ORC_FIREWALL") for voce in comando)


def test_n9c_l_entrypoint_blocca_le_reti_private_e_non_parte_se_il_firewall_fallisce():
    """Controllo statico: la prova vera e' `test_sandbox_integration`, con Docker."""
    script = Path("docker/sandbox-entrypoint.sh").read_text()

    for rete in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"):
        assert rete in script, rete
    assert "set -e" in script                   # se una regola fallisce, il comando non parte
    assert "--bounding-set=-all" in script      # i permessi si azzerano prima di eseguire
    assert "--no-new-privs" in script
    assert "--dport 53" in script               # l'unica eccezione: il DNS del container


def test_n9d_il_dockerfile_installa_il_firewall_e_usa_l_entrypoint():
    testo = Path("docker/sandbox.Dockerfile").read_text()

    assert "iptables" in testo
    assert "sandbox-entrypoint.sh" in testo
    assert "ENTRYPOINT" in testo


# ── Avvio a freddo di Docker: il controllo dell'immagine aspetta, poi decide ─
#
# Nota di design (tesi):
#    Docker Desktop spegne il motore dopo una decina di minuti di inattivita' e lo riavvia al primo
#    comando. Nei primi secondi dopo il riavvio `docker image inspect <nome>` risponde «No such
#    image» anche se l'immagine c'e' (osservato il 12 ottobre 2026, in coincidenza con i
#    `Docker:starting` del log di Docker Desktop). Un controllo che si arrende al primo tentativo
#    ferma una campagna per un errore che si risolve da solo; uno che aspetta all'infinito
#    nasconde un'immagine davvero mancante. Qui si aspetta un tempo limitato.

def _inspect_che_risponde_al_tentativo(n):
    chiamate = []

    def inspect(immagine):
        chiamate.append(immagine)
        return "sha256:ok" if len(chiamate) >= n else None

    return inspect, chiamate


def test_d1_ensure_image_ritenta_finche_docker_risponde():
    from executors.docker import ensure_image
    inspect, chiamate = _inspect_che_risponde_al_tentativo(3)
    attese = []

    ensure_image("orc-sandbox:m2s4", inspect=inspect, attempts=6, delay=5.0, sleep=attese.append)

    assert len(chiamate) == 3
    assert attese == [5.0, 5.0]                         # dorme fra un tentativo e l'altro, non dopo l'ultimo


def test_d2_dopo_tutti_i_tentativi_senza_risposta_solleva_l_errore_di_sempre():
    from executors.docker import SandboxImageMissing, ensure_image
    inspect, chiamate = _inspect_che_risponde_al_tentativo(99)
    attese = []

    with pytest.raises(SandboxImageMissing, match="docker build"):
        ensure_image("orc-sandbox:m2s4", inspect=inspect, attempts=4, delay=2.0, sleep=attese.append)

    assert len(chiamate) == 4 and attese == [2.0, 2.0, 2.0]


def test_d3_se_l_immagine_risponde_subito_non_si_aspetta():
    from executors.docker import ensure_image
    inspect, chiamate = _inspect_che_risponde_al_tentativo(1)
    attese = []

    ensure_image("orc-sandbox:m2s4", inspect=inspect, attempts=6, delay=5.0, sleep=attese.append)

    assert len(chiamate) == 1 and attese == []


def test_d4_senza_parametri_resta_un_solo_tentativo_senza_attesa():
    from executors.docker import SandboxImageMissing, ensure_image
    inspect, chiamate = _inspect_che_risponde_al_tentativo(99)

    with pytest.raises(SandboxImageMissing):
        ensure_image("orc-sandbox:m2s4", inspect=inspect)

    assert len(chiamate) == 1


def test_d5_la_campagna_passa_tentativi_e_attesa_al_controllo():
    import campaign
    inspect, chiamate = _inspect_che_risponde_al_tentativo(2)
    attese = []

    campaign.ensure_image_available("orc-sandbox:m2s4", inspect=inspect, attempts=3, delay=1.5,
                                    sleep=attese.append)

    assert len(chiamate) == 2 and attese == [1.5]


def test_d6a_la_politica_di_attesa_copre_un_avvio_a_freddo_senza_bloccare_per_minuti():
    import config
    totale = config.DOCKER_ATTESA_AVVIO_S * (config.DOCKER_TENTATIVI_AVVIO - 1)

    assert 30 <= totale <= 90
    assert config.DOCKER_TENTATIVI_AVVIO >= 2


def test_d6b_main_aspetta_davvero_l_avvio_di_docker_poi_esce_senza_creare_cartelle(tmp_path, monkeypatch, capsys):
    """Fa girare `main`, non guarda il sorgente: se `main.py` smettesse di passare la politica,
    il numero di attese sarebbe zero."""
    import config
    from main import main
    attese = []
    monkeypatch.setattr("executors.docker.image_id", lambda image: None)
    monkeypatch.setattr("executors.docker._attendi", attese.append)

    with pytest.raises(SystemExit) as uscita:
        main(["--runs-dir", str(tmp_path / "runs"), "--workspace", str(tmp_path / "ws"), "task"],
             dotenv_path=tmp_path / ".env")

    assert uscita.value.code == 2
    assert attese == [config.DOCKER_ATTESA_AVVIO_S] * (config.DOCKER_TENTATIVI_AVVIO - 1)
    assert not (tmp_path / "runs").exists() and not (tmp_path / "ws").exists()


def test_d6c_la_campagna_aspetta_davvero_l_avvio_di_docker_poi_esce_con_codice_2(tmp_path, monkeypatch, capsys):
    import campaign
    import config
    attese = []
    monkeypatch.setattr("executors.docker.image_id", lambda image: None)
    monkeypatch.setattr("executors.docker._attendi", attese.append)

    codice = campaign.main(
        ["run", "--budget-usd", "0.01", "--max-total-usd", "1.0", "--campaign-id", "x"],
        dotenv_path=tmp_path / ".env")

    assert codice == 2
    assert attese == [config.DOCKER_ATTESA_AVVIO_S] * (config.DOCKER_TENTATIVI_AVVIO - 1)
    assert "docker build" in capsys.readouterr().err


# ── Rilievi della revisione: tempo totale e `docker` assente ──────────────

from executors import docker as _modulo_docker
_IMAGE_ID_VERO = _modulo_docker.image_id      # presa prima che conftest la sostituisca


class OrologioFinto:
    """Orologio che avanza solo quando qualcuno 'lavora' o 'dorme'."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_e1_il_tempo_totale_e_limitato_anche_se_ogni_tentativo_e_lento():
    """Con Docker bloccato ogni `inspect` puo' durare fino al suo timeout (30 s): contare solo
    le pause darebbe 12 x 30 + 55 secondi. Il tetto vale sul tempo reale trascorso."""
    from executors.docker import SandboxImageMissing, ensure_image
    orologio = OrologioFinto()
    chiamate = []

    def inspect_lento(immagine):
        chiamate.append(orologio.t)
        orologio.t += 30.0                          # ogni tentativo "dura" 30 s e fallisce
        return None

    def dormi(secondi):
        orologio.t += secondi

    with pytest.raises(SandboxImageMissing):
        ensure_image("orc-sandbox:m2s4", inspect=inspect_lento, attempts=12, delay=5.0,
                     sleep=dormi, max_total_s=55.0, clock=orologio)

    assert len(chiamate) == 2                       # t=0 e t=35; al terzo il tetto di 55 s e' superato
    assert orologio.t <= 55.0 + 30.0                # al piu' un tentativo in volo oltre il tetto


def test_e2_senza_tetto_di_tempo_il_comportamento_resta_quello_dei_tentativi():
    from executors.docker import SandboxImageMissing, ensure_image
    inspect, chiamate = _inspect_che_risponde_al_tentativo(99)

    with pytest.raises(SandboxImageMissing):
        ensure_image("orc-sandbox:m2s4", inspect=inspect, attempts=3, delay=0.0, sleep=lambda s: None)

    assert len(chiamate) == 3


def test_e3_se_il_comando_docker_non_esiste_l_errore_e_immediato_e_dice_perche(monkeypatch):
    """Il binario assente si sa al primo tentativo: aspettare 55 s non lo cambierebbe."""
    from executors.docker import SandboxImageMissing, ensure_image
    attese = []

    def senza_docker(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'docker'")

    monkeypatch.setattr("executors.docker.image_id", _IMAGE_ID_VERO)
    monkeypatch.setattr("executors.docker.subprocess.run", senza_docker)

    with pytest.raises(SandboxImageMissing, match="docker.*PATH") as errore:
        ensure_image("orc-sandbox:m2s4", attempts=12, delay=5.0, sleep=attese.append)

    assert attese == []
    assert "docker build" not in str(errore.value)  # costruire l'immagine non serve senza `docker`


def test_e4_un_timeout_di_docker_invece_si_ritenta(monkeypatch):
    """Docker che non risponde in tempo e' proprio lo stato transitorio dell'avvio a freddo."""
    import subprocess
    from executors.docker import ensure_image
    chiamate = []

    def lento_poi_ok(*args, **kwargs):
        chiamate.append(1)
        if len(chiamate) < 3:
            raise subprocess.TimeoutExpired(cmd="docker", timeout=30)
        return subprocess.CompletedProcess(args, 0, stdout="sha256:ok\n", stderr="")

    monkeypatch.setattr("executors.docker.image_id", _IMAGE_ID_VERO)
    monkeypatch.setattr("executors.docker.subprocess.run", lento_poi_ok)

    ensure_image("orc-sandbox:m2s4", attempts=6, delay=1.0, sleep=lambda s: None)

    assert len(chiamate) == 3


# ── `image_id` cerca l'immagine con `docker image ls`, non con `inspect` ───
#
# Nota di design (tesi):
#    Con l'archivio immagini containerd di Docker Desktop, `docker image inspect <nome corto>`
#    risponde a tratti «No such image» anche con Docker acceso e l'immagine presente (osservato 3
#    volte il 12-13 ottobre 2026); nelle stesse finestre `docker images` la elencava e `docker run`
#    la eseguiva. Cercarla nell'elenco evita il comando inaffidabile invece di aspettarlo.

def _subprocess_finto(stdout="", returncode=0, viste=None):
    import subprocess

    def run(args, **kwargs):
        if viste is not None:
            viste.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    return run


def test_f1_image_id_usa_l_elenco_delle_immagini_e_restituisce_l_id_completo(monkeypatch):
    viste = []
    monkeypatch.setattr("executors.docker.subprocess.run",
                        _subprocess_finto(stdout="sha256:abc123\n", viste=viste))

    assert _IMAGE_ID_VERO("orc-sandbox:m2s4") == "sha256:abc123"
    assert viste == [["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", "orc-sandbox:m2s4"]]


def test_f2_immagine_assente_elenco_vuoto_e_none(monkeypatch):
    monkeypatch.setattr("executors.docker.subprocess.run", _subprocess_finto(stdout="\n"))

    assert _IMAGE_ID_VERO("orc-sandbox:inesistente") is None


def test_f3_docker_che_risponde_con_errore_e_none(monkeypatch):
    monkeypatch.setattr("executors.docker.subprocess.run",
                        _subprocess_finto(stdout="", returncode=1))

    assert _IMAGE_ID_VERO("orc-sandbox:m2s4") is None


def test_f4_con_piu_righe_vale_la_prima(monkeypatch):
    monkeypatch.setattr("executors.docker.subprocess.run",
                        _subprocess_finto(stdout="sha256:primo\nsha256:secondo\n"))

    assert _IMAGE_ID_VERO("orc-sandbox:m2s4") == "sha256:primo"


# ── Un comando che non finisce non lascia un container vivo ───────────────

import subprocess  # noqa: E402


def _esecuzioni_che_scadono(monkeypatch, kill_solleva=False):
    """`docker run` scade come per un ciclo infinito; registra anche l'eventuale `docker kill`."""
    viste: list[list[str]] = []

    def finto(argomenti, **kwargs):
        viste.append(list(argomenti))
        if argomenti[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(argomenti, 1)
        if kill_solleva:
            raise OSError("docker non risponde")
        return NS(stdout="", stderr="", returncode=0)

    monkeypatch.setattr("executors.docker.subprocess.run", finto)
    return viste


def test_ogni_container_ha_un_nome_proprio(tmp_path, chiamate):
    esecutore = DockerExecutor(str(tmp_path))

    esecutore.run("true")
    esecutore.run("true")

    nomi = [_valore_dopo(c, "--name") for c in chiamate]
    assert len(set(nomi)) == 2 and all(n.startswith("orc-sandbox-") for n in nomi)


def test_allo_scadere_del_tempo_il_container_si_ferma_e_l_errore_resta(tmp_path, monkeypatch):
    """`subprocess.run(timeout=)` ferma il programma `docker`, non il container: servirebbe un `kill`."""
    viste = _esecuzioni_che_scadono(monkeypatch)

    with pytest.raises(subprocess.TimeoutExpired):
        DockerExecutor(str(tmp_path)).run("while true; do :; done")

    nome = _valore_dopo(viste[0], "--name")
    # P19-D2 (24 ott): `rm -f` toglie anche un container mai partito, `kill` no.
    assert viste[1] == ["docker", "rm", "-f", nome]


def test_se_il_kill_fallisce_l_errore_di_tempo_arriva_lo_stesso(tmp_path, monkeypatch):
    _esecuzioni_che_scadono(monkeypatch, kill_solleva=True)

    with pytest.raises(subprocess.TimeoutExpired):
        DockerExecutor(str(tmp_path)).run("while true; do :; done")


def test_senza_scadenza_non_c_e_nessun_kill(tmp_path, chiamate):
    DockerExecutor(str(tmp_path)).run("true")

    assert len(chiamate) == 1 and chiamate[0][:2] == ["docker", "run"]
