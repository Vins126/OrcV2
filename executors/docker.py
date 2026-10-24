"""Esecuzione di comandi in un container Docker isolato.

È l'esecutore usato in produzione: ogni comando prodotto dal modello viene
eseguito in un container effimero, senza rete, con filesystem in sola lettura e
risorse limitate. L'unico punto di contatto con l'host è la cartella di lavoro,
montata su `/workspace`.

Nota di design (tesi):
    L'isolamento è un investimento con tre rese distinte, ed è per questo che
    occupa una posizione più centrale di quanto suggerisca la parola "sicurezza":
      1. **safety** — il modello può sbagliare o essere indotto a comandi
         distruttivi; il container ne limita gli effetti al workspace. È un
         differenziatore esplicito rispetto a lavori affini (OI-MAS dichiara
         l'assenza di safety come proprio limite);
      2. **validità della misura** — un ambiente identico e ripulito a ogni
         esecuzione è la condizione perché costo e qualità osservati siano
         confrontabili tra modelli diversi;
      3. **parallelismo** — nello swarm (M4) container separati permettono a più
         agenti di lavorare senza interferire.

Prerequisito operativo:
    Richiede che il daemon Docker sia in esecuzione. Se non lo è, ogni comando
    fallisce: l'errore torna al modello come osservazione, ma l'agente non potrà
    concludere task che richiedono la shell.

Limiti noti:
    - L'utente del container è fissato a `1000:1000`: i file creati nel workspace
      appartengono a quell'UID, che può non coincidere con quello dell'host.
    - Allo scadere del timeout il container viene fermato con `docker kill`; se
      anche il `kill` fallisce (Docker bloccato), il container puo' restare vivo.
    - Il limite ai container contemporanei (`ContainerLimiter`) usa `fcntl`, che
      esiste su macOS e Linux, non su Windows.
"""

import fcntl
import logging
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from executors.base import CommandExecutor
from task_model import VerificationError

log = logging.getLogger(__name__)

#: Reti ammesse. `host` o una rete con nome aprirebbero la sandbox verso la
#: macchina o verso altri container senza che nessuno l'abbia deciso.
RETI_AMMESSE = ("none", "bridge")


#: Tempo massimo concesso al `docker kill` dopo un timeout. Un `kill` sano risponde in
#: meno di un secondo; con Docker Desktop sotto carico puo' volerci qualche secondo. Piu'
#: corto rischierebbe di liberare il posto con il container ancora vivo.
KILL_TIMEOUT_S = 10

#: Sotto questa attesa per un posto non si scrive nulla nel ledger: ogni comando
#: aggiungerebbe una riga inutile.
SANDBOX_WAIT_EVENT_S = 0.1


class EventSink(Protocol):
    """Dove annotare un fatto tecnico (in pratica il `CurrentRun` dell'agente)."""

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Registra un fatto della run che non e' un consumo."""


