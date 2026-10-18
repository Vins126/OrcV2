"""M3.1b-b e M3.3: `read_file` e `write_file` fra controllo e uso, e sotto scritture concorrenti.

Il rischio non e' il carico su `Workspace.resolve` (una funzione pura): e' l'istante fra
il controllo del percorso e l'apertura del file. Se in quell'istante qualcuno (un comando
nel container, che vede la stessa cartella) mette al posto del file un link simbolico
verso l'esterno, un `open` normale lo seguirebbe e uscirebbe dal workspace.
"""

import os
import stat
import threading

import pytest

from tools.read_file import ReadFileTool
from tools.write_file import WriteFileTool
from workspace import Workspace


class WorkspaceConScambio(Workspace):
    """Controlla il percorso come sempre, poi, prima che il tool lo apra, lo sostituisce
    con un link simbolico verso `bersaglio`: e' la corsa fra controllo e uso."""

    def __init__(self, path, bersaglio):
        super().__init__(path)
        self.bersaglio = bersaglio

    def resolve(self, user_path):
        p = super().resolve(user_path)
        if os.path.lexists(p):
            os.remove(p)
        os.symlink(self.bersaglio, p)
        return p


@pytest.fixture
def esterno(tmp_path):
    f = tmp_path / "fuori" / "segreto.txt"
    f.parent.mkdir()
    f.write_text("dati dell'host")
    return f


# -- B: link simbolico messo fra controllo e uso ----------------------------

def test_write_non_segue_un_link_messo_dopo_il_controllo(tmp_path, esterno):
    ws = WorkspaceConScambio(tmp_path / "ws", esterno)

    WriteFileTool(ws).execute({"path": "a.txt", "content": "nuovo"})

    assert esterno.read_text() == "dati dell'host"           # l'host non e' stato toccato
    dentro = tmp_path / "ws" / "a.txt"
    assert not dentro.is_symlink() and dentro.read_text() == "nuovo"


def test_read_rifiuta_un_link_messo_dopo_il_controllo(tmp_path, esterno):
    ws = WorkspaceConScambio(tmp_path / "ws", esterno)

    with pytest.raises(OSError):
        ReadFileTool(ws).execute({"path": "a.txt"})


def test_un_link_verso_fuori_gia_presente_resta_bloccato_dal_controllo(tmp_path, esterno):
    ws = Workspace(tmp_path / "ws")
    os.symlink(esterno, tmp_path / "ws" / "link.txt")

    with pytest.raises(ValueError):
        ReadFileTool(ws).execute({"path": "link.txt"})
    with pytest.raises(ValueError):
        WriteFileTool(ws).execute({"path": "link.txt", "content": "x"})
    assert esterno.read_text() == "dati dell'host"


def test_un_link_interno_al_workspace_si_legge_e_si_scrive_ancora(tmp_path):
    ws = Workspace(tmp_path / "ws")
    (tmp_path / "ws" / "vero.txt").write_text("ciao")
    os.symlink(tmp_path / "ws" / "vero.txt", tmp_path / "ws" / "alias.txt")

    assert ReadFileTool(ws).execute({"path": "alias.txt"}) == {"content": "ciao"}
    WriteFileTool(ws).execute({"path": "alias.txt", "content": "nuovo"})
    assert (tmp_path / "ws" / "vero.txt").read_text() == "nuovo"


# -- D: scrittura atomica ---------------------------------------------------

def test_chi_legge_vede_sempre_un_file_intero_mai_vuoto_ne_misto(tmp_path):
    ws = Workspace(tmp_path / "ws")
    scrivi, leggi = WriteFileTool(ws), ReadFileTool(ws)
    a, b = "A" * 200_000, "B" * 200_000
    scrivi.execute({"path": "f.txt", "content": a})
    smetti = threading.Event()
    visti: set[str] = set()

    def scrittore(testo):
        while not smetti.is_set():
            scrivi.execute({"path": "f.txt", "content": testo})

    thread = [threading.Thread(target=scrittore, args=(t,)) for t in (a, b)]
    for t in thread:
        t.start()
    try:
        for _ in range(300):
            contenuto = leggi.execute({"path": "f.txt"})["content"]
            visti.add("A" if contenuto == a else "B" if contenuto == b else "ROTTO")
    finally:
        smetti.set()
        for t in thread:
            t.join()

    assert "ROTTO" not in visti
    assert (tmp_path / "ws" / "f.txt").read_text() in (a, b)   # vince l'ultimo, ma sempre intero


