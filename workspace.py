"""Cartella di lavoro isolata dell'agente.

Rappresenta l'unica porzione di filesystem che l'agente può leggere e scrivere
tramite i tool `read_file` e `write_file`. Ogni percorso richiesto dal modello
passa da qui per essere validato.

Nota di design (tesi):
    L'isolamento serve tre scopi distinti, ed è per questo che è un investimento
    conveniente:
      1. **sicurezza** — un modello che sbaglia (o un prompt malevolo) non può
         toccare file fuori dalla cartella;
      2. **riproducibilità della misura** — ogni esecuzione parte da uno stato
         noto e delimitato, condizione necessaria perché costo e qualità
         misurati siano confrontabili tra loro;
      3. **parallelismo** — nello swarm di M2 più agenti potranno lavorare senza
         calpestarsi, ciascuno con il proprio spazio.

    Questa classe copre la difesa a livello di *percorso*; la difesa a livello di
    *esecuzione* è delegata a `executors.docker.DockerExecutor`. Le due sono
    complementari: la prima impedisce di nominare file esterni, la seconda
    impedisce a un comando shell di raggiungerli comunque.
"""

import os

class Workspace:
    """Radice del filesystem accessibile all'agente, con guardia anti-traversal.

    Attributes:
        path: percorso assoluto e canonico della cartella di lavoro.
    """

    def __init__(self, path):
        """Crea (se assente) la cartella di lavoro e ne memorizza il percorso reale.

        Il percorso viene normalizzato con `realpath`, che risolve link simbolici
        e riferimenti relativi: è indispensabile che `self.path` sia già in forma
        canonica, perché `resolve` lo userà come termine di paragone.

        Args:
            path: percorso della cartella di lavoro, relativo o assoluto.
        """
        self.path = os.path.realpath(path)
        os.makedirs(self.path, exist_ok=True)

    def resolve(self, user_path):
        """Traduce un percorso richiesto dal modello in percorso assoluto sicuro.

        La verifica avviene **dopo** la canonicalizzazione, non prima: controllare
        la stringa grezza sarebbe aggirabile (con `..`, link simbolici o percorsi
        assoluti). Si risolve quindi il percorso fino alla sua forma reale e si
        verifica che la radice comune con il workspace sia il workspace stesso.

        Args:
            user_path: percorso indicato dal modello, atteso come relativo alla
                cartella di lavoro.

        Returns:
            Il percorso assoluto corrispondente, garantito interno al workspace.

        Raises:
            ValueError: se il percorso risolto cade fuori dal workspace. Copre sia
                i tentativi di risalita (`../../etc/passwd`) sia i percorsi
                assoluti (`/etc/passwd`), perché `os.path.join` scarta la base
                quando il secondo argomento è assoluto.
        """
        p = os.path.join(self.path, user_path)
        p = os.path.realpath(p)
        if os.path.commonpath([p, self.path]) != self.path:
            raise ValueError("Path is outside the workspace")
        return p
