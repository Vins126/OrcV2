"""Test della guardia di sicurezza sui percorsi del workspace.

Verificano che `Workspace.resolve` accetti i percorsi legittimi e respinga i due
modi in cui un modello potrebbe uscire dalla cartella di lavoro: la risalita
relativa e il percorso assoluto.

Nota di design (tesi):
    Sono i test più rilevanti della suite dal punto di vista della sicurezza:
    coprono il confine che separa l'agente dal resto del filesystem. La fixture
    `tmp_path` di pytest fornisce a ogni test una cartella temporanea isolata,
    così le prove non lasciano tracce e non dipendono dallo stato della macchina.
"""

import pytest

from workspace import Workspace


def test_resolve_path_valido(tmp_path):
    """Un percorso relativo interno viene risolto senza errori."""
    ws = Workspace(str(tmp_path))               #Cartella temporanea
    risolto = ws.resolve("file.txt")            #Testo metodo
    assert risolto.endswith("file.txt")         #Se trovo nome corretto allroa funziona corretta


def test_resolve_blocca_traversal(tmp_path):
    """La risalita con `..` viene respinta.

    È l'attacco classico di *path traversal*: la stringa sembra relativa, ma una
    volta canonicalizzata punta fuori dal workspace.
    """
    ws = Workspace(str(tmp_path))               #Cartella temporanea
    with pytest.raises(ValueError):             #Mi aspetto un errore
        ws.resolve("../../etc/passwd")          #Testo metodo


def test_resolve_blocca_path_assoluto(tmp_path):
    """Un percorso assoluto viene respinto.

    Caso distinto dal precedente e altrettanto necessario: `os.path.join` scarta
    la cartella base quando il secondo argomento è assoluto, quindi senza la
    verifica finale il percorso uscirebbe dal workspace senza usare alcun `..`.
    """
    ws = Workspace(str(tmp_path))               #Cartella temporanea
    with pytest.raises(ValueError):             #Mi aspetto un errore
        ws.resolve("/etc/passwd")               #Testo metodo