class ContainerLimiter:
    """Limita quanti container possono girare nello stesso momento, anche fra processi.

    Il limite riguarda una risorsa unica, la macchina (memoria, processore, demone
    Docker): per questo di norma ne esiste una sola istanza per processo, quella di
    modulo (`shared_limiter`), e chi ne vuole una propria (un test, un uso
    particolare) la passa a `DockerExecutor`.

    I posti sono `max_concurrent` file in `slots_dir`: prendere un posto vuol dire
    bloccare uno di quei file con `fcntl.flock`. Il blocco e' del sistema operativo,
    quindi vale fra thread e fra **processi diversi** (due campagne lanciate da due
    terminali) che usano la stessa cartella, e si scioglie da solo se il processo
    muore, anche per un crash o un Ctrl+C: nessun posto resta bloccato per sempre.

    Limiti noti:
        - Processi con `max_concurrent` diversi sulla stessa cartella: vale il
          limite piu' alto (chi ha 6 usa i file 0-5, chi ha 4 i file 0-3).
        - L'attesa di un posto ha un tempo massimo solo se dato (`max_wait_s`; il
          limitatore di modulo usa `config.DOCKER_ATTESA_POSTO_MAX_S`): il `timeout`
          dell'esecutore conta da quando il container parte. Il tempo in coda si
          legge nel ledger (evento `sandbox_wait`).
        - Il posto libero si cerca ogni `poll_s` secondi: l'ordine fra chi aspetta
          non e' garantito (nessuna coda equa).
        - Il container puo' restare vivo con il posto gia' libero se il processo
          muore (`kill -9`) durante un `docker run`: provato con Docker vero il 24
          ott. Su un'eccezione, Ctrl+C compreso, il container si toglie per nome con
          `docker rm -f` prima di liberare il posto; gli orfani di un processo morto
          li toglie `cleanup_orphans` all'avvio della campagna.
    """

    def __init__(self, max_concurrent: int, slots_dir: str | Path, *, poll_s: float = 0.05,
                 max_wait_s: float | None = None):
        """Prepara i posti.

        Args:
            max_concurrent: container al massimo vivi insieme.
            slots_dir: cartella dei file dei posti, condivisa da chi deve rispettare
                lo stesso limite.
            poll_s: ogni quanto riprovare quando i posti sono tutti presi.
            max_wait_s: attesa massima per un posto; `None` aspetta senza limite.

        Raises:
            ValueError: se `max_concurrent` non e' positivo o `max_wait_s` e'
                negativo. Si controlla prima di creare la cartella, per non
                lasciarne di orfane.
        """
        if max_concurrent < 1:
            raise ValueError(f"max_concurrent deve essere almeno 1, non {max_concurrent}")
        if max_wait_s is not None and max_wait_s < 0:
            raise ValueError(f"max_wait_s non puo' essere negativo, non {max_wait_s}")
        self.max_concurrent = max_concurrent
        self.slots_dir = Path(slots_dir)
        self.poll_s = poll_s
        self.max_wait_s = max_wait_s
        self.slots_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def slot(self) -> Iterator[float]:
        """Prende un posto, aspettando se sono tutti occupati, e lo rilascia sempre.

        Yields:
            I secondi passati ad aspettare il posto.

        Raises:
            SandboxSlotTimeout: nessun posto libero entro `max_wait_s`.
        """
        inizio = time.monotonic()
        while True:
            for indice in range(self.max_concurrent):
                fd = os.open(self.slots_dir / f"slot-{indice}.lock", os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                    continue
                except BaseException:
                    # Un errore diverso da «occupato» (per esempio un disco che non
                    # supporta i lock): il descrittore non deve restare aperto.
                    os.close(fd)
                    raise
                try:
                    yield time.monotonic() - inizio
                finally:
                    # Chiudere il descrittore scioglie gia' il blocco: `close` deve
                    # avvenire anche se lo sblocco esplicito fallisse.
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)
                return
            atteso = time.monotonic() - inizio
            if self.max_wait_s is not None and atteso >= self.max_wait_s:
                raise SandboxSlotTimeout(
                    f"nessun posto della sandbox libero dopo {atteso:.1f} s "
                    f"({self.max_concurrent} occupati)")
            resta = None if self.max_wait_s is None else self.max_wait_s - atteso
            time.sleep(self.poll_s if resta is None else min(self.poll_s, resta))


_shared: ContainerLimiter | None = None
_shared_lock = threading.Lock()


def shared_limiter() -> ContainerLimiter:
    """Il limitatore unico di modulo, creato alla prima richiesta.

    Legge `config.DOCKER_MAX_CONCURRENT` e `config.DOCKER_SLOTS_DIR` **una volta
    sola**: cambiarli dopo non ha effetto (e' voluto: il limite non deve cambiare a
    meta' lavoro), salvo `reset_shared_limiter`.
    """
    global _shared
    with _shared_lock:
        if _shared is None:
            import config
            _shared = ContainerLimiter(config.DOCKER_MAX_CONCURRENT,
                                       Path(config.DOCKER_SLOTS_DIR).expanduser(),
                                       max_wait_s=config.DOCKER_ATTESA_POSTO_MAX_S)
        return _shared


def reset_shared_limiter() -> None:
    """Dimentica il limitatore di modulo (serve ai test, per ripartire da uno nuovo)."""
    global _shared
    with _shared_lock:
        _shared = None


class SandboxSlotTimeout(VerificationError):
    """Nessun posto libero nella sandbox entro l'attesa massima.

    E' un guasto della macchina, non del modello (P19-D4): in verifica la riga
    diventa `evaluation_failed` e resta fuori da `f`. Durante il lavoro
    dell'agente arriva come un errore qualunque della run.
    """


