"""Lo strumento `bash` tronca le uscite troppo lunghe prima di darle al modello (R2.2).

Nota di design (tesi):
    L'esito di uno strumento resta nella storia e si rimanda a ogni iterazione:
    un `npm install` da centinaia di migliaia di caratteri si pagherebbe come
    input fino a 30 volte. Si tengono l'inizio e, piu' lunga, la coda, dove di
    solito stanno gli errori; in mezzo un segnaposto dice quanto manca.
    L'executor riporta tutto: decide lo strumento cosa vede il modello.
"""

import pytest

import config
from executors.base import CommandExecutor
from tools.bash import BashTool


class ExecutorFinto(CommandExecutor):
    """Restituisce sempre lo stesso esito e ricorda i comandi ricevuti."""

    def __init__(self, stdout="", stderr="", exit_code=0):
        self.esito = {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
        self.comandi = []

    def run(self, command):
        self.comandi.append(command)
        return dict(self.esito)


def _bash(executor, **kwargs):
    kwargs.setdefault("max_chars", 100)
    kwargs.setdefault("head_chars", 25)
    return BashTool(executor, **kwargs)


def test_un_uscita_entro_il_limite_resta_intera():
    esito = _bash(ExecutorFinto(stdout="a" * 100, stderr="b" * 99)).execute({"command": "ls"})

    assert esito == {"stdout": "a" * 100, "stderr": "b" * 99, "exit_code": 0}


def test_un_uscita_lunga_tiene_inizio_e_coda_e_dice_quanto_manca():
    testo = "".join(f"{i:05d}" for i in range(1000))      # 5000 caratteri, tutti distinti

    esito = _bash(ExecutorFinto(stdout=testo)).execute({"command": "ls"})

    uscita = esito["stdout"]
    assert uscita.startswith(testo[:25])
    assert uscita.endswith(testo[-75:])
    assert "[... 4900 characters omitted ...]" in uscita
    assert len(uscita) < len(testo)


def test_stdout_e_stderr_si_troncano_ognuno_per_conto_suo():
    esito = _bash(ExecutorFinto(stdout="x" * 50, stderr="e" * 1000, exit_code=1)).execute(
        {"command": "make"})

    assert esito["stdout"] == "x" * 50
    assert "[... 900 characters omitted ...]" in esito["stderr"]
    assert esito["exit_code"] == 1


def test_appena_sopra_il_limite_non_si_tronca_se_il_segnaposto_allungherebbe_il_testo():
    esito = _bash(ExecutorFinto(stdout="a" * 101)).execute({"command": "ls"})

    assert esito["stdout"] == "a" * 101


def test_il_comando_arriva_all_executor_invariato():
    executor = ExecutorFinto()

    _bash(executor).execute({"command": "echo ciao"})

    assert executor.comandi == ["echo ciao"]


def test_i_limiti_di_default_vengono_dalla_configurazione():
    strumento = BashTool(ExecutorFinto())

    assert strumento.max_chars == config.BASH_OUTPUT_MAX_CHARS == 10_000
    assert strumento.head_chars == config.BASH_OUTPUT_HEAD_CHARS == 2_500


@pytest.mark.parametrize("max_chars, head_chars", [(50, 80), (-1, 0), (100, -1)])
def test_limiti_incoerenti_sono_un_errore_alla_costruzione(max_chars, head_chars):
    """Con `head_chars` oltre `max_chars` la coda diventerebbe negativa e il testo si allungherebbe."""
    with pytest.raises(ValueError):
        BashTool(ExecutorFinto(), max_chars=max_chars, head_chars=head_chars)


def test_tutto_l_inizio_e_nessuna_coda_e_ammesso():
    esito = _bash(ExecutorFinto(stdout="a" * 1000), max_chars=100, head_chars=100).execute(
        {"command": "ls"})

    assert esito["stdout"] == "a" * 100 + "\n[... 900 characters omitted ...]\n"
