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

import errno
import os
import stat

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
            OSError: se il file non esiste, non e' leggibile, e' una cartella o e'
                diventato un link simbolico dopo il controllo del percorso.

        Nota:
            Le eccezioni non vengono catturate qui di proposito: l'Agent le
            trasforma in osservazioni testuali, così il modello *vede* l'errore
            (es. "file inesistente") e può correggersi da solo.
        """
        path = self.workspace.resolve(args["path"])
        # `O_NOFOLLOW`: se fra il controllo e l'apertura qualcuno ha messo al posto
        # del file un link simbolico, l'apertura fallisce invece di seguirlo fuori dal
        # workspace. `resolve` ha gia' risolto i link legittimi, quindi qui un link non
        # dovrebbe esserci. Limite noto: non copre una cartella intermedia scambiata.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        # Una cartella si apre, ma l'errore successivo nominerebbe il numero del
        # descrittore invece del percorso: il modello non capirebbe.
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            raise IsADirectoryError(errno.EISDIR, "e' una cartella, non un file", args["path"])
        with os.fdopen(fd, "r") as f:
            contenuto = f.read()
        return {"content": contenuto}
