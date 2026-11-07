"""Skill dell'harness (task 7, P25-D1): catalogo, scaricamento e strumento `load_skill`.

Lo schema e' quello di Claude Code: nel contesto stanno solo nome e descrizione di
ogni skill; il testo intero entra quando il modello chiama `load_skill`; script e
file allegati si usano con `bash`. Le skill stanno nell'immagine della sandbox in
/opt/skills, a un commit fissato per repo (`docker/skills.toml`).

Docker non serve: l'esecutore e lo scaricamento sono finti.
"""

import io
import tarfile
from pathlib import Path

import pytest

import config
from tools.load_skill import (SKILLS_ROOT, LoadSkillTool, SkillCatalogError, SkillEntry,
                              load_catalog)

MANIFESTO = Path("docker/skills.toml")


# ── Catalogo ──────────────────────────────────────────────────────────────

def test_k1_il_catalogo_vero_ha_le_skill_approvate():
    catalogo = load_catalog(MANIFESTO)

    assert sorted(s.name for s in catalogo) == [
        "design-taste-frontend", "frontend-design", "systematic-debugging", "ui-ux-pro-max",
        "verification-before-completion", "webapp-testing",
    ]


def test_k2_ogni_voce_e_fissata_a_un_commit_e_ha_una_descrizione_breve():
    for skill in load_catalog(MANIFESTO):
        assert len(skill.commit) == 40 and all(c in "0123456789abcdef" for c in skill.commit)
        assert "/" in skill.repo and skill.path
        assert 0 < len(skill.description) <= 300
        assert skill.license


def _scrivi(tmp_path: Path, testo: str) -> Path:
    percorso = tmp_path / "skills.toml"
    percorso.write_text(testo)
    return percorso


VOCE = '''
[[skills]]
name = "{name}"
repo = "o/r"
commit = "{commit}"
path = "skills/x"
license = "MIT"
description = "Una riga."
'''


@pytest.mark.parametrize("name, commit", [
    ("ok", "abc"),                       # commit non intero
    ("../fuori", "a" * 40),              # nome che esce da /opt/skills
    ("Con Spazi", "a" * 40),
])
def test_k3_voci_non_valide_sono_un_errore_parlante(tmp_path, name, commit):
    with pytest.raises(SkillCatalogError):
        load_catalog(_scrivi(tmp_path, VOCE.format(name=name, commit=commit)))


def test_k4_nomi_doppi_sono_un_errore(tmp_path):
    voce = VOCE.format(name="uno", commit="a" * 40)
    with pytest.raises(SkillCatalogError, match="uno"):
        load_catalog(_scrivi(tmp_path, voce + voce))


def test_k5_manifesto_assente_e_un_errore(tmp_path):
    with pytest.raises(SkillCatalogError):
        load_catalog(tmp_path / "manca.toml")


# ── Strumento load_skill ──────────────────────────────────────────────────

class EsecutoreFinto:
    def __init__(self, stdout="# Skill\ntesto", exit_code=0, stderr=""):
        self.comandi: list[str] = []
        self.risposta = {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}

    def run(self, command):
        self.comandi.append(command)
        return self.risposta


CATALOGO = [
    SkillEntry(name="frontend-design", repo="o/r", commit="a" * 40, path="p", license="MIT",
               description="Distinctive visual design."),
    SkillEntry(name="webapp-testing", repo="o/r", commit="b" * 40, path="q", license="MIT",
               description="Test a running web app with Playwright."),
]


def test_k6_nome_schema_e_descrizione_elencano_le_skill():
    tool = LoadSkillTool(EsecutoreFinto(), CATALOGO)

    assert tool.name == "load_skill"
    proprieta = tool.parameters["properties"]["name"]
    assert proprieta["enum"] == ["frontend-design", "webapp-testing"]
    assert tool.parameters["required"] == ["name"]
    for skill in CATALOGO:
        assert skill.name in tool.description and skill.description in tool.description


def test_k7_carica_il_testo_intero_dalla_sandbox_con_la_cartella_della_skill():
    lungo = "x" * 40_000          # piu' lungo del troncamento di bash: qui non si tronca
    esecutore = EsecutoreFinto(stdout=lungo)

    esito = LoadSkillTool(esecutore, CATALOGO).execute({"name": "webapp-testing"})

    assert esecutore.comandi == [f"cat {SKILLS_ROOT}/webapp-testing/SKILL.md"]
    testo = str(esito)
    assert lungo in testo
    assert f"{SKILLS_ROOT}/webapp-testing" in testo.split(lungo)[0]


@pytest.mark.parametrize("nome", ["manca", "../etc", "frontend-design; rm -rf /"])
def test_k8_un_nome_fuori_catalogo_e_un_errore_senza_toccare_la_sandbox(nome):
    esecutore = EsecutoreFinto()

    esito = LoadSkillTool(esecutore, CATALOGO).execute({"name": nome})

    assert "error" in esito and "frontend-design" in str(esito["error"])
    assert esecutore.comandi == []


def test_k9_un_errore_della_sandbox_arriva_al_modello():
    esecutore = EsecutoreFinto(stdout="", stderr="No such file", exit_code=1)

    esito = LoadSkillTool(esecutore, CATALOGO).execute({"name": "frontend-design"})

    assert "error" in esito and "No such file" in str(esito["error"])


