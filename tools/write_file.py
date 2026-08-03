"""Tool di scrittura di file nel workspace.

Nota di design (tesi):
    È il tool con cui l'agente produce il proprio artefatto. Nella prospettiva di
    M2 questa è l'operazione centrale della topologia "team su git": il progetto
    non nasce da un merge finale degli output, ma **cresce incrementalmente**
    nel workspace condiviso, una scrittura alla volta. Ne segue che la qualità
    andrà misurata sullo *stato del workspace* ai checkpoint (compila? i test
    passano?), non sulle singole risposte dei modelli.
"""

from tools.base import Tool
from workspace import Workspace


class WriteFileTool(Tool):
    """Scrive contenuto testuale in un file interno al workspace.

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
        return "write_file"

    @property
    def description(self) -> str:
        """Descrizione mostrata al modello per orientarne la scelta."""
        return "Scrive testo in un file, creandolo o sovrascrivendolo"

    @property
    def parameters(self) -> dict:
        """Schema degli argomenti: `path` e `content`, entrambi obbligatori."""
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "il percorso del file da scrivere",
                },
                "content": {
                    "type": "string",
                    "description": "il contenuto del file da scrivere",
                }
            },
            "required": ["path", "content"],
        }

    def execute(self, args: dict) -> dict:
        """Risolve il percorso e vi scrive il contenuto, sovrascrivendo se esiste.

        Args:
            args: dizionario con le chiavi `path` e `content`.

        Returns:
            Un dizionario di conferma con `status` e il `path` richiesto. Si
            restituisce il percorso **originale** e non quello assoluto risolto,
            per non rivelare al modello la struttura reale del filesystem
            dell'host e per mantenerlo coerente con ciò che lui stesso ha chiesto.

        Raises:
            ValueError: se il percorso esce dal workspace (sollevata da `resolve`).
            OSError: se la scrittura fallisce (es. cartella intermedia assente).
        """
        path = self.workspace.resolve(args["path"])
        with open(path, "w") as f:
            f.write(args["content"])
        return {
            "status": "ok",
            "path": args["path"],
        }
