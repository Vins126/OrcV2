"""Dichiarazione dei passi, esecuzione e punteggio «funziona» (R1.7).

Uno script di compito e' un modulo Python con funzioni decorate da `@passo`
(interfaccia) o `@rotta` (test diretti sul server). Ogni funzione riceve un
contesto nuovo, con il sito ripartito da uno stato pulito, e:
- finisce senza eccezioni -> superato;
- solleva `Fallito` o un'eccezione qualunque -> fallito;
- solleva `NonValutabile` (preparazione via rotte non riuscita) -> esce dal conteggio.

Nota di design (tesi):
    «funziona» = passi d'interfaccia superati / passi d'interfaccia valutabili x
    100; «funziona-server» = test delle rotte superati / test delle rotte x 100
    (PROTOCOLLO §6). Se un passo dipende da un altro che non e' superato, eredita
    l'esito senza essere eseguito: fallito se l'altro e' fallito, non valutabile
    se l'altro lo e'.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

from task_model import CampaignError

INTERFACCIA = "interfaccia"
ROTTA = "rotta"
SUPERATO = "superato"
FALLITO = "fallito"
NON_VALUTABILE = "non_valutabile"


class ScriptError(CampaignError):
    """Script di valutazione scritto male (id doppio, dipendenza inesistente)."""


class Fallito(Exception):
    """Un atteso del passo non e' verificato."""


class NonValutabile(Exception):
    """La preparazione del passo via rotte non e' riuscita."""


@dataclass(frozen=True)
class Passo:
    id: str
    tipo: str
    origine: str
    funzione: Callable[[Any], None]
    dipende: tuple[str, ...] = ()


@dataclass(frozen=True)
class Esito:
    id: str
    tipo: str
    stato: str
    motivo: str = ""


@dataclass(frozen=True)
class Punteggio:
    """Esito dello script: punteggi 0-100 e dettaglio per passo.

    `funziona_server` e' `None` se lo script non ha test delle rotte.
    """

    funziona: float
    funziona_server: float | None
    esiti: list[Esito]


_ATTRIBUTO = "_orc_passo"


def _decoratore(tipo: str, id: str, origine: str, dipende: tuple[str, ...]):
    def registra(funzione: Callable[[Any], None]) -> Callable[[Any], None]:
        setattr(funzione, _ATTRIBUTO, Passo(id=id, tipo=tipo, origine=origine,
                                            funzione=funzione, dipende=tuple(dipende)))
        return funzione
    return registra


def passo(id: str, *, origine: str, dipende: tuple[str, ...] = ()):
    """Dichiara un passo d'interfaccia; `origine` cita il caso di prova o la voce di checklist."""
    return _decoratore(INTERFACCIA, id, origine, dipende)


def rotta(id: str, *, origine: str, dipende: tuple[str, ...] = ()):
    """Dichiara un test diretto sulle rotte del contratto."""
    return _decoratore(ROTTA, id, origine, dipende)


def raccogli(modulo: ModuleType) -> list[Passo]:
    """I passi dichiarati in un modulo, nell'ordine in cui sono scritti.

    Raises:
        ScriptError: id ripetuto, o dipendenza da un passo che non esiste o che
            viene dopo (l'esecuzione segue l'ordine di scrittura).
    """
    passi = [getattr(f, _ATTRIBUTO) for f in vars(modulo).values() if hasattr(f, _ATTRIBUTO)]
    passi.sort(key=lambda p: p.funzione.__code__.co_firstlineno)
    visti: set[str] = set()
    for p in passi:
        if p.id in visti:
            raise ScriptError(f"passo '{p.id}' dichiarato due volte")
        for d in p.dipende:
            if d not in visti:
                raise ScriptError(f"il passo '{p.id}' dipende da '{d}', che non esiste prima di lui")
        visti.add(p.id)
    return passi


def _quota(esiti: list[Esito], tipo: str) -> float | None:
    """Superati / valutabili x 100 per un tipo; `None` se il tipo non ha passi."""
    del_tipo = [e for e in esiti if e.tipo == tipo]
    if not del_tipo:
        return None
    valutabili = [e for e in del_tipo if e.stato != NON_VALUTABILE]
    if not valutabili:
        return 0.0
    return 100 * sum(e.stato == SUPERATO for e in valutabili) / len(valutabili)


def esegui(passi: list[Passo], nuovo_contesto: Callable[[], AbstractContextManager[Any]]) -> Punteggio:
    """Esegue i passi in ordine, ciascuno con un contesto nuovo, e calcola i punteggi.

    Nessuna eccezione di un passo ferma lo script: diventa l'esito di quel passo.
    """
    esiti: list[Esito] = []
    stato_di: dict[str, str] = {}
    for p in passi:
        bloccante = next((d for d in p.dipende if stato_di[d] != SUPERATO), None)
        if bloccante is not None:
            stato = NON_VALUTABILE if stato_di[bloccante] == NON_VALUTABILE else FALLITO
            esito = Esito(p.id, p.tipo, stato, f"dipende dal passo '{bloccante}', {stato_di[bloccante]}")
        else:
            try:
                with nuovo_contesto() as contesto:
                    p.funzione(contesto)
                esito = Esito(p.id, p.tipo, SUPERATO)
            except NonValutabile as errore:
                esito = Esito(p.id, p.tipo, NON_VALUTABILE, str(errore))
            except Exception as errore:
                esito = Esito(p.id, p.tipo, FALLITO, f"{type(errore).__name__}: {errore}")
        esiti.append(esito)
        stato_di[p.id] = esito.stato
    funziona = _quota(esiti, INTERFACCIA)
    return Punteggio(funziona=funziona if funziona is not None else 0.0,
                     funziona_server=_quota(esiti, ROTTA), esiti=esiti)
