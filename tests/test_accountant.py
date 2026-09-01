"""Test del contabile dei costi.

Coprono le tre responsabilita' di `InMemoryAccountant`: **calcolare** il costo
di una chiamata a partire dalle quantita' consumate, **conservare** il dettaglio
delle chiamate, e **sommare** i totali. Piu' le garanzie del contratto astratto.

Nota di design (tesi):
    Il registro qui e' un finto (`RegistroFinto`) con prezzi tondi, non il
    `ModelRegistry` vero: cosi' i test verificano il contabile e non la lettura
    del TOML, e i costi attesi restano verificabili a mente. E' la stessa
    ragione per cui `FakeClient` sostituisce l'SDK nei test dell'agente — ed e'
    possibile solo perche' il registro arriva per iniezione.

    Un unico test in fondo usa il registro reale, per garantire che i due pezzi
    combacino davvero.
"""

import pytest

from accounting import (
    Accountant,
    InMemoryAccountant,
    ModelRegistry,
    UnitNotFound,
    ModelNotFound,
    UsageRecord,
)
from accounting.errors import UnpricedUsage


class RegistroFinto:
    """Listino minimo con prezzi tondi, per rendere i costi verificabili a mente.

    Non eredita da `ModelRegistry` ne' legge file: espone solo il metodo che il
    contabile usa davvero, `cost(...)`. E' quanto basta, perche' il contabile
    non conosce il tipo del registro — gli serve solo che sappia rispondere.
    """

    def __init__(self, prezzi=None):
        """Args:
            prezzi: mappa unita' -> costo di UNA unita'. Default: 1 dollaro per
                token di input, 2 per quello di output.
        """
        self.prezzi = prezzi if prezzi is not None else {
            "input_tokens": 1.0,
            "output_tokens": 2.0,
        }
        self.chiamate = []   # traccia delle richieste ricevute

    def cost(self, model: str, unit: str, quantity: float) -> float:
        self.chiamate.append((model, unit, quantity))
        if unit not in self.prezzi:
            raise UnitNotFound(f"unita' '{unit}' non prevista dal registro finto")
        return quantity * self.prezzi[unit]


def _contabile(prezzi=None):
    """Crea un contabile con un registro finto."""
    return InMemoryAccountant(RegistroFinto(prezzi))


def _record(model="modello", **quantita):
    """Crea un record con le quantita' passate come argomenti nominali."""
    return UsageRecord(model=model, quantities=quantita)


# ── Calcolo del costo ─────────────────────────────────────────────────────

def test_costo_di_una_singola_unita():
    # 10 token input a $1 l'uno
    assert _contabile().register(_record(input_tokens=10)) == pytest.approx(10.0)


def test_costo_somma_tutte_le_unita():
    # 10 input a $1  +  5 output a $2  =  20
    assert _contabile().register(_record(input_tokens=10, output_tokens=5)) == pytest.approx(20.0)


def test_il_costo_viene_scritto_nel_record():
    # Il record arriva con cost=0.0 e deve uscire valorizzato: chi lo crea non
    # conosce i prezzi, li conosce solo il contabile.
    c, r = _contabile(), _record(input_tokens=10)
    assert r.cost == 0.0
    c.register(r)
    assert r.cost == pytest.approx(10.0)


def test_record_senza_quantita_costa_zero():
    assert _contabile().register(_record()) == 0.0


def test_record_con_usage_mancante_non_e_prezzabile():
    record = UsageRecord(
        model="modello",
        quantities={},
        measurement_source="missing",
    )

    assert record.is_priceable is False


def test_usage_mancante_non_viene_archiviato_ne_contabilizzato():
    contabile = _contabile()
    record = UsageRecord(
        model="modello",
        quantities={},
        measurement_source="missing",
    )

    with pytest.raises(UnpricedUsage):
        contabile.register(record)

    assert contabile.call_count == 0
    assert contabile.total_cost == 0.0


def test_il_modello_del_record_arriva_al_registro():
    # Verifica che il contabile inoltri il modello giusto, non un valore fisso
    finto = RegistroFinto()
    InMemoryAccountant(finto).register(_record(model="opus-5", input_tokens=10))
    assert finto.chiamate == [("opus-5", "input_tokens", 10)]


# ── Accumulo e totali ─────────────────────────────────────────────────────

def test_totale_su_piu_chiamate():
    c = _contabile()
    c.register(_record(input_tokens=10))    # 10
    c.register(_record(output_tokens=5))    # 10
    assert c.total_cost == pytest.approx(20.0)


