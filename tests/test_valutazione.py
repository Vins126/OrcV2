"""I passi di uno script si dichiarano, si eseguono e danno «funziona» come dice il protocollo.

Nota di design (tesi):
    Qui non c'e' ne' browser ne' server: il contesto e' un oggetto finto che
    annota quando viene aperto e chiuso. La parte con Playwright si prova con
    Docker vero (`ORC_INTEGRATION=1`).
"""

import types
from contextlib import contextmanager

import pytest

from task_model import CampaignError
from valutazione.libreria import (
    FALLITO,
    INTERFACCIA,
    NON_VALUTABILE,
    ROTTA,
    SUPERATO,
    Fallito,
    NonValutabile,
    ScriptError,
    esegui,
    passo,
    raccogli,
    rotta,
)


def _modulo(**funzioni) -> types.ModuleType:
    m = types.ModuleType("script_finto")
    for nome, f in funzioni.items():
        setattr(m, nome, f)
    return m


def _contesti():
    """Fabbrica di contesti finti: ogni passo ne riceve uno nuovo, aperto e chiuso."""
    aperti: list[int] = []
    chiusi: list[int] = []

    @contextmanager
    def nuovo():
        n = len(aperti)
        aperti.append(n)
        try:
            yield {"n": n}
        finally:
            chiusi.append(n)
    return nuovo, aperti, chiusi


def _ok(c):
    pass


def _ko(c):
    raise Fallito("non c'e'")


def _nv(c):
    raise NonValutabile("POST /api/files: 404")


def _stati(punteggio):
    return {e.id: e.stato for e in punteggio.esiti}


# ── Dichiarazione ──────────────────────────────────────────────────────────

def test_v1_i_passi_si_raccolgono_nell_ordine_in_cui_sono_scritti():
    @passo("1", origine="testo: a")
    def p1(c): pass

    @passo("2", origine="testo: b", dipende=("1",))
    def p2(c): pass

    @rotta("R1", origine="contratto: crea")
    def r1(c): pass

    passi = raccogli(_modulo(p1=p1, p2=p2, r1=r1, altro=lambda: None))

    assert [(p.id, p.tipo) for p in passi] == [("1", INTERFACCIA), ("2", INTERFACCIA), ("R1", ROTTA)]
    assert passi[1].dipende == ("1",) and passi[0].origine == "testo: a"


def test_v2_un_id_doppio_e_un_errore():
    @passo("1", origine="x")
    def a(c): pass

    @passo("1", origine="y")
    def b(c): pass

    with pytest.raises(ScriptError, match="'1'"):
        raccogli(_modulo(a=a, b=b))


def test_v3_una_dipendenza_inesistente_o_successiva_e_un_errore():
    @passo("1", origine="x", dipende=("9",))
    def a(c): pass

    with pytest.raises(ScriptError, match="'9'"):
        raccogli(_modulo(a=a))

    @passo("1", origine="x", dipende=("2",))
    def b(c): pass

    @passo("2", origine="y")
    def d(c): pass

    with pytest.raises(ScriptError, match="'2'"):
        raccogli(_modulo(b=b, d=d))


def test_v4_l_errore_e_un_errore_del_progetto():
    assert issubclass(ScriptError, CampaignError)


# ── Esecuzione e punteggio ─────────────────────────────────────────────────

def _p(id_, f, tipo=INTERFACCIA, dipende=()):
    from valutazione.libreria import Passo
    return Passo(id=id_, tipo=tipo, origine="o", funzione=f, dipende=dipende)


def test_v5_tutti_superati_vale_100():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _ok), _p("2", _ok)], nuovo)
    assert r.funziona == 100 and r.funziona_server is None
    assert _stati(r) == {"1": SUPERATO, "2": SUPERATO}


def test_v6_un_atteso_mancato_e_un_passo_fallito():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _ok), _p("2", _ko)], nuovo)
    assert r.funziona == 50
    esito = next(e for e in r.esiti if e.id == "2")
    assert esito.stato == FALLITO and "non c'e'" in esito.motivo


def test_v7_non_valutabile_esce_dal_denominatore():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _ok), _p("2", _ko), _p("3", _nv), _p("4", _nv)], nuovo)
    assert r.funziona == 50                      # 1 superato su 2 valutabili
    assert _stati(r)["3"] == NON_VALUTABILE


def test_v8_chi_dipende_da_un_fallito_fallisce_senza_essere_eseguito():
    chiamato = []
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _ko), _p("2", lambda c: chiamato.append(1), dipende=("1",))], nuovo)
    assert chiamato == []
    assert _stati(r) == {"1": FALLITO, "2": FALLITO}
    assert "1" in next(e for e in r.esiti if e.id == "2").motivo


def test_v9_chi_dipende_da_un_non_valutabile_e_non_valutabile():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _nv), _p("2", _ok, dipende=("1",)), _p("3", _ok)], nuovo)
    assert _stati(r) == {"1": NON_VALUTABILE, "2": NON_VALUTABILE, "3": SUPERATO}
    assert r.funziona == 100


def test_v10_un_eccezione_qualunque_e_un_passo_fallito_e_si_prosegue():
    def rotto(c):
        raise RuntimeError("Timeout 5000ms exceeded")

    nuovo, _, _ = _contesti()
    r = esegui([_p("1", rotto), _p("2", _ok)], nuovo)
    esito = next(e for e in r.esiti if e.id == "1")
    assert esito.stato == FALLITO and "Timeout" in esito.motivo
    assert _stati(r)["2"] == SUPERATO


def test_v11_le_rotte_danno_un_punteggio_a_parte():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _ok), _p("R1", _ok, ROTTA), _p("R2", _ko, ROTTA), _p("R3", _ko, ROTTA),
                _p("R4", _ok, ROTTA)], nuovo)
    assert r.funziona == 100
    assert r.funziona_server == 50


def test_v12_nessun_passo_valutabile_vale_0():
    nuovo, _, _ = _contesti()
    r = esegui([_p("1", _nv), _p("2", _nv)], nuovo)
    assert r.funziona == 0


def test_v13_ogni_passo_ha_un_contesto_nuovo_sempre_chiuso():
    nuovo, aperti, chiusi = _contesti()
    visti = []
    esegui([_p("1", lambda c: visti.append(c["n"])), _p("2", _ko),
            _p("3", lambda c: visti.append(c["n"]))], nuovo)
    assert visti == [0, 2]
    assert aperti == chiusi == [0, 1, 2]


def test_v14_un_contesto_che_non_si_apre_fa_fallire_solo_quel_passo():
    tentativi = []

    @contextmanager
    def nuovo():
        tentativi.append(1)
        if len(tentativi) == 1:
            raise RuntimeError("server non ripartito")
        yield {}

    r = esegui([_p("1", _ok), _p("2", _ok)], nuovo)
    assert _stati(r) == {"1": FALLITO, "2": SUPERATO}
    assert "server" in next(e for e in r.esiti if e.id == "1").motivo
