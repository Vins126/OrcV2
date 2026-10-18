"""M3.2: contabile di squadra (scelta T = A, interfaccia C2, conteggio C-b).

La squadra somma i contabili dei membri a ogni lettura, senza un contatore proprio, e
conta solo la spesa fatta **dopo** l'ingresso di ciascun membro. Il test chiave confronta
due fonti indipendenti: il totale di squadra e i riepiloghi riletti dai file dei ledger.
"""

import threading

import pytest

from accounting.base import Accountant, SpendReader
from accounting.errors import TeamMembershipError
from accounting.ledger import RunLedger
from accounting.ledger_accountant import LedgerAccountant
from accounting.memory import InMemoryAccountant
from accounting.record import UsageRecord
from accounting.team import TeamAccountant


class RegistroFinto:
    def cost(self, _model, _unit, quantity, route=None):
        return quantity * 0.001


def _contabile():
    return InMemoryAccountant(RegistroFinto())


def _spendi(contabile, volte=1, token=10):
    for _ in range(volte):
        contabile.register(UsageRecord(model="m", quantities={"input_tokens": token}))


# -- interfaccia (C2) -------------------------------------------------------

def test_la_squadra_legge_la_spesa_ma_non_registra_consumi():
    squadra = TeamAccountant()

    assert isinstance(squadra, SpendReader)
    assert not isinstance(squadra, Accountant)
    assert not hasattr(squadra, "register")


def test_ogni_contabile_e_anche_un_lettore_di_spesa():
    assert isinstance(_contabile(), SpendReader)


# -- somme e attribuzione ---------------------------------------------------

def test_squadra_vuota_ha_zero():
    squadra = TeamAccountant()

    assert (squadra.total_cost, squadra.call_count, squadra.breakdown()) == (0.0, 0, {})


def test_il_totale_e_la_somma_dei_membri_e_si_aggiorna_mentre_spendono():
    a, b = _contabile(), _contabile()
    squadra = TeamAccountant()
    squadra.add("a", a)
    squadra.add("b", b)

    _spendi(a, 2)            # 2 x 0,01
    assert squadra.total_cost == pytest.approx(0.02)
    _spendi(b, 1, token=30)  # 0,03, letto senza chiamare nulla sulla squadra
    assert squadra.total_cost == pytest.approx(0.05)
    assert squadra.call_count == 3


def test_il_dettaglio_attribuisce_ogni_spesa_al_suo_membro():
    a, b = _contabile(), _contabile()
    squadra = TeamAccountant()
    squadra.add("planner", a)
    squadra.add("worker", b)
    _spendi(a, 1)
    _spendi(b, 3)

    assert squadra.breakdown() == {
        "planner": {"cost": pytest.approx(0.01), "calls": 1},
        "worker": {"cost": pytest.approx(0.03), "calls": 3},
    }


# -- C-b: si conta dall'ingresso in squadra ---------------------------------

def test_la_spesa_fatta_prima_di_entrare_non_conta():
    veterano = _contabile()
    _spendi(veterano, 5)                 # 0,05 spesi altrove, prima
    squadra = TeamAccountant()
    squadra.add("veterano", veterano)

    assert (squadra.total_cost, squadra.call_count) == (0.0, 0)
    _spendi(veterano, 1)
    assert squadra.total_cost == pytest.approx(0.01)
    assert squadra.call_count == 1
    assert veterano.total_cost == pytest.approx(0.06)   # il contabile dell'agente resta di tutta la vita


# -- errori -----------------------------------------------------------------

def test_lo_stesso_contabile_due_volte_e_un_errore_di_doppio_conteggio():
    a = _contabile()
    squadra = TeamAccountant()
    squadra.add("a", a)

    with pytest.raises(TeamMembershipError):
        squadra.add("a-bis", a)


def test_due_membri_con_lo_stesso_nome_sono_un_errore():
    squadra = TeamAccountant()
    squadra.add("a", _contabile())

    with pytest.raises(TeamMembershipError):
        squadra.add("a", _contabile())


