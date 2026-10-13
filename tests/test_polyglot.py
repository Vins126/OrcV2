"""Gli esercizi Python del benchmark polyglot di Aider diventano task di campagna.

Nota di design (tesi):
    Gli esercizi sono di Exercism (licenza MIT) e arrivano da un archivio GitHub
    fissato a un commit. Qui non si scarica niente: un finto `download` consegna
    un archivio costruito dal test, con la stessa struttura reale
    (`python/exercises/practice/<nome>/{.docs,.meta,<nome>.py,<nome>_test.py}`).

    Due cose proteggono la misura. La soluzione di riferimento
    (`.meta/example.py`) resta fuori dal workspace dell'agente, altrimenti il
    test non misurerebbe niente. E la verifica ripristina i file di test
    originali e ignora `conftest.py` e i file di configurazione di pytest:
    cambiare i test, o inserire un `conftest.py` che li fa passare, non deve
    contare come successo.
"""

import io
import json
import tarfile
from pathlib import Path

import pytest

from campaign import CampaignError, Task
from polyglot import (
    POLYGLOT_COMMIT,
    PolyglotError,
    content_digest,
    exercise_to_task,
    fetch_polyglot,
    load_exercises,
    load_tasks,
)


def _scrivi_esercizio(radice: Path, nome: str, *, test_files=None, appendice=None,
                      introduzione=None, config=True, con_test=True):
    """Costruisce una cartella di esercizio nella struttura reale di Exercism."""
    cartella = radice / nome
    (cartella / ".docs").mkdir(parents=True)
    (cartella / ".meta").mkdir()
    (cartella / ".docs" / "instructions.md").write_text(f"# Istruzioni di {nome}\n\nFai la cosa.\n")
    if appendice:
        (cartella / ".docs" / "instructions.append.md").write_text(appendice)
    if introduzione:
        (cartella / ".docs" / "introduction.md").write_text(introduzione)
    (cartella / f"{nome}.py").write_text("def risolvi():\n    pass\n")
    test_files = test_files or [f"{nome}_test.py"]
    if con_test:
        for f in test_files:
            (cartella / f).write_text(f"# test originale {f}\n")
    (cartella / ".meta" / "example.py").write_text("def risolvi():\n    return 42  # SOLUZIONE\n")
    if config:
        (cartella / ".meta" / "config.json").write_text(json.dumps({
            "files": {"solution": [f"{nome}.py"], "test": test_files,
                      "example": [".meta/example.py"]}}))
    return cartella


@pytest.fixture
def albero(tmp_path):
    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "uno", appendice="# Appendice di uno\n\nDettaglio extra.\n")
    _scrivi_esercizio(radice, "due", test_files=["due_test.py", "test_utils.py"],
                      introduzione="# Introduzione di due\n")
    return radice


# ── P1: caricamento degli esercizi ────────────────────────────────────────

def test_p1a_un_esercizio_ha_istruzioni_scheletro_e_test(albero):
    uno = next(e for e in load_exercises(albero) if e.name == "uno")

    assert "Istruzioni di uno" in uno.instructions
    assert "Appendice di uno" in uno.instructions            # l'appendice segue le istruzioni
    assert uno.instructions.index("Istruzioni") < uno.instructions.index("Appendice")
    assert uno.solution_files == {"uno.py": "def risolvi():\n    pass\n"}
    assert uno.test_files == {"uno_test.py": "# test originale uno_test.py\n"}


def test_p1a2_l_introduzione_viene_prima_delle_istruzioni(albero):
    due = next(e for e in load_exercises(albero) if e.name == "due")

    assert due.instructions.index("Introduzione di due") < due.instructions.index("Istruzioni di due")


def test_p1a3_tutti_i_file_di_test_elencati_nel_config_sono_letti(albero):
    due = next(e for e in load_exercises(albero) if e.name == "due")

    assert sorted(due.test_files) == ["due_test.py", "test_utils.py"]     # come paasio


