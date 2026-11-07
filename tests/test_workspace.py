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
    ws = Workspace(str(tmp_path))
    risolto = ws.resolve("file.txt")
    assert risolto.endswith("file.txt")


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


# ── H1 (task 7): il percorso del container ────────────────────────────────
# `bash` gira nel container con cartella di lavoro /workspace: un modello che fa
# `pwd` vede quel percorso e lo riusa con write_file/read_file, che girano
# sull'host. Nella prova del 3 nov 2026 questo errore e' comparso 13 volte.

@pytest.mark.parametrize("percorso, atteso", [
    ("/workspace/index.html", "index.html"),
    ("/workspace/public/app.js", "public/app.js"),
    ("/workspace", ""),
    ("/workspace/", ""),
])
def test_h1_il_percorso_del_container_si_traduce_nel_workspace(tmp_path, percorso, atteso):
    ws = Workspace(str(tmp_path))

    assert ws.resolve(percorso) == ws.resolve(atteso or ".")


@pytest.mark.parametrize("percorso", [
    "/workspace/../etc/passwd",     # risalita dopo il prefisso
    "/workspaces/x",                # solo un prefisso di stringa, non la cartella
    "/workspace-x/f",
    "/etc/passwd",
])
def test_h1_fuori_dal_container_resta_fuori(tmp_path, percorso):
    ws = Workspace(str(tmp_path))

    with pytest.raises(ValueError):
        ws.resolve(percorso)


def test_h1_l_errore_dice_al_modello_come_correggersi(tmp_path):
    ws = Workspace(str(tmp_path))

    with pytest.raises(ValueError, match="relative"):
        ws.resolve("/etc/passwd")
