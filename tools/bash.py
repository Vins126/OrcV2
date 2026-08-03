"""Tool di esecuzione di comandi shell.

Espone al modello la capacità di eseguire comandi, delegando l'esecuzione vera e
propria a un `CommandExecutor` iniettato dall'esterno.

Nota di design (tesi):
    La separazione tra *tool* ed *executor* è deliberata e ha valore
    sperimentale. `BashTool` decide **cosa** viene offerto al modello (il nome,
    la descrizione, il contratto degli argomenti); l'executor decide **dove** il
    comando viene eseguito (container isolato o macchina locale). Cambiare il
    livello di isolamento diventa così una questione di configurazione, non di
    riscrittura: si può misurare lo stesso agente in condizioni di sicurezza
    diverse senza alterarne il comportamento osservabile.
"""



from executors.base import CommandExecutor
from tools.base import Tool


class BashTool(Tool):
    """Permette al modello di eseguire comandi shell tramite un executor.

    Attributes:
        executor: strategia di esecuzione a cui il comando viene delegato.
    """

    def __init__(self, executor: CommandExecutor):
        """Inietta la strategia di esecuzione.

        Args:
            executor: implementazione di `CommandExecutor` (in produzione
                `DockerExecutor`, nei test o in sviluppo `LocalExecutor`).
        """
        self.executor = executor

    @property
    def name(self) -> str:
        """Nome esposto al modello."""
        return "bash"

    @property
    def description(self) -> str:
        """Descrizione mostrata al modello per orientarne la scelta."""
        return "Esegue un comando shell e restituisce stdout, stderr ed exit code"

    @property
    def parameters(self) -> dict:
        """Schema degli argomenti: un unico campo `command` obbligatorio."""
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "il comando shell da eseguire",
                },
            },
            "required": ["command"],
        }

    def execute(self, args: dict) -> dict:
        """Esegue il comando delegandolo all'executor.

        Args:
            args: dizionario con la chiave `command`.

        Returns:
            Il risultato prodotto dall'executor: `stdout`, `stderr` ed `exit_code`.
            Si restituiscono tutti e tre anche in caso di fallimento, perché un
            errore non è un'eccezione da nascondere ma un'informazione utile al
            modello per capire cosa è andato storto e riprovare diversamente.
        """
        return self.executor.run(args["command"])