def test_p1b_la_soluzione_di_riferimento_non_e_nel_workspace_ne_nel_prompt(albero):
    for esercizio in load_exercises(albero):
        task = exercise_to_task(esercizio)

        assert "SOLUZIONE" in esercizio.reference_files[".meta/example.py"]   # esiste, ma a parte
        assert all("SOLUZIONE" not in contenuto for contenuto in task.files.values())
        assert "SOLUZIONE" not in task.prompt
        assert not any(percorso.startswith(".meta") for percorso in task.files)


def test_p1c_un_esercizio_senza_config_o_senza_test_e_un_errore_parlante(tmp_path):
    radice = tmp_path / "practice"
    _scrivi_esercizio(radice, "senza-config", config=False)
    with pytest.raises(PolyglotError, match="senza-config"):
        load_exercises(radice)

    radice2 = tmp_path / "practice2"
    _scrivi_esercizio(radice2, "senza-test", con_test=False)
    with pytest.raises(PolyglotError, match="senza-test"):
        load_exercises(radice2)


def test_p1c2_una_cartella_vuota_o_inesistente_e_un_errore(tmp_path):
    with pytest.raises(PolyglotError):
        load_exercises(tmp_path / "non-esiste")
    (tmp_path / "vuota").mkdir()
    with pytest.raises(PolyglotError):
        load_exercises(tmp_path / "vuota")


# ── P2-P5: da esercizio a task ────────────────────────────────────────────

def test_p2_il_task_porta_scheletro_e_test_nel_workspace_con_gli_stessi_nomi(albero):
    task = exercise_to_task(next(e for e in load_exercises(albero) if e.name == "due"))

    assert isinstance(task, Task)
    assert task.id == "due"
    assert sorted(task.files) == ["due.py", "due_test.py", "test_utils.py"]


def test_p5_il_prompt_contiene_le_istruzioni_nomina_i_file_e_vieta_di_toccare_i_test(albero):
    task = exercise_to_task(next(e for e in load_exercises(albero) if e.name == "uno"))

    assert "Istruzioni di uno" in task.prompt
    assert "uno.py" in task.prompt and "uno_test.py" in task.prompt
    assert "pytest" in task.prompt
    assert "non modificare" in task.prompt.lower()


def test_p3_la_verifica_ripristina_i_test_originali_e_ignora_conftest_e_configurazioni(albero):
    task = exercise_to_task(next(e for e in load_exercises(albero) if e.name == "due"))

    assert task.restore == {"due_test.py": "# test originale due_test.py\n",
                            "test_utils.py": "# test originale test_utils.py\n"}
    for pezzo in ("pytest", "--noconftest", "-c /dev/null", "-p no:cacheprovider",
                  "due_test.py"):
        assert pezzo in task.verify, pezzo


def test_p3b_le_soluzioni_non_si_ripristinano(albero):
    task = exercise_to_task(next(e for e in load_exercises(albero) if e.name == "uno"))

    assert "uno.py" not in task.restore        # e' proprio il lavoro dell'agente


def test_p6_load_tasks_seleziona_per_nome_e_un_nome_ignoto_e_un_errore(albero):
    assert [t.id for t in load_tasks(albero)] == ["due", "uno"]       # ordine alfabetico
    assert [t.id for t in load_tasks(albero, only=["uno"])] == ["uno"]

    with pytest.raises(PolyglotError, match="inventato"):
        load_tasks(albero, only=["uno", "inventato"])


def test_p6b_polyglot_error_e_un_campaign_error():
    assert issubclass(PolyglotError, CampaignError)


# ── F: scaricamento verificato ────────────────────────────────────────────

