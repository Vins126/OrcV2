"""Composizione dei tool disponibili all'agente.

Questo package espone `build_default_tools`, la factory con cui il punto di
ingresso costruisce gli strumenti. Qui, e solo qui, vengono scelti executor,
workspace e limiti.

Nota di design (tesi):
    Il modulo funge da *composition root*: concentra in un unico punto le
    decisioni di cablaggio, lasciando le altre classi ignare di come vengano
    costruite. Sostituire `DockerExecutor` con `LocalExecutor`, o dare a worker
    diversi insiemi di tool diversi (scenario M2), significa intervenire qui
    senza toccare né l'agente né i tool.

Non esistono istanze globali: importare `tools` non crea directory e non prepara
Docker. Questo evita effetti collaterali nei test e permette a run concorrenti di
ricevere workspace distinti.
"""

import config
from executors.docker import DockerExecutor
from tools.bash import BashTool
from tools.read_file import ReadFileTool
from tools.write_file import WriteFileTool
from workspace import Workspace

def build_default_tools(workspace_path: str) -> list:
    """Costruisce i tool standard, tutti confinati nello stesso workspace."""
    workspace = Workspace(workspace_path)
    executor = DockerExecutor(
        workspace.path,
        image=config.DOCKER_IMAGE,
        timeout=config.EXEC_TIMEOUT,
        memory=config.DOCKER_MEMORY,
        pids_limit=config.DOCKER_PIDS_LIMIT,
    )
    return [BashTool(executor), ReadFileTool(workspace), WriteFileTool(workspace)]
