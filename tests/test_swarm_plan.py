"""Il piano dello sciame (R3.1): lettura, validazione e ondate.

Nota di design (tesi):
    Il piano lo scrive Opus, quindi va trattato come un dato non fidato: ogni
    regola che l'orchestratore da' per vera (niente cicli, file disgiunti, ogni
    rotta del contratto con un responsabile, worker ammesso) si controlla qui,
    prima di spendere un dollaro sui worker. Nessun test chiama un modello.
"""

import json
from pathlib import Path

import pytest

from swarm_plan import Piece, Plan, PlanError, contract_routes, parse_plan, waves

WORKERS = ("worker", "worker_cheap")

PROMPT_CON_CONTRATTO = """Build a booking site.

## Routes contract

Prefix `/api`, JSON bodies.

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| GET | `/api/cars` | - | 200 | - |
| GET | `/api/cars/:id/availability?start=…&end=…` | - | 200 | 404 |
| post | `/api/bookings` | `{car_id}` | 201 | 400 |

## data-testid markers

| Marker | Element |
|---|---|
| `car-card` | one card per car |
"""


def _pezzo(id_, files, depends_on=(), routes=(), worker="worker_cheap"):
    return {"id": id_, "files": list(files), "depends_on": list(depends_on),
            "description": f"pezzo {id_}", "routes": list(routes), "worker": worker}


def _piano(*pezzi, style=":root { --accent: #c33; }"):
    return json.dumps({"style": style, "pieces": list(pezzi)})


def _valido():
    return _piano(
        _pezzo("skeleton", ["start.sh", "package.json", "server.js", "public/style.css"]),
        _pezzo("cars", ["routes/cars.js"], ["skeleton"], ["GET /api/cars", "GET /api/cars/:id/availability"]),
        _pezzo("bookings", ["routes/bookings.js"], ["skeleton"], ["POST /api/bookings"], worker="worker"),
        _pezzo("page", ["public/index.html", "public/app.js"], ["cars", "bookings"]),
    )


ROTTE = ("GET /api/cars", "GET /api/cars/:id/availability", "POST /api/bookings")


# ── Rotte del contratto ───────────────────────────────────────────────────

def test_p1_le_rotte_si_leggono_dalla_tabella_del_contratto_normalizzate():
    """Metodo in maiuscolo, senza backtick e senza la parte dopo `?`."""
    assert contract_routes(PROMPT_CON_CONTRATTO) == ROTTE


def test_p2_un_compito_senza_contratto_non_ha_rotte():
    assert contract_routes("Build a static page.\n\n## data-testid markers\n\n| `x` | y |\n") == ()


def test_p3_le_rotte_dei_cinque_compiti_veri_si_leggono():
    """Quattro compiti hanno un contratto, `842` e' un sito senza server."""
    cartella = Path("campaigns/r1_prompt")
    for compito in ("000040", "000058", "000098", "684"):
        rotte = contract_routes((cartella / f"{compito}.md").read_text())
        assert len(rotte) >= 4, compito
        assert all(r.split(" ", 1)[0] in {"GET", "POST", "PUT", "PATCH", "DELETE"} for r in rotte), compito
    assert contract_routes((cartella / "842.md").read_text()) == ()


# ── Piano valido ──────────────────────────────────────────────────────────

def test_p4_un_piano_valido_diventa_un_plan():
    piano = parse_plan(_valido(), routes=ROTTE, workers=WORKERS)

    assert isinstance(piano, Plan)
    assert piano.style == ":root { --accent: #c33; }"
    assert [p.id for p in piano.pieces] == ["skeleton", "cars", "bookings", "page"]
    bookings = piano.pieces[2]
    assert isinstance(bookings, Piece)
    assert bookings.files == ("routes/bookings.js",)
    assert bookings.depends_on == ("skeleton",)
    assert bookings.routes == ("POST /api/bookings",)
    assert bookings.worker == "worker"
    assert bookings.description == "pezzo bookings"


@pytest.mark.parametrize("contorno", [
    "Ecco il piano:\n```json\n{}\n```\nFine.",
    "```\n{}\n```",
    "Piano: {} -- fine",
])
def test_p5_il_json_si_trova_anche_dentro_un_blocco_o_con_testo_intorno(contorno):
    testo = contorno.replace("{}", _valido())
    assert len(parse_plan(testo, routes=ROTTE, workers=WORKERS).pieces) == 4


def test_p6_le_rotte_del_piano_si_confrontano_normalizzate():
    """Opus puo' scrivere `get /api/cars?x=1`: e' la stessa rotta."""
    testo = _piano(_pezzo("s", ["start.sh"], routes=["get /api/cars?x=1", "GET /api/cars/:id/availability",
                                                     "POST /api/bookings"]))
    assert parse_plan(testo, routes=ROTTE, workers=WORKERS).pieces[0].routes == ROTTE


def test_p7_senza_contratto_un_piano_senza_rotte_e_valido():
    testo = _piano(_pezzo("s", ["start.sh", "index.html"]))
    assert parse_plan(testo, routes=(), workers=WORKERS).pieces[0].routes == ()


# ── Piano invalido: ogni regola ha il suo messaggio ───────────────────────

