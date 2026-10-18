"""Tool di scrittura di file nel workspace.

Nota di design (tesi):
    È il tool con cui l'agente produce il proprio artefatto. Nella prospettiva dello
    swarm (M4) questa è l'operazione centrale della topologia "team su git": il progetto
    non nasce da un merge finale degli output, ma **cresce incrementalmente**
    nel workspace condiviso, una scrittura alla volta. Ne segue che la qualità
    andrà misurata sullo *stato del workspace* ai checkpoint (compila? i test
    passano?), non sulle singole risposte dei modelli.
"""

import errno
import os
import stat
import tempfile

from tools.base import Tool
from workspace import Workspace

#: Permessi di un file nuovo: leggibile da tutti, perche' il container gira come utente
#: 1000, che puo' non coincidere con il proprietario sull'host.
MODO_FILE_NUOVO = 0o644


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

        La scrittura e' **atomica**: il testo va in un file temporaneo nella stessa
        cartella, che poi prende il posto di quello vero con `os.replace`. Ne seguono
        due garanzie:
          - chi legge vede sempre un file intero, il vecchio o il nuovo, mai vuoto o
            a meta'; fra due scrittori concorrenti vince l'ultimo (M3.3);
          - se fra il controllo del percorso e la scrittura qualcuno mette al suo
            posto un link simbolico verso l'esterno, `os.replace` sostituisce il link
            invece di seguirlo, e l'host resta intatto (M3.1b-b).
        Un file che esisteva conserva i suoi permessi (uno script eseguibile resta
        eseguibile); uno nuovo nasce con `MODO_FILE_NUOVO`.

        Limite noto: non copre una **cartella intermedia** sostituita con un link nello
        stesso istante; servirebbe aprire il percorso un pezzo alla volta (`openat`).

        Raises:
            ValueError: se il percorso esce dal workspace (sollevata da `resolve`).
            IsADirectoryError: se il percorso e' una cartella (anche la radice).
            PermissionError: se il file esiste ed e' in sola lettura.
            OSError: se la scrittura fallisce (es. cartella intermedia assente).
        """
        path = self.workspace.resolve(args["path"])
        # Prima di creare qualsiasi file. Su una cartella la scrittura fallirebbe comunque,
        # e per la radice la cartella che la contiene e' FUORI dal workspace: il temporaneo
        # nascerebbe li'. Un file reso di sola lettura apposta (per esempio i test di un
        # esercizio) resta protetto, come con il vecchio `open(path, "w")`.
        if os.path.isdir(path):
            raise IsADirectoryError(errno.EISDIR, "e' una cartella, non un file", args["path"])
        if os.path.isfile(path) and not os.access(path, os.W_OK):
            raise PermissionError(errno.EACCES, "file in sola lettura", args["path"])
        modo = self._modo_da_conservare(path)
        # `mkstemp` crea il file in modo esclusivo e non segue link: il nome e' nuovo.
        fd, temporaneo = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".orc-scrittura-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(args["content"])
                os.fchmod(f.fileno(), modo)
            os.replace(temporaneo, path)
        except BaseException:
            # Il file vero non e' stato toccato: si toglie solo il temporaneo.
            try:
                os.unlink(temporaneo)
            except FileNotFoundError:
                pass
            raise
        return {
            "status": "ok",
            "path": args["path"],
        }

    @staticmethod
    def _modo_da_conservare(path: str) -> int:
        """I permessi del file che si sta per sostituire, se e' un file normale."""
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            return MODO_FILE_NUOVO
        if stat.S_ISREG(info.st_mode):
            return stat.S_IMODE(info.st_mode)
        return MODO_FILE_NUOVO
