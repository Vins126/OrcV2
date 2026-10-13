"""Esercizi Python del benchmark polyglot di Aider come task di campagna.

Gli esercizi sono quelli di Exercism (licenza MIT, copyright Exercism) raccolti
nel repository `Aider-AI/polyglot-benchmark`: i 34 piu' difficili in Python.
Non stanno nel repo del progetto: li scarica `fetch_polyglot` da un archivio
fissato a un commit e ne verifica il contenuto con un hash.

Nota di design (tesi):
    Due cose proteggono la misura. La soluzione di riferimento
    (`.meta/example.py`) viene caricata ma **non** entra mai nel workspace
    dell'agente ne' nel prompt: se la vedesse, il test non misurerebbe nulla. E
    la verifica ripristina i file di test originali e lancia `pytest` ignorando
    `conftest.py` e i file di configurazione: modificare i test, o inserire un
    `conftest.py` che fa saltare tutto (e quindi "passare"), non deve contare
    come successo. Resta aperto, in teoria, qualunque altro modo di alterare
    l'interprete dal workspace (per esempio `sitecustomize.py`): e' un limite
    dichiarato, non coperto.
"""

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from task_model import CampaignError, Task

#: Commit di `Aider-AI/polyglot-benchmark` da cui si scaricano gli esercizi.
POLYGLOT_COMMIT = "7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f"
#: Hash del contenuto dei 34 esercizi estratti (non dell'archivio: GitHub non
#: garantisce archivi identici byte per byte nel tempo).
POLYGLOT_DIGEST = "eb7ae8e70eae358b8a748af0ee322ad51db603f0a2ade751ed4f5e8db2e444e5"
_PERCORSO_ESERCIZI = "python/exercises/practice"


class PolyglotError(CampaignError):
    """Errore nel caricamento o nello scaricamento degli esercizi."""


@dataclass(frozen=True)
class Exercise:
    """Un esercizio: cio' che l'agente vede, i test originali e la soluzione a parte.

    Attributes:
        name: nome della cartella (`two-bucket`).
        instructions: introduzione, istruzioni e appendice, in quest'ordine.
        solution_files: scheletri da completare, percorso -> contenuto.
        test_files: file di test originali, percorso -> contenuto.
        reference_files: soluzione di riferimento. Non va mai al modello.
    """

    name: str
    instructions: str
    solution_files: dict[str, str]
    test_files: dict[str, str]
    reference_files: dict[str, str]


def content_digest(root: Path) -> str:
    """Hash del contenuto di una cartella: dipende dai percorsi e dai byte dei file."""
    radice = Path(root)
    h = hashlib.sha256()
    for percorso in sorted(p for p in radice.rglob("*") if p.is_file()):
        h.update(percorso.relative_to(radice).as_posix().encode())
        h.update(b"\0")
        h.update(hashlib.sha256(percorso.read_bytes()).digest())
    return h.hexdigest()


def _leggi(cartella: Path, percorso: str, nome: str) -> str:
    file = cartella / percorso
    if not file.is_file():
        raise PolyglotError(f"esercizio '{nome}': manca il file '{percorso}'")
    return file.read_text()


def load_exercises(root: Path) -> list[Exercise]:
    """Legge tutti gli esercizi di una cartella, in ordine alfabetico.

    Per ogni esercizio i nomi dei file (scheletro, test, soluzione) si leggono da
    `.meta/config.json`, non si indovinano: `paasio`, per esempio, ha due file
    di test.

    Raises:
        PolyglotError: se la cartella non esiste o e' vuota, o se un esercizio
            non ha configurazione, istruzioni, scheletro o test.
    """
    radice = Path(root)
    if not radice.is_dir():
        raise PolyglotError(f"cartella degli esercizi non trovata: {radice}")
    cartelle = sorted(p for p in radice.iterdir() if p.is_dir())
    if not cartelle:
        raise PolyglotError(f"nessun esercizio in {radice}")

    esercizi = []
    for cartella in cartelle:
        nome = cartella.name
        config = json.loads(_leggi(cartella, ".meta/config.json", nome))
        files = config.get("files", {})
        pezzi = [
            file for file in (cartella / ".docs" / n for n in
                              ("introduction.md", "instructions.md", "instructions.append.md"))
            if file.is_file()
        ]
        if not (cartella / ".docs" / "instructions.md").is_file():
            raise PolyglotError(f"esercizio '{nome}': mancano le istruzioni")
        esercizi.append(Exercise(
            name=nome,
            instructions="\n\n".join(f.read_text().strip() for f in pezzi),
            solution_files={p: _leggi(cartella, p, nome) for p in files.get("solution", [])},
            test_files={p: _leggi(cartella, p, nome) for p in files.get("test", [])},
            reference_files={p: _leggi(cartella, p, nome) for p in files.get("example", [])},
        ))
        if not esercizi[-1].solution_files or not esercizi[-1].test_files:
            raise PolyglotError(f"esercizio '{nome}': config senza scheletro o senza test")
    return esercizi