def _errore(testo, routes=ROTTE):
    with pytest.raises(PlanError) as info:
        parse_plan(testo, routes=routes, workers=WORKERS)
    return str(info.value)


def test_p8_testo_senza_json_e_un_errore():
    assert "JSON" in _errore("Non ho un piano.")


def test_p9_json_malformato_e_un_errore():
    assert "JSON" in _errore('{"style": "x", "pieces": [}')


@pytest.mark.parametrize("documento", [
    {"pieces": []},
    {"style": "x"},
    {"style": "x", "pieces": []},
    {"style": 3, "pieces": [_pezzo("s", ["a"])]},
    {"style": "x", "pieces": [{"id": "s", "files": ["a"]}]},
    {"style": "x", "pieces": [{**_pezzo("s", ["a"]), "files": []}]},
    {"style": "x", "pieces": [{**_pezzo("s", ["a"]), "files": "a"}]},
    {"style": "x", "pieces": [{**_pezzo("s", ["a"]), "id": ""}]},
])
def test_p10_campi_mancanti_vuoti_o_del_tipo_sbagliato_sono_un_errore(documento):
    _errore(json.dumps(documento), routes=())


def test_p11_due_pezzi_con_lo_stesso_id_sono_un_errore():
    assert "s" in _errore(_piano(_pezzo("s", ["a"]), _pezzo("s", ["b"])), routes=())


def test_p12_un_ciclo_e_un_errore():
    testo = _piano(_pezzo("a", ["a.js"], ["c"]), _pezzo("b", ["b.js"], ["a"]), _pezzo("c", ["c.js"], ["b"]))
    assert "ciclo" in _errore(testo, routes=())


def test_p13_un_pezzo_che_dipende_da_se_stesso_e_un_ciclo():
    assert "ciclo" in _errore(_piano(_pezzo("a", ["a.js"], ["a"])), routes=())


def test_p14_una_dipendenza_inesistente_e_un_errore():
    assert "fantasma" in _errore(_piano(_pezzo("a", ["a.js"], ["fantasma"])), routes=())


@pytest.mark.parametrize("secondo", ["server.js", "./server.js", "lib/../server.js"])
def test_p15_lo_stesso_file_in_due_pezzi_e_un_errore(secondo):
    """Il confronto avviene sul percorso normalizzato: `./server.js` e' `server.js`."""
    testo = _piano(_pezzo("a", ["server.js"]), _pezzo("b", [secondo]))
    assert "server.js" in _errore(testo, routes=())


@pytest.mark.parametrize("percorso", ["/etc/passwd", "../fuori.js", "a/../../fuori.js", ""])
def test_p16_un_file_fuori_dal_workspace_e_un_errore(percorso):
    _errore(_piano(_pezzo("a", [percorso])), routes=())


def test_p17_una_rotta_del_contratto_senza_responsabile_e_un_errore():
    testo = _piano(_pezzo("s", ["start.sh"], routes=["GET /api/cars", "GET /api/cars/:id/availability"]))
    assert "POST /api/bookings" in _errore(testo)


def test_p18_una_rotta_con_due_responsabili_e_un_errore():
    testo = _piano(_pezzo("a", ["a.js"], routes=list(ROTTE)), _pezzo("b", ["b.js"], routes=["GET /api/cars"]))
    assert "GET /api/cars" in _errore(testo)


def test_p19_una_rotta_fuori_dal_contratto_e_ammessa():
    """Un'API in piu' non viola il contratto; conta solo che le sue rotte ci siano tutte."""
    testo = _piano(_pezzo("s", ["start.sh"], routes=[*ROTTE, "GET /api/health"]))
    assert len(parse_plan(testo, routes=ROTTE, workers=WORKERS).pieces) == 1


@pytest.mark.parametrize("worker", ["planner", "opus-5-5", "", None])
def test_p20_un_worker_non_ammesso_e_un_errore(worker):
    """Opus sceglie fra i worker ammessi, non puo' assegnare un pezzo a se stesso."""
    assert "worker" in _errore(_piano(_pezzo("s", ["a"], worker=worker)), routes=())


# ── Ondate ────────────────────────────────────────────────────────────────

def test_p21_le_ondate_seguono_le_dipendenze_e_l_ordine_del_piano():
    piano = parse_plan(_valido(), routes=ROTTE, workers=WORKERS)

    assert [[p.id for p in onda] for onda in waves(piano)] == [["skeleton"], ["cars", "bookings"], ["page"]]


def test_p22_pezzi_indipendenti_stanno_tutti_nella_prima_ondata():
    piano = parse_plan(_piano(_pezzo("a", ["a"]), _pezzo("b", ["b"]), _pezzo("c", ["c"])),
                       routes=(), workers=WORKERS)
    assert [[p.id for p in onda] for onda in waves(piano)] == [["a", "b", "c"]]


def test_p23_un_pezzo_va_nell_ondata_dopo_la_sua_dipendenza_piu_lontana():
    piano = parse_plan(_piano(_pezzo("a", ["a"]), _pezzo("b", ["b"], ["a"]), _pezzo("c", ["c"], ["a", "b"]),
                              _pezzo("d", ["d"], ["a"])), routes=(), workers=WORKERS)
    assert [[p.id for p in onda] for onda in waves(piano)] == [["a"], ["b", "d"], ["c"]]