def remove_container(name: str, runner: Callable[..., Any] | None = None) -> None:
    """Toglie un container per nome, che sia vivo, fermo o mai partito.

    `docker kill` non toglie un container rimasto «Created» (tempo scaduto prima
    dell'avvio) e su quello `--rm` non scatta: `rm -f` si'. Un errore qui non deve
    nascondere quello che ha portato a chiamarla: si ignora.
    """
    esegui = runner if runner is not None else subprocess.run
    with suppress(Exception):
        esegui(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=KILL_TIMEOUT_S)


#: Prefissi dei nomi dei container del progetto: sandbox, renderer, script d'interazione.
ORPHAN_PREFIXES = ("orc-sandbox-", "orc-renderer-", "orc-eval-")
#: Margine oltre il tempo massimo di un container prima di considerarlo orfano.
ORPHAN_MARGIN_S = 30.0


def _creato(testo: str) -> datetime:
    """Data di creazione di `docker inspect` (RFC 3339 con nanosecondi) come datetime UTC."""
    base, _, resto = testo.strip().partition(".")
    return datetime.fromisoformat(base + ("+00:00" if resto.endswith("Z") or not resto else ""))


def cleanup_orphans(max_age_s: Mapping[str, float], *, created_grace_s: float = 60.0,
                    runner: Callable[..., Any] | None = None,
                    now: datetime | None = None) -> list[str]:
    """Toglie i container del progetto rimasti orfani; restituisce i nomi tolti.

    Si giudica per eta' (P19-D1), cosi' i container di una campagna viva in un
    altro terminale non si toccano: un container che ha superato il suo tempo
    massimo (`max_age_s[prefisso]`) di oltre 30 s, o uno mai partito («created»)
    da oltre `created_grace_s`, non appartiene piu' a nessuno.

    Args:
        max_age_s: tempo massimo di vita per prefisso del nome (`orc-sandbox-` ...).
        created_grace_s: dopo quanto un container mai partito e' orfano.
        runner: chi esegue i comandi `docker` (nei test, un finto).
        now: l'ora di riferimento (nei test, fissa).

    Una rimozione fallita e' un avviso nel log, non un errore: la campagna parte.
    """
    esegui = runner if runner is not None else subprocess.run
    adesso = now if now is not None else datetime.now(timezone.utc)
    elenco = esegui(["docker", "ps", "-a", "--filter", "name=orc-", "--format", "{{.Names}}"],
                    capture_output=True, text=True, timeout=30)
    # Il filtro di Docker cerca la sottostringa: si ricontrolla l'inizio del nome.
    nomi = [n for n in elenco.stdout.split() if n.startswith(tuple(max_age_s))]
    if not nomi:
        return []
    dettagli = esegui(["docker", "inspect", "--format", "{{.Name}}\t{{.State.Status}}\t{{.Created}}", *nomi],
                      capture_output=True, text=True, timeout=30)
    tolti: list[str] = []
    for riga in dettagli.stdout.splitlines():
        nome, stato, creato = riga.lstrip("/").split("\t")
        eta = (adesso - _creato(creato)).total_seconds()
        massimo = next(v for k, v in max_age_s.items() if nome.startswith(k))
        if eta <= (created_grace_s if stato == "created" else massimo + ORPHAN_MARGIN_S):
            continue
        esito = esegui(["docker", "rm", "-f", nome], capture_output=True, text=True, timeout=KILL_TIMEOUT_S)
        if esito.returncode == 0:
            tolti.append(nome)
        else:
            log.warning("Container orfano %s non rimosso: %s", nome, (esito.stderr or "").strip())
    return tolti


class SandboxImageMissing(Exception):
    """L'immagine della sandbox non esiste (o Docker non risponde)."""


def image_id(image: str) -> str | None:
    """Identificativo dell'immagine Docker, oppure `None` se non c'e' o Docker non risponde.

    Cerca l'immagine nell'elenco (`docker image ls`) e non con `docker image inspect`:
    con l'archivio immagini containerd di Docker Desktop, `inspect` sul nome corto risponde
    a tratti «No such image» anche con l'immagine presente e Docker acceso (osservato il
    12-13 ottobre 2026), mentre l'elenco la riporta. Un nome assente da' un elenco vuoto.
    """
    try:
        r = subprocess.run(
            ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", image],
            capture_output=True, text=True, timeout=30)
    except FileNotFoundError as errore:
        # Il comando non esiste: non e' uno stato transitorio, ritentare non serve.
        raise SandboxImageMissing(
            "il comando `docker` non e' installato o non e' nel PATH: "
            "installa Docker Desktop e avvialo") from errore
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    righe = r.stdout.split()
    return righe[0] if righe else None


