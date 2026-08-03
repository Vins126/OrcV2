"""Esecuzione di comandi direttamente sulla macchina host.

⚠️ SENZA ISOLAMENTO. Il comando gira con i privilegi dell'utente corrente, con
accesso completo al filesystem e alla rete. Va usato solo in sviluppo o nei test,
quando Docker non è disponibile e i comandi eseguiti sono noti e innocui.
L'esecutore usato in produzione è `executors.docker.DockerExecutor`.

Nota di design (tesi):
    Questa classe esiste soprattutto come **termine di paragone**: dimostra che
    l'astrazione `CommandExecutor` regge davvero (due implementazioni molto
    diverse, stessi chiamanti) e permette, volendo, di quantificare l'overhead
    introdotto dalla sandbox misurando lo stesso task nelle due modalità.
"""

import subprocess

from executors.base import CommandExecutor

class LocalExecutor(CommandExecutor):
    """Esegue comandi shell sull'host, senza alcun isolamento.

    Attributes:
        timeout: secondi oltre i quali il comando viene interrotto.
    """

    def __init__(self, timeout: int = 60):
        """Configura il tempo massimo di esecuzione.

        Args:
            timeout: secondi concessi al comando prima dell'interruzione.
        """
        self.timeout = timeout

    def run(self, command: str) -> dict:
        """Esegue il comando tramite la shell di sistema.

        Args:
            command: comando shell da eseguire.

        Returns:
            Dizionario con `stdout`, `stderr` ed `exit_code`.

        Raises:
            subprocess.TimeoutExpired: se il comando supera il timeout.
        """
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=self.timeout
        )
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
