"""Esecuzione concorrente di lavori indipendenti su un gruppo di thread."""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

log = logging.getLogger(__name__)

J = TypeVar("J")
R = TypeVar("R")


class Admission(Enum):
    """Cosa decide chi governa le partenze quando un lavoro sta per iniziare."""

    START = "start"    # parte subito
    WAIT = "wait"      # non ora: si aspetta che un lavoro in corso finisca e si richiede
    STOP = "stop"      # nessun altro lavoro parte, i rimanenti restano non avviati


@dataclass(frozen=True)
class JobOutcome(Generic[J, R]):
    """L'esito di un lavoro.

    Attributes:
        index: posizione del lavoro nella lista data.
        job: il lavoro.
        started: falso se non e' mai partito (le partenze sono state fermate).
        result: cio' che ha restituito, se e' riuscito.
        error: l'eccezione che ha sollevato, se e' fallito.
    """

    index: int
    job: J
    started: bool
    result: R | None = None
    error: Exception | None = None


def run_parallel(jobs: Sequence[J], work: Callable[[J], R], *, max_workers: int,
                 admit: Callable[[J, int], Admission] | None = None,
                 on_done: Callable[[JobOutcome[J, R]], None] | None = None) -> list[JobOutcome[J, R]]:
    """Esegue `work` su ogni lavoro, al massimo `max_workers` alla volta.

    Il gruppo di thread ha gia' una coda: i lavori in piu' aspettano che un
    operaio si liberi. Qui non se ne aggiunge un'altra. Quello che si aggiunge e'
    **chi decide quando un lavoro parte**: le partenze le governa il thread
    principale, un lavoro alla volta, chiamando `admit` prima di ognuna. Cosi' chi
    tiene i conti (la spesa, i lavori in volo) li aggiorna da un solo thread, senza
    lock, e un tetto di spesa puo' guardare davvero lo stato corrente.

    Un errore di `work` non ferma gli altri: finisce nell'esito di quel lavoro.
    Un lavoro non parte finche' non c'e' un operaio libero e `admit` non dice `START`.

    Args:
        jobs: i lavori, nell'ordine in cui devono partire.
        work: cosa fare di un lavoro; gira su un thread del gruppo.
        max_workers: quanti lavori al massimo in corso insieme.
        admit: chiamata dal thread principale prima di far partire un lavoro, con
            il lavoro e il numero di quelli in volo. `START` lo fa partire; `WAIT`
            aspetta che uno in volo finisca e richiede (senza lavori in volo
            equivale a `STOP`, per non bloccarsi); `STOP` non fa partire piu'
            nessuno. Senza, partono tutti.
        on_done: chiamata dal thread principale alla fine di ogni lavoro avviato,
            anche dopo un errore o un Ctrl+C nel ciclo principale (vedi sotto).

    Returns:
        Un esito per lavoro, nell'ordine di `jobs`; i lavori mai partiti hanno
        `started=False`.

    Raises:
        ValueError: se `max_workers` e' minore di uno.
        BaseException: un errore di `admit`/`on_done` o un Ctrl+C risale dopo che
            i lavori gia' in volo sono finiti e sono arrivati a `on_done`.
    """
    if max_workers < 1:
        raise ValueError(f"max_workers deve essere almeno 1, non {max_workers}")

    esiti: list[JobOutcome[J, R] | None] = [None] * len(jobs)
    in_volo: dict[Future[tuple[R | None, Exception | None]], int] = {}
    prossimo = 0
    fermo = False

    def lavora(job: J) -> tuple[R | None, Exception | None]:
        try:
            return work(job), None
        except Exception as errore:   # un lavoro guasto non deve fermare gli altri
            return None, errore

    def registra(futuro: Future[tuple[R | None, Exception | None]]) -> JobOutcome[J, R]:
        indice = in_volo.pop(futuro)
        risultato, errore = futuro.result()
        esito = JobOutcome(index=indice, job=jobs[indice], started=True,
                           result=risultato, error=errore)
        esiti[indice] = esito
        return esito

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="orc-worker") as gruppo:
        try:
            while True:
                while not fermo and prossimo < len(jobs) and len(in_volo) < max_workers:
                    decisione = (admit(jobs[prossimo], len(in_volo))
                                 if admit is not None else Admission.START)
                    if decisione is Admission.START:
                        in_volo[gruppo.submit(lavora, jobs[prossimo])] = prossimo
                        prossimo += 1
                    elif decisione is Admission.WAIT and in_volo:
                        break                      # si aspetta un lavoro in volo e si richiede
                    else:
                        fermo = True               # STOP, o un WAIT che non finirebbe mai
                if not in_volo:
                    break
                fatti, _ = wait(in_volo, return_when=FIRST_COMPLETED)
                # Se piu' lavori finiscono insieme, si registrano in ordine di partenza:
                # il risultato non dipende da chi il sistema operativo ha svegliato prima.
                for futuro in sorted(fatti, key=lambda f: in_volo[f]):
                    esito = registra(futuro)
                    if on_done is not None:
                        on_done(esito)
        except BaseException:
            # Un errore di `admit`/`on_done` o un Ctrl+C durante l'attesa: non parte piu'
            # niente, ma i lavori in volo non si possono fermare (sono thread) e la loro
            # spesa e' reale. Si aspettano e ognuno arriva lo stesso a `on_done`, che
            # scrive il manifesto; un suo errore qui si annota soltanto, per non perdere
            # quello originale, che poi risale. Un secondo Ctrl+C interrompe anche
            # quest'attesa: le righe delle run ancora in volo restano solo nei loro ledger.
            for futuro in sorted(in_volo, key=lambda f: in_volo[f]):
                esito = registra(futuro)
                if on_done is not None:
                    try:
                        on_done(esito)
                    except Exception:
                        log.exception("on_done fallito per il lavoro %d dopo un'interruzione",
                                      esito.index)
            raise

    return [e if e is not None else JobOutcome(index=i, job=jobs[i], started=False)
            for i, e in enumerate(esiti)]
