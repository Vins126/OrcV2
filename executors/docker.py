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
    - Allo scadere del timeout viene interrotto il processo client `docker run`,
      ma il container potrebbe restare in esecuzione.
"""

import os
import subprocess
import time

from executors.base import CommandExecutor

#: Reti ammesse. `host` o una rete con nome aprirebbero la sandbox verso la
#: macchina o verso altri container senza che nessuno l'abbia deciso.
RETI_AMMESSE = ("none", "bridge")


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
                 memory="512m", pids_limit="256", network="none"):
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
        docker_cmd = [
            "docker", "run",
            "--rm",
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
        r = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=self.timeout)
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