def test_una_squadra_non_puo_contenere_se_stessa():
    squadra = TeamAccountant()

    with pytest.raises(TeamMembershipError):
        squadra.add("io", squadra)


# -- concorrenza: il test chiave della fase ---------------------------------

def test_con_agenti_concorrenti_il_totale_di_squadra_coincide_con_i_ledger(tmp_path):
    """Due fonti indipendenti: la somma in memoria della squadra e i summary su disco."""
    agenti, squadra = [], TeamAccountant()
    for n in range(6):
        ledger = RunLedger(root=tmp_path, task=f"t{n}", run_id=f"r{n}")
        contabile = LedgerAccountant(_contabile(), ledger)
        squadra.add(f"agente-{n}", contabile)
        agenti.append((contabile, ledger))
    via = threading.Barrier(len(agenti))

    def lavora(contabile, n):
        via.wait()
        for i in range(40):
            contabile.register(UsageRecord(model="m", quantities={"input_tokens": n + i}))

    thread = [threading.Thread(target=lavora, args=(c, n)) for n, (c, _) in enumerate(agenti)]
    for t in thread:
        t.start()
    for t in thread:
        t.join()

    sommari = {f"agente-{n}": led.close(status="completed", iterations=1) for n, (_, led) in enumerate(agenti)}
    assert squadra.total_cost == pytest.approx(sum(s["total_cost"] for s in sommari.values()))
    assert squadra.call_count == sum(s["usage_count"] for s in sommari.values()) == 6 * 40
    for nome, voce in squadra.breakdown().items():           # ogni spesa attribuibile al suo agente
        assert voce["cost"] == pytest.approx(sommari[nome]["total_cost"])
        assert voce["calls"] == sommari[nome]["usage_count"]


def test_aggiungere_un_membro_mentre_altri_leggono_non_rompe_le_letture():
    squadra = TeamAccountant()
    errori: list[BaseException] = []
    smetti = threading.Event()

    def leggi():
        while not smetti.is_set():
            try:
                _ = (squadra.total_cost, squadra.call_count, squadra.breakdown())
            except BaseException as e:      # "dictionary changed size during iteration"
                errori.append(e)

    lettori = [threading.Thread(target=leggi) for _ in range(4)]
    for t in lettori:
        t.start()
    try:
        for n in range(300):
            squadra.add(f"m{n}", _contabile())
    finally:
        smetti.set()
        for t in lettori:
            t.join()

    assert errori == []
    assert len(squadra.breakdown()) == 300


# -- rilievi della revisione del 17 ott -------------------------------------

def _con_tempo_massimo(funzione, secondi=3):
    """Esegue in un thread: se resta bloccato (deadlock) il test fallisce invece di appendersi."""
    esito: dict = {}

    def corpo():
        try:
            funzione()
        except BaseException as e:
            esito["errore"] = e

    t = threading.Thread(target=corpo, daemon=True)
    t.start()
    t.join(secondi)
    assert not t.is_alive(), "bloccato: deadlock"
    return esito.get("errore")


def test_due_squadre_che_si_contengono_a_vicenda_sono_un_errore_non_un_blocco():
    s1, s2 = TeamAccountant(), TeamAccountant()
    s1.add("s2", s2)

    errore = _con_tempo_massimo(lambda: s2.add("s1", s1))

    assert isinstance(errore, TeamMembershipError)


def test_un_ciclo_piu_lungo_e_un_errore():
    a, b, c = TeamAccountant(), TeamAccountant(), TeamAccountant()
    a.add("b", b)
    b.add("c", c)

    errore = _con_tempo_massimo(lambda: c.add("a", a))

    assert isinstance(errore, TeamMembershipError)


def test_una_sottosquadra_senza_cicli_si_somma_normalmente():
    contabile = _contabile()
    reparto, azienda = TeamAccountant(), TeamAccountant()
    reparto.add("a", contabile)
    azienda.add("reparto", reparto)

    _spendi(contabile, 2)

    assert azienda.total_cost == pytest.approx(0.02)
    assert azienda.call_count == 2
