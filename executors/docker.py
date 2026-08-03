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
      3. **parallelismo** — nello swarm di M2 container separati permettono a più
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

from executors.base import CommandExecutor


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
                 memory="512m", pids_limit="256"):
        """Prepara la configurazione del container e la cartella condivisa.

        Args:
            workspace: cartella dell'host da montare come `/workspace`.
            image: immagine Docker da usare.
            timeout: secondi concessi a ogni comando.
            memory: limite di memoria del container.
            pids_limit: limite di processi del container.
        """
        self.workspace = os.path.abspath(workspace)
        # Se la cartella non esiste viene creata
        os.makedirs(self.workspace, exist_ok=True)
        self.image = image
        self.timeout = timeout
        self.memory = memory
        self.pids_limit = pids_limit

    def run(self, command: str) -> dict:
        """Esegue il comando in un container usa-e-getta.

        Le opzioni di `docker run` compongono la sandbox, ciascuna con uno scopo
        preciso:
            --rm            il container viene distrutto a fine comando: nessuno
                            stato sopravvive tra un'esecuzione e l'altra;
            --network none  nessun accesso di rete (niente esfiltrazione di dati
                            né download di codice arbitrario);
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
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp",
            "--memory", self.memory,
            "--pids-limit", self.pids_limit,
            "--user", "1000:1000",
            "--workdir", "/workspace",
            "--volume", f"{self.workspace}:/workspace",
            self.image,
            "bash", "-c", command,
        ]
        r = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=self.timeout)
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