# ── Scaricamento per la costruzione dell'immagine ─────────────────────────

def _tarball(prefisso: str, file: dict[str, str]) -> bytes:
    """Un archivio come quelli di codeload.github.com: tutto sotto una cartella radice."""
    dati = io.BytesIO()
    with tarfile.open(fileobj=dati, mode="w:gz") as archivio:
        for nome, testo in file.items():
            corpo = testo.encode()
            info = tarfile.TarInfo(f"{prefisso}/{nome}")
            info.size = len(corpo)
            archivio.addfile(info, io.BytesIO(corpo))
    return dati.getvalue()


def test_k10_lo_scaricamento_estrae_solo_la_cartella_della_skill(tmp_path):
    from fetch_skills import fetch_skills

    voce = SkillEntry(name="frontend-design", repo="o/r", commit="a" * 40,
                      path="skills/frontend-design", license="Apache-2.0", description="d")
    archivio = _tarball("r-" + "a" * 40, {
        "skills/frontend-design/SKILL.md": "# fd",
        "skills/frontend-design/scripts/x.py": "print(1)",
        "skills/altro/SKILL.md": "# no",
        "README.md": "no",
    })
    richieste = []

    def scarica(repo, commit):
        richieste.append((repo, commit))
        return archivio

    fetch_skills([voce], tmp_path / "out", download=scarica)

    assert richieste == [("o/r", "a" * 40)]
    radice = tmp_path / "out" / "frontend-design"
    assert (radice / "SKILL.md").read_text() == "# fd"
    assert (radice / "scripts" / "x.py").read_text() == "print(1)"
    assert not (tmp_path / "out" / "altro").exists()


def test_k11_una_skill_senza_skill_md_e_un_errore(tmp_path):
    from fetch_skills import fetch_skills

    voce = SkillEntry(name="vuota", repo="o/r", commit="a" * 40, path="skills/vuota",
                      license="MIT", description="d")
    archivio = _tarball("r-x", {"skills/vuota/README.md": "niente"})

    with pytest.raises(SkillCatalogError, match="vuota"):
        fetch_skills([voce], tmp_path / "out", download=lambda r, c: archivio)


def test_k12_un_archivio_con_percorsi_che_escono_e_respinto(tmp_path):
    from fetch_skills import fetch_skills

    voce = SkillEntry(name="cattiva", repo="o/r", commit="a" * 40, path="skills/cattiva",
                      license="MIT", description="d")
    archivio = _tarball("r-x", {"skills/cattiva/SKILL.md": "# ok",
                                "skills/cattiva/../../../../fuori.txt": "male"})

    with pytest.raises(SkillCatalogError):
        fetch_skills([voce], tmp_path / "out", download=lambda r, c: archivio)
    assert not (tmp_path / "fuori.txt").exists()


# ── Cablaggio nell'harness ────────────────────────────────────────────────

def test_k13_load_skill_e_fra_gli_strumenti_comuni(tmp_path):
    from tools import build_default_tools

    nomi = [t.name for t in build_default_tools(str(tmp_path / "a"))]

    assert nomi == ["bash", "read_file", "write_file", "view_site", "load_skill"]


def test_k14_il_prompt_di_sistema_nomina_load_skill_e_i_programmi_preinstallati():
    from agent import SYSTEM_PROMPT

    assert "`load_skill`" in SYSTEM_PROMPT
    for programma in ("playwright", "lighthouse", "biome", "htmlhint", "vnu", "hurl", "vitest"):
        assert programma in SYSTEM_PROMPT


def test_k15_i_limiti_della_sandbox_bastano_per_chromium_e_vite():
    # 512 MB, 256 processi e 60 s per comando non bastano a Chromium, a `npm install`
    # e alla build di Vite (4 nov 2026). Valgono per tutti i bracci (parita').
    assert config.DOCKER_MEMORY == "2g"
    assert config.DOCKER_PIDS_LIMIT == "1024"
    assert config.DOCKER_SHM_SIZE == "1g"
    assert config.EXEC_TIMEOUT == 300
    assert config.DOCKER_IMAGE == "orc-sandbox:r3h"


def test_k16_il_container_riceve_la_memoria_condivisa(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    from executors.docker import DockerExecutor

    visti = []
    monkeypatch.setattr("executors.docker.subprocess.run",
                        lambda a, **k: visti.append(list(a)) or NS(stdout="", stderr="", returncode=0))

    DockerExecutor(str(tmp_path), shm_size="1g").run("true")

    assert visti[0][visti[0].index("--shm-size") + 1] == "1g"


def test_k17_il_dockerfile_copia_le_skill_e_fissa_le_versioni():
    testo = Path("docker/sandbox.Dockerfile").read_text()

    assert f"{SKILLS_ROOT}" in testo
    for fissato in ("playwright==1.64.0", "lighthouse@13.5.0", "@biomejs/biome@2.5.15",
                    "htmlhint@1.9.2", "vitest@4.1.12", "vnu-jar@26.10.12", "8.0.1"):
        assert fissato in testo