def _archivio(commit: str, albero: Path, *, extra: dict[str, bytes] | None = None) -> bytes:
    """Un archivio con la forma di quelli di GitHub: una radice col nome del commit."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for percorso in sorted(albero.rglob("*")):
            if percorso.is_file():
                relativo = percorso.relative_to(albero)
                tar.add(percorso, arcname=f"polyglot-benchmark-{commit}/python/exercises/practice/{relativo}")
        for nome, contenuto in (extra or {}).items():
            info = tarfile.TarInfo(f"polyglot-benchmark-{commit}/{nome}")
            info.size = len(contenuto)
            tar.addfile(info, io.BytesIO(contenuto))
    return buffer.getvalue()


def test_f1_il_download_estrae_gli_esercizi_e_verifica_il_contenuto(albero, tmp_path):
    archivio = _archivio("abc123", albero, extra={"README.md": b"fuori dagli esercizi"})
    chiamate = []

    dest = fetch_polyglot(
        tmp_path / "dati", commit="abc123", digest=content_digest(albero),
        download=lambda url: chiamate.append(url) or archivio)

    assert "abc123" in chiamate[0] and chiamate[0].startswith("https://")
    assert [e.name for e in load_exercises(dest)] == ["due", "uno"]
    assert not (tmp_path / "dati" / "README.md").exists()      # solo la cartella degli esercizi


def test_f2_un_contenuto_diverso_da_quello_atteso_e_un_errore_e_non_lascia_nulla(albero, tmp_path):
    archivio = _archivio("abc123", albero)

    with pytest.raises(PolyglotError, match="contenuto"):
        fetch_polyglot(tmp_path / "dati", commit="abc123", digest="0" * 64,
                       download=lambda url: archivio)

    assert not (tmp_path / "dati").exists()


def test_f3_se_la_destinazione_esiste_gia_non_si_sovrascrive(albero, tmp_path):
    dest = tmp_path / "dati"
    dest.mkdir()
    (dest / "mio.txt").write_text("da non toccare")

    with pytest.raises(PolyglotError, match="esiste"):
        fetch_polyglot(dest, commit="abc123", digest=content_digest(albero),
                       download=lambda url: _archivio("abc123", albero))

    assert (dest / "mio.txt").read_text() == "da non toccare"


def test_f4_il_digest_dipende_dal_contenuto_e_dai_nomi(albero):
    prima = content_digest(albero)
    (albero / "uno" / "uno.py").write_text("def risolvi():\n    return 1\n")

    assert content_digest(albero) != prima


def test_f5_il_commit_fissato_e_quello_dichiarato_in_tesi():
    assert POLYGLOT_COMMIT == "7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f"


# ── Casi limite aggiunti dopo un terzo controllo del codice (ott 2026) ────

def test_r1_la_verifica_gira_in_una_cartella_pulita_con_solo_soluzione_e_test(albero):
    """Un `pytest.py` o un `conftest.py` messi dall'agente nel workspace non devono
    esistere per la verifica: si copiano solo i file elencati in una cartella
    nuova e si lancia `pytest` li'. La prova vera e' `test_polyglot_integration`."""
    task = exercise_to_task(next(e for e in load_exercises(albero) if e.name == "due"))

    assert "mktemp -d" in task.verify
    assert "cp --parents due.py due_test.py test_utils.py" in task.verify
    assert 'cd "$d"' in task.verify
    assert task.verify.index("cp --parents") < task.verify.index("python3 -m pytest")


def test_r4_un_errore_di_rete_nel_download_e_un_errore_del_progetto(tmp_path):
    import urllib.error

    def senza_rete(url):
        raise urllib.error.URLError("rete assente")

    with pytest.raises(PolyglotError, match="rete"):
        fetch_polyglot(tmp_path / "dati", commit="abc123", digest="0" * 64, download=senza_rete)
    assert not (tmp_path / "dati").exists()


@pytest.mark.parametrize("archivio", [b"non e' un tar", b"", b"\x1f\x8b\x08\x00troncato"])
def test_r4b_un_archivio_corrotto_e_un_errore_del_progetto_e_non_lascia_nulla(tmp_path, archivio):
    with pytest.raises(PolyglotError, match="archivio"):
        fetch_polyglot(tmp_path / "dati", commit="abc123", digest="0" * 64,
                       download=lambda url: archivio)

    assert not (tmp_path / "dati").exists()
    assert list(tmp_path.glob(".polyglot-*")) == []          # nemmeno la cartella temporanea