def exercise_to_task(exercise: Exercise) -> Task:
    """Trasforma un esercizio in un task di campagna.

    Nel workspace vanno scheletro e test (la soluzione di riferimento mai).
    La verifica ripristina i test originali e lancia `pytest` senza `conftest.py`
    ne' configurazioni, senza cache e senza rete.
    """
    soluzioni = ", ".join(exercise.solution_files)
    test = ", ".join(exercise.test_files)
    prompt = (
        f"Devi risolvere l'esercizio '{exercise.name}'.\n\n"
        f"Le istruzioni (in inglese) sono queste:\n\n{exercise.instructions}\n\n"
        f"Implementa la soluzione nel file {soluzioni}, che trovi gia' nella cartella di lavoro "
        f"con lo scheletro da completare. I test sono in {test}: leggili per capire cosa "
        f"deve fare il codice e lanciali con `python3 -m pytest -q` per controllare il lavoro. "
        f"Non modificare i file di test: verranno ripristinati prima della verifica finale. "
        f"Hai finito quando tutti i test passano."
    )
    # La verifica gira in una cartella NUOVA con solo soluzione e test originali:
    # nel workspace l'agente puo' aver messo un `pytest.py` (che prenderebbe il
    # posto di pytest), un `conftest.py` o altro. `mktemp` sta nella /tmp del
    # container, che e' scrivibile anche con il filesystem in sola lettura.
    file_da_copiare = " ".join([*exercise.solution_files, *exercise.test_files])
    verify = (f'd=$(mktemp -d) && cp --parents {file_da_copiare} "$d" && cd "$d" && '
              "python3 -m pytest -q --noconftest -c /dev/null -p no:cacheprovider "
              + " ".join(exercise.test_files))
    return Task(
        id=exercise.name, prompt=prompt, verify=verify,
        files={**exercise.solution_files, **exercise.test_files},
        restore=dict(exercise.test_files),
    )


def load_tasks(root: Path, only: list[str] | None = None) -> list[Task]:
    """Task di tutti gli esercizi di una cartella, o solo di quelli indicati.

    Raises:
        PolyglotError: se `only` contiene un nome che non esiste. Si elencano i
            disponibili, cosi' un errore di battitura non fa partire una
            campagna sull'insieme sbagliato.
    """
    esercizi = load_exercises(root)
    if only is not None:
        disponibili = {e.name for e in esercizi}
        ignoti = [nome for nome in only if nome not in disponibili]
        if ignoti:
            raise PolyglotError(
                f"esercizi inesistenti: {', '.join(ignoti)}; "
                f"disponibili: {', '.join(sorted(disponibili))}")
        esercizi = [e for e in esercizi if e.name in only]
    return [exercise_to_task(e) for e in esercizi]


def _scarica(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as risposta:
        return risposta.read()


def fetch_polyglot(dest: Path, *, commit: str = POLYGLOT_COMMIT, digest: str = POLYGLOT_DIGEST,
                   download: Callable[[str], bytes] | None = None) -> Path:
    """Scarica gli esercizi al commit fissato e li mette in `dest`, dopo averli verificati.

    L'estrazione avviene in una cartella temporanea accanto a `dest`: se il
    contenuto non corrisponde all'hash atteso non resta nulla, e `dest` compare
    solo a verifica superata. Non sovrascrive mai una cartella esistente.

    Args:
        dest: cartella di destinazione; non deve esistere.
        commit: commit del repository da scaricare.
        digest: hash atteso del contenuto estratto (`content_digest`).
        download: chi scarica l'archivio dato l'URL; `None` usa la rete.

    Raises:
        PolyglotError: se `dest` esiste, se l'archivio non contiene gli esercizi
            o se il contenuto non corrisponde all'hash.
    """
    destinazione = Path(dest)
    if destinazione.exists():
        raise PolyglotError(f"la cartella {destinazione} esiste gia': non la sovrascrivo")

    scarica = download if download is not None else _scarica
    try:
        archivio = scarica(f"https://github.com/Aider-AI/polyglot-benchmark/archive/{commit}.tar.gz")
    except (urllib.error.URLError, OSError, TimeoutError) as errore:
        raise PolyglotError(f"scaricamento dalla rete non riuscito: {errore}") from errore

    destinazione.parent.mkdir(parents=True, exist_ok=True)
    temporanea = Path(tempfile.mkdtemp(prefix=".polyglot-", dir=destinazione.parent))
    try:
        estratti = temporanea / "estratti"
        prefisso = f"polyglot-benchmark-{commit}/{_PERCORSO_ESERCIZI}/"
        with tarfile.open(fileobj=_in_memoria(archivio), mode="r:gz") as tar:
            membri = [m for m in tar.getmembers() if m.name.startswith(prefisso)]
            if not any(m.isfile() for m in membri):
                raise PolyglotError(f"l'archivio non contiene {_PERCORSO_ESERCIZI}")
            tar.extractall(estratti, members=membri, filter="data")
        esercizi = estratti / prefisso.rstrip("/")
        trovato = content_digest(esercizi)
        if trovato != digest:
            raise PolyglotError(
                f"il contenuto scaricato non corrisponde a quello atteso "
                f"(atteso {digest[:12]}..., trovato {trovato[:12]}...)")
        esercizi.rename(destinazione)
    except PolyglotError:
        raise
    except (tarfile.TarError, EOFError, OSError) as errore:
        raise PolyglotError(f"archivio non valido o danneggiato: {errore}") from errore
    finally:
        shutil.rmtree(temporanea, ignore_errors=True)
    return destinazione


def _in_memoria(contenuto: bytes):
    import io
    return io.BytesIO(contenuto)