def test_conteggio_chiamate():
    c = _contabile()
    assert c.call_count == 0
    c.register(_record(input_tokens=1))
    c.register(_record(input_tokens=1))
    assert c.call_count == 2


def test_contabile_nuovo_parte_da_zero():
    c = _contabile()
    assert c.total_cost == 0.0
    assert c.call_count == 0


def test_i_record_restano_in_ordine():
    c = _contabile()
    c.register(_record(model="primo", input_tokens=1))
    c.register(_record(model="secondo", input_tokens=1))
    assert [r.model for r in c.records] == ["primo", "secondo"]


def test_due_contabili_sono_indipendenti():
    """La lista dei record e' per istanza, non condivisa dalla classe.

    E' la garanzia che rende possibile lo swarm di M4: N worker, N contabili,
    costi attribuibili a ciascuno. Se la lista fosse un attributo di classe le
    spese si mescolerebbero, con un guasto difficilissimo da diagnosticare.
    """
    a, b = _contabile(), _contabile()
    a.register(_record(input_tokens=10))
    assert a.call_count == 1
    assert b.call_count == 0
    assert b.total_cost == 0.0


# ── Propagazione degli errori ─────────────────────────────────────────────

def test_unita_sconosciuta_propaga_l_errore():
    # Il contabile non nasconde l'errore del registro: se un prezzo manca,
    # e' un problema di configurazione e deve emergere.
    with pytest.raises(UnitNotFound):
        _contabile().register(_record(unita_inesistente=10))


def test_il_record_non_viene_archiviato_se_il_calcolo_fallisce():
    c = _contabile()
    with pytest.raises(UnitNotFound):
        c.register(_record(unita_inesistente=10))
    assert c.call_count == 0


# ── Garanzie del contratto astratto ───────────────────────────────────────

def test_il_contratto_non_e_istanziabile():
    with pytest.raises(TypeError):
        Accountant()  # type: ignore[abstract]  <- il rifiuto E' cio' che si verifica


def test_una_sottoclasse_incompleta_e_rifiutata():
    """Chi implementa il contratto a meta' non riesce nemmeno a creare l'oggetto.

    E' la protezione che sposta l'errore dal momento dell'uso a quello della
    costruzione: se un domani si aggiunge un contabile aggregante e ci si
    dimentica un metodo, Python lo segnala subito e dice quale manca.
    """
    class ContabileMonco(Accountant):
        def register(self, record):
            return 0.0
        # total_cost e call_count mancano di proposito

    with pytest.raises(TypeError):
        ContabileMonco()  # type: ignore[abstract]  <- idem: deve fallire


def test_inmemory_rispetta_il_contratto():
    assert isinstance(_contabile(), Accountant)


# ── Integrazione col registro vero ────────────────────────────────────────

def test_col_registro_reale_del_progetto():
    """Contabile e registro combaciano davvero, coi prezzi di `models.toml`.

    350 token input di opus-5 a $5/milione  = $0.00175
    120 token output a $25/milione          = $0.00300
                                              ---------
                                              $0.00475
    """
    c = InMemoryAccountant(ModelRegistry.from_file("models.toml"))
    costo = c.register(UsageRecord(
        model="opus-5",
        quantities={"input_tokens": 350, "output_tokens": 120},
    ))
    assert costo == pytest.approx(0.00475)
    assert c.total_cost == pytest.approx(0.00475)


def test_col_registro_reale_modello_inesistente():
    c = InMemoryAccountant(ModelRegistry.from_file("models.toml"))
    with pytest.raises(ModelNotFound):
        c.register(UsageRecord(model="inesistente", quantities={"input_tokens": 1}))


# ── La scheda di consumo ──────────────────────────────────────────────────

def test_i_default_del_record():
    r = UsageRecord(model="m", quantities={})
    assert r.cost == 0.0
    assert r.attempt == 1
    assert r.n_tool_calls == 0
    assert r.reasoning_tokens == 0
    assert r.label is None
    assert r.finish_reason is None


def test_ogni_record_ha_il_proprio_timestamp():
    """Il timestamp e' calcolato alla creazione, non all'avvio del programma.

    Con `default=` invece di `default_factory=` tutti i record condividerebbero
    l'ora in cui Python ha letto il modulo: un errore che non produce eccezioni,
    solo dati sbagliati, e che renderebbe inutilizzabile la cronologia dei log.
    """
    import time
    a = UsageRecord(model="m", quantities={})
    time.sleep(0.01)
    b = UsageRecord(model="m", quantities={})
    assert a.timestamp != b.timestamp