def _attendi(secondi: float) -> None:
    """Pausa fra due tentativi. Funzione a se' perche' i test la sostituiscono."""
    time.sleep(secondi)


def ensure_image(image: str, *, inspect=None, attempts: int = 1, delay: float = 0.0,
                 sleep=None, max_total_s: float | None = None, clock=None) -> None:
    """Controlla che l'immagine della sandbox esista, prima di costruire agenti.

    Senza, ogni chiamata a `bash` fallirebbe con codice 125 e l'agente
    brucerebbe budget su errori inutili.

    Args:
        image: nome dell'immagine, come in `config.DOCKER_IMAGE`.
        inspect: chi legge l'identificativo; `None` usa `image_id`, cercata al
            momento della chiamata (cosi' i test possono sostituirla).
        attempts: quante volte chiedere prima di arrendersi. Il predefinito (1)
            e' il controllo istantaneo; i punti d'ingresso ne passano di piu'
            perche' Docker Desktop si spegne a riposo e nei primi secondi dopo
            il riavvio risponde «No such image» anche se l'immagine c'e'.
        delay: secondi fra un tentativo e l'altro (non dopo l'ultimo).
        sleep: come attendere; `None` usa la pausa vera (iniettabile nei test).
        max_total_s: tetto sul tempo REALE trascorso, pause e tentativi compresi.
            Senza, con Docker bloccato ogni tentativo puo' durare il suo timeout
            (30 s) e l'attesa reale sarebbe molto piu' lunga delle sole pause.
        clock: orologio monotono; `None` usa `time.monotonic` (iniettabile).

    Raises:
        SandboxImageMissing: se l'immagine non c'e' o Docker non risponde dopo
            tutti i tentativi; subito, senza attese, se il comando `docker` manca.
    """
    leggi = inspect if inspect is not None else image_id
    attendi = sleep if sleep is not None else _attendi
    orologio = clock if clock is not None else time.monotonic
    inizio = orologio()
    for tentativo in range(1, max(1, attempts) + 1):
        if leggi(image) is not None:
            return
        if tentativo >= attempts:
            break
        if max_total_s is not None and orologio() - inizio + delay >= max_total_s:
            break
        attendi(delay)
    raise SandboxImageMissing(
        f"immagine '{image}' non trovata (o Docker non raggiungibile). "
        f"Costruiscila dalla radice del progetto con: "
        f"docker build -f docker/sandbox.Dockerfile -t {image} docker/")


