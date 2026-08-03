"""Tool di lettura di file dal workspace.

Nota di design (tesi):
    Esiste un tool dedicato alla lettura anche se il modello potrebbe ottenere lo
    stesso risultato con `bash` (`cat file`). La ridondanza è voluta:
      - il percorso passa dalla guardia del `Workspace`, quindi la lettura è
        vincolata alla cartella di lavoro anche quando la sandbox non è attiva;
      - il risultato torna come dato strutturato (`{"content": ...}`) invece che
        come testo indistinto mescolato a stderr;
      - non richiede l'avvio di un container, quindi è molto più rapido ed
        economico in latenza per l'operazione più frequente di un coding agent.
"""

from tools.base import Tool
from workspace import Workspace


class ReadFileTool(Tool):
    """Legge il contenuto testuale di un file interno al workspace.

    Attributes:
        workspace: workspace che valida e risolve i percorsi richiesti.
    """

    def __init__(self, workspace: Workspace):
        """Inietta il workspace su cui operare.

        Args:
            workspace: cartella di lavoro autorizzata.
        """
        self.workspace = workspace


    @property
    def name(self) -> str:
        """Nome esposto al modello."""
        return "read_file"

    @property
    def description(self) -> str:
        """Descrizione mostrata al modello per orientarne la scelta."""
        return "Legge il contenuto di un file di testo e lo restituisce"

    @property
    def parameters(self) -> dict:
        """Schema degli argomenti: un unico campo `path` obbligatorio."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "il percorso del file da leggere",
                },
            },
            "required": ["path"],
        }

    def execute(self, args: dict) -> dict:
        """Risolve il percorso e restituisce il contenuto del file.

        Args:
            args: dizionario con la chiave `path`, relativa al workspace.

        Returns:
            Un dizionario con la chiave `content` contenente il testo del file.

        Raises:
            ValueError: se il percorso esce dal workspace (sollevata da `resolve`).
            OSError: se il file non esiste o non è leggibile.

        Nota:
            Le eccezioni non vengono catturate qui di proposito: l'Agent le
            trasforma in osservazioni testuali, così il modello *vede* l'errore
            (es. "file inesistente") e può correggersi da solo.
        """
        path = self.workspace.resolve(args["path"])
        with open(path, "r") as f:
            contenuto = f.read()
        return {"content": contenuto}