def test_un_file_nuovo_e_leggibile_dal_container(tmp_path):
    """Il container gira come utente 1000: un file 0600 dell'host non lo leggerebbe."""
    ws = Workspace(tmp_path / "ws")

    WriteFileTool(ws).execute({"path": "n.txt", "content": "x"})

    assert stat.S_IMODE(os.stat(tmp_path / "ws" / "n.txt").st_mode) == 0o644


def test_sovrascrivere_conserva_i_permessi_del_file(tmp_path):
    """Uno script reso eseguibile non deve perdere il permesso quando viene riscritto."""
    ws = Workspace(tmp_path / "ws")
    script = tmp_path / "ws" / "run.sh"
    script.write_text("echo vecchio")
    os.chmod(script, 0o755)

    WriteFileTool(ws).execute({"path": "run.sh", "content": "echo nuovo"})

    assert script.read_text() == "echo nuovo"
    assert stat.S_IMODE(os.stat(script).st_mode) == 0o755


def test_nessun_file_temporaneo_resta_dopo_una_scrittura_riuscita(tmp_path):
    ws = Workspace(tmp_path / "ws")

    WriteFileTool(ws).execute({"path": "f.txt", "content": "x"})

    assert sorted(os.listdir(tmp_path / "ws")) == ["f.txt"]


def test_se_la_sostituzione_fallisce_il_file_vecchio_resta_e_il_temporaneo_sparisce(tmp_path, monkeypatch):
    ws = Workspace(tmp_path / "ws")
    (tmp_path / "ws" / "f.txt").write_text("vecchio")

    def rotto(*a, **k):
        raise OSError("disco pieno")

    monkeypatch.setattr("tools.write_file.os.replace", rotto)
    with pytest.raises(OSError):
        WriteFileTool(ws).execute({"path": "f.txt", "content": "nuovo"})

    assert (tmp_path / "ws" / "f.txt").read_text() == "vecchio"
    assert sorted(os.listdir(tmp_path / "ws")) == ["f.txt"]


def test_cartella_intermedia_assente_resta_un_errore_del_sistema(tmp_path):
    ws = Workspace(tmp_path / "ws")

    with pytest.raises(OSError):
        WriteFileTool(ws).execute({"path": "manca/f.txt", "content": "x"})


# -- rilievi della revisione del 17 ott -------------------------------------

@pytest.mark.parametrize("percorso", [".", "", "sotto", "sotto/.."])
def test_scrivere_su_una_cartella_e_un_errore_che_non_tocca_niente(tmp_path, percorso, monkeypatch):
    """Con la radice, la cartella che la contiene e' FUORI dal workspace: li' non deve nascere nulla,
    neanche per un istante (il temporaneo verrebbe poi cancellato, ma un crash lo lascerebbe li')."""
    ws = Workspace(tmp_path / "ws")
    (tmp_path / "ws" / "sotto").mkdir()
    prima = sorted(os.listdir(tmp_path))
    import tempfile
    temporanei: list = []
    vero = tempfile.mkstemp
    monkeypatch.setattr("tools.write_file.tempfile.mkstemp",
                        lambda *a, **k: temporanei.append(k.get("dir")) or vero(*a, **k))

    with pytest.raises(IsADirectoryError):
        WriteFileTool(ws).execute({"path": percorso, "content": "x"})

    assert temporanei == []                       # il controllo arriva prima di creare qualsiasi file

    assert sorted(os.listdir(tmp_path)) == prima
    assert sorted(os.listdir(tmp_path / "ws")) == ["sotto"]


def test_un_file_in_sola_lettura_resta_protetto(tmp_path):
    """Un file reso 0444 apposta (per esempio i test di un esercizio) non si sovrascrive."""
    ws = Workspace(tmp_path / "ws")
    protetto = tmp_path / "ws" / "test_ufficiali.py"
    protetto.write_text("originale")
    os.chmod(protetto, 0o444)

    with pytest.raises(PermissionError):
        WriteFileTool(ws).execute({"path": "test_ufficiali.py", "content": "barato"})

    assert protetto.read_text() == "originale"
    assert sorted(os.listdir(tmp_path / "ws")) == ["test_ufficiali.py"]


def test_leggere_una_cartella_da_un_errore_che_nomina_il_percorso(tmp_path):
    ws = Workspace(tmp_path / "ws")
    (tmp_path / "ws" / "sotto").mkdir()

    with pytest.raises(IsADirectoryError) as errore:
        ReadFileTool(ws).execute({"path": "sotto"})

    assert "sotto" in str(errore.value)
