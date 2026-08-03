"""Composizione dei tool disponibili all'agente.

Questo package espone `ALL_TOOLS`, l'insieme di capacità con cui l'agente viene
equipaggiato. È qui, e solo qui, che i pezzi vengono messi insieme: si sceglie
quale executor usare, si crea il workspace e si passano i limiti definiti in
`config`.

Nota di design (tesi):
    Il modulo funge da *composition root*: concentra in un unico punto le
    decisioni di cablaggio, lasciando le altre classi ignare di come vengano
    costruite. Sostituire `DockerExecutor` con `LocalExecutor`, o dare a worker
    diversi insiemi di tool diversi (scenario M2), significa intervenire qui
    senza toccare né l'agente né i tool.

Limite noto:
    Il workspace è creato dal percorso relativo `"workspace"`, risolto rispetto
    alla directory da cui si lancia il programma. Avviando il progetto da un'altra
    cartella si otterrebbe quindi un workspace diverso.
"""

import config
from executors.docker import DockerExecutor
from tools.bash import BashTool
from tools.read_file import ReadFileTool
from tools.write_file import WriteFileTool
from workspace import Workspace

# Unica istanza di workspace, condivisa dai tool di lettura/scrittura e montata
# nel container: agente e sandbox devono vedere la stessa cartella.
ws = Workspace("workspace")

#: Insieme dei tool passati all'Agent. L'ordine non è significativo.
ALL_TOOLS = [
    BashTool(DockerExecutor(
        ws.path,
        image=config.DOCKER_IMAGE,
        timeout=config.EXEC_TIMEOUT,
        memory=config.DOCKER_MEMORY,
        pids_limit=config.DOCKER_PIDS_LIMIT,
    )),
    ReadFileTool(ws),
    WriteFileTool(ws),
]