class DockerExecutor(CommandExecutor):
    """Esegue comandi shell in un container effimero e confinato.

    Attributes:
        workspace: percorso assoluto sull'host della cartella montata nel container.
        image: immagine Docker usata per il container.
        timeout: secondi oltre i quali l'esecuzione viene interrotta.
        memory: tetto di memoria del container (formato Docker, es. "512m").
        pids_limit: numero massimo di processi, come difesa contro le fork bomb.
    """

    def __init__(self, workspace="workspace", image="debian:bookworm-slim", timeout=60,
                 memory="512m", pids_limit="256", network="none",
                 limiter: ContainerLimiter | None = None,
                 event_sink: EventSink | None = None):
        """Prepara la configurazione del container e la cartella condivisa.

        Args:
            workspace: cartella dell'host da montare come `/workspace`.
            image: immagine Docker da usare.
            timeout: secondi concessi a ogni comando.
            memory: limite di memoria del container.
            pids_limit: limite di processi del container.
            network: `none` (nessuna rete, la base delle misure) oppure `bridge`
                (rete normale di Docker, la condizione "con internet"). La rete
                e' una proprieta' dell'agente per tutta la sua vita.
            limiter: limitatore dei container contemporanei. Se manca si usa quello
                unico di modulo (`shared_limiter`), cosi' il limite non si aggira
                per dimenticanza.
            event_sink: dove annotare le attese lunghe per un posto (evento
                `sandbox_wait`). Di norma il `CurrentRun` dell'agente; `None` per
                non annotare (per esempio la verifica di una campagna).

        Raises:
            ValueError: se la rete non e' fra quelle ammesse. Si controlla prima
                di creare la cartella, per non lasciarne di orfane.
        """
        if network not in RETI_AMMESSE:
            raise ValueError(
                f"rete '{network}' non ammessa: scegli fra {', '.join(RETI_AMMESSE)}")
        self.network = network
        self.workspace = os.path.abspath(workspace)
        # Se la cartella non esiste viene creata
        os.makedirs(self.workspace, exist_ok=True)
        self.image = image
        self.timeout = timeout
        self.memory = memory
        self.pids_limit = pids_limit
        self.limiter = limiter if limiter is not None else shared_limiter()
        self.event_sink = event_sink

    def _utente_e_permessi(self) -> list[str]:
        """Utente e permessi del container, secondo la rete.

        `none`: utente 1000 senza altri permessi, come sempre. `bridge`: il
        container parte come amministratore con quattro soli permessi (applicare
        il firewall e scendere a utente 1000); l'entrypoint dell'immagine li
        azzera prima di eseguire il comando, che gira quindi come utente 1000
        senza alcun permesso. Vedi `docker/sandbox-entrypoint.sh`.
        """
        if self.network != "bridge":
            return ["--user", "1000:1000"]
        return [
            "--user", "0:0",
            "--cap-drop", "ALL",
            "--cap-add", "NET_ADMIN", "--cap-add", "SETUID",
            "--cap-add", "SETGID", "--cap-add", "SETPCAP",
            "-e", "ORC_FIREWALL=1",
            "-e", "ORC_RUN_AS=1000:1000",
        ]

    def run(self, command: str) -> dict:
        """Esegue il comando in un container usa-e-getta.

        Le opzioni di `docker run` compongono la sandbox, ciascuna con uno scopo
        preciso:
            --rm            il container viene distrutto a fine comando: nessuno
                            stato sopravvive tra un'esecuzione e l'altra;
            --network       `none` di default: nessun accesso di rete (niente
                            esfiltrazione di dati né download di codice
                            arbitrario) e ambiente ripetibile. `bridge` solo
                            nella condizione sperimentale "con internet";
            --read-only     filesystem del container non scrivibile, così le
                            uniche modifiche possibili sono nel workspace;
            --tmpfs /tmp    area temporanea in memoria, necessaria perché molti
                            comandi falliscono senza una /tmp scrivibile;
            --memory        tetto di memoria;
            --pids-limit    tetto di processi (anti fork bomb);
            --user          esecuzione come utente non privilegiato, non root;
            --volume        unico canale verso l'host: la cartella di lavoro.

        Args:
            command: comando shell da eseguire dentro il container.

        Returns:
            Dizionario con `stdout`, `stderr` ed `exit_code`. Un comando fallito
            non è un'eccezione: l'esito negativo viene restituito e diventa
            un'osservazione da cui il modello può ripartire.

        Raises:
            subprocess.TimeoutExpired: se il comando supera il timeout.
            FileNotFoundError: se l'eseguibile `docker` non è installato.
        """
        # Un nome proprio per ogni container: serve a fermarlo se il comando non finisce.
        nome = f"orc-sandbox-{uuid.uuid4().hex[:12]}"
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", nome,
            "--network", self.network,
            "--read-only",
            "--tmpfs", "/tmp",
            "--memory", self.memory,
            "--pids-limit", self.pids_limit,
            *self._utente_e_permessi(),
            "--workdir", "/workspace",
            "--volume", f"{self.workspace}:/workspace",
            self.image,
            "bash", "-c", command,
        ]
        # Il posto si tiene fino a container fermo: anche il `kill` avviene dentro.
        with self.limiter.slot() as attesa:
            if self.event_sink is not None and attesa >= SANDBOX_WAIT_EVENT_S:
                # L'attesa e' un dato secondario: se annotarla fallisce si avvisa nel
                # log e il comando dell'agente parte lo stesso.
                try:
                    self.event_sink.append_event("sandbox_wait", {
                        "wait_s": round(attesa, 3),
                        "max_concurrent": self.limiter.max_concurrent,
                    })
                except Exception as errore:
                    log.warning("Evento sandbox_wait non registrato (%.3f s di attesa): %s",
                                attesa, errore)
            try:
                r = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=self.timeout)
            except BaseException:
                # `timeout` di `subprocess.run` ferma il programma `docker`, non il container,
                # e un Ctrl+C lo stesso: un ciclo infinito resterebbe vivo per sempre. Lo si
                # toglie per nome, anche se non era ancora partito; l'errore arriva comunque
                # a chi ha chiamato.
                remove_container(nome)
                raise
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
