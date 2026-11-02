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


import config
from executors.base import CommandExecutor
from tools.base import Tool


def truncate_output(text: str, max_chars: int, head_chars: int) -> str:
    """Accorcia un testo troppo lungo tenendo inizio e coda.

    In mezzo resta un segnaposto con il numero di caratteri tolti. Se il
    risultato non sarebbe piu' corto dell'originale, il testo resta intero.

    Args:
        text: uscita del comando.
        max_chars: caratteri tenuti in tutto, segnaposto escluso.
        head_chars: quanti di questi vengono dall'inizio; gli altri dalla coda.
    """
    if len(text) <= max_chars:
        return text
    omessi = len(text) - max_chars
    segnaposto = f"\n[... {omessi} characters omitted ...]\n"
    if max_chars + len(segnaposto) >= len(text):
        return text
    coda = max_chars - head_chars
    return text[:head_chars] + segnaposto + (text[-coda:] if coda else "")


class BashTool(Tool):
    """Permette al modello di eseguire comandi shell tramite un executor.

    Attributes:
        executor: strategia di esecuzione a cui il comando viene delegato.
    """

    def __init__(self, executor: CommandExecutor, *,
                 max_chars: int = config.BASH_OUTPUT_MAX_CHARS,
                 head_chars: int = config.BASH_OUTPUT_HEAD_CHARS):
        """Inietta la strategia di esecuzione e i limiti delle uscite.

        Args:
            executor: implementazione di `CommandExecutor` (in produzione
                `DockerExecutor`, nei test o in sviluppo `LocalExecutor`).
            max_chars: lunghezza oltre la quale `stdout` e `stderr` si troncano.
            head_chars: caratteri tenuti dall'inizio di un'uscita troncata.

        Raises:
            ValueError: un limite negativo, o `head_chars` oltre `max_chars`: la
                coda diventerebbe negativa e il testo si allungherebbe invece di
                accorciarsi.
        """
        if not 0 <= head_chars <= max_chars:
            raise ValueError(
                f"limiti di bash incoerenti: serve 0 <= head_chars <= max_chars, "
                f"non head_chars={head_chars}, max_chars={max_chars}")
        self.executor = executor
        self.max_chars = max_chars
        self.head_chars = head_chars

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
            `stdout` e `stderr` oltre `max_chars` si troncano ognuno per conto
            suo: l'esito resta nella storia e si rimanda a ogni iterazione.
        """
        esito = self.executor.run(args["command"])
        for flusso in ("stdout", "stderr"):
            if isinstance(esito.get(flusso), str):
                esito[flusso] = truncate_output(esito[flusso], self.max_chars, self.head_chars)
        return esito
