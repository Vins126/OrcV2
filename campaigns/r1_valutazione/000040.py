"""Compito 000040 (WebGen-Bench): sito di consulenza con formazione e acquisti.

Testo originale: «Please implement a consulting business website that provides
leadership and business training services. The website should have an
e-commerce component, allowing customers to purchase services directly from the
site. The website should include features such as workshops, online classes,
podcasts, and blogs. Users should be able to browse and purchase services, and
interact with the website. Set all pages to have a light cyan background and
cadet blue components.»

Bozza R1.3 con 12 marcatori, NON ancora approvata (vedi `000040.md`, sezione 6).
Ogni passo riparte da un sito pulito; i passi d'interfaccia non preparano dati via
rotte, quindi nessuno puo' risultare «non valutabile». I casi di prova citati come
C1-C5 sono quelli di `000040.json`, nell'ordine.
"""

import re

from valutazione.libreria import Fallito, passo, rotta

LIGHT_CYAN = "rgb(224, 255, 255)"
CADET_BLUE = "rgb(95, 158, 160)"
SEZIONI = ("home", "services", "workshops", "classes", "podcasts", "blogs", "contact")
CARTA = "4242424242424242"

#: Recapiti: un indirizzo email o un numero di telefono di almeno 7 cifre.
RECAPITO = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+|\+?\d[\d ().-]{6,}\d")

#: Date nei formati comuni: 2026-11-05, 11/05/2026, Nov 5, 5 November.
_MESI = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DATA = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}"
                  rf"|\b{_MESI}\s+\d{{1,2}}\b|\b\d{{1,2}}(st|nd|rd|th)?\s+{_MESI}", re.IGNORECASE)


# ── Funzioni d'appoggio ────────────────────────────────────────────────────

def vai(c, sezione):
    """Clic sul link della barra di navigazione di quella sezione."""
    c.clicca(f"nav-link-{sezione}")
    c.aspetta(0.5)


def sfondo_pagina(c):
    """Sfondo calcolato del primo elemento non trasparente fra html, body e il contenitore principale.

    Il contenitore principale e' `main`, oppure `#root` / `#app` (scelta da approvare: non ha un marcatore).
    """
    return c.pagina.evaluate(
        "() => { const els = [document.documentElement, document.body,"
        " document.querySelector('main, #root, #app')].filter(Boolean);"
        " for (const e of els) { const b = getComputedStyle(e).backgroundColor;"
        " if (b && b !== 'transparent' && b !== 'rgba(0, 0, 0, 0)') return b; }"
        " return ''; }")


def compra_un_servizio(c):
    """Passo 16: dal primo `service-item` al carrello."""
    c.apri()
    vai(c, "services")
    c.clicca("add-to-cart", dentro=c.elemento("service-item"))
    c.aspetta(0.5)
    vai(c, "cart")


def paga(c):
    """Passo 17: numero di carta e conferma."""
    c.scrivi("checkout-card", CARTA)
    c.clicca("checkout-submit")


def vetrina(c):
    """Dati d'esempio per gli screenshot del giudice: un servizio e un workshop nel carrello."""
    catalogo = c.prepara("GET", "/api/catalog").json or []
    for tipo in ("service", "workshop"):
        voce = next((v for v in catalogo if v.get("type") == tipo), None)
        if voce is not None:
            c.prepara("POST", "/api/cart", json={"itemId": voce["id"]})


# ── Passi d'interfaccia ────────────────────────────────────────────────────

@passo("1", origine="C1: «navigation bar ... between Home, Services, Workshops, Online Classes, Podcasts, Blogs, and Contact»")
def p1(c):
    c.apri()
    c.atteso(c.visibile("site-nav"), "site-nav visibile")
    nav = c.elemento("site-nav")
    mancanti = [s for s in SEZIONI if not c.visibile(f"nav-link-{s}", dentro=nav, attesa_ms=1_000)]
    c.atteso(not mancanti, f"dentro site-nav mancano i link {mancanti}")


@passo("2", origine="C1 + C2: «select a service»")
def p2(c):
    c.apri()
    vai(c, "services")
    c.atteso(c.conta("service-item") >= 1, "almeno un service-item visibile")
    c.atteso(c.visibile("add-to-cart", dentro=c.elemento("service-item")), "il primo service-item ha add-to-cart")


@passo("3", origine="C1: sezione Workshops")
def p3(c):
    c.apri()
    vai(c, "workshops")
    c.atteso(c.conta("workshop-item") >= 1, "almeno un workshop-item visibile")


@passo("4", origine="C1: sezione «Online Classes»")
def p4(c):
    c.apri()
    vai(c, "classes")
    c.atteso(c.conta("class-item") >= 1, "almeno un class-item visibile")


@passo("5", origine="C1: sezione «Podcasts»")
def p5(c):
    c.apri()
    vai(c, "podcasts")
    c.atteso(c.conta("podcast-item") >= 1, "almeno un podcast-item visibile")


@passo("6", origine="C1: sezione «Blogs»")
def p6(c):
    c.apri()
    vai(c, "blogs")
    c.atteso(c.conta("blog-post") >= 1, "almeno un blog-post visibile")


@passo("7", origine="C1: sezione «Contact»")
def p7(c):
    c.apri()
    vai(c, "contact")
    testo = c.pagina.inner_text("body", timeout=5_000)
    c.atteso(RECAPITO.search(testo) is not None, "la pagina mostra un'email o un telefono")


@passo("8", origine="C1: ritorno a «Home»")
def p8(c):
    c.apri()
    vai(c, "services")
    vai(c, "home")
    c.atteso(c.visibile("site-nav"), "site-nav ancora visibile dopo il ritorno a Home")


@passo("9", origine="C5: «'light cyan' as the background color»")
def p9(c):
    c.apri()
    sfondo = sfondo_pagina(c)
    c.atteso(sfondo == LIGHT_CYAN, f"sfondo della home light cyan ({sfondo!r})")


@passo("10", origine="C5 + testo: «Set all pages to have a light cyan background» (Workshops)")
def p10(c):
    c.apri()
    vai(c, "workshops")
    sfondo = sfondo_pagina(c)
    c.atteso(sfondo == LIGHT_CYAN, f"sfondo di Workshops light cyan ({sfondo!r})")


@passo("11", origine="C5 + testo: «Set all pages to have a light cyan background» (Blogs)")
def p11(c):
    c.apri()
    vai(c, "blogs")
    sfondo = sfondo_pagina(c)
    c.atteso(sfondo == LIGHT_CYAN, f"sfondo di Blogs light cyan ({sfondo!r})")


@passo("12", origine="C5: «components (such as buttons, cards, headers, etc.) ... 'cadet blue'»")
def p12(c):
    c.apri()
    vai(c, "services")  # l'add-to-cart puo' esistere solo nella pagina dei servizi
    colori = []
    for marcatore in ("site-nav", "add-to-cart"):
        try:
            colori.append(c.stile(marcatore, "background-color"))
        except Exception:
            colori.append("")
    c.atteso(CADET_BLUE in colori, f"site-nav o add-to-cart cadet blue ({colori})")


@passo("13", origine="C4: «including dates, topics, and speakers»")
def p13(c):
    c.apri()
    vai(c, "workshops")
    testi = c.testi("workshop-item")
    c.atteso(bool(testi), "almeno un workshop-item")
    senza = [t[:40] for t in testi if not DATA.search(t)]
    c.atteso(not senza, f"workshop senza data: {senza}")


@passo("14", origine="C4: «ability to register directly from the page»")
def p14(c):
    c.apri()
    vai(c, "workshops")
    c.atteso(c.visibile("workshop-item"), "almeno un workshop-item")
    c.atteso(c.visibile("add-to-cart", dentro=c.elemento("workshop-item")), "il primo workshop-item ha add-to-cart")


@passo("15", origine="C3: «Blog entries should be relevant ...» (la pertinenza la giudica il giudice)")
def p15(c):
    c.apri()
    vai(c, "blogs")
    testi = [t.strip() for t in c.testi("blog-post")]
    c.atteso(len(testi) >= 2, f"almeno 2 blog-post ({len(testi)})")
    corti = [t[:40] for t in testi if len(t) < 80]
    c.atteso(not corti, f"blog-post con meno di 80 caratteri: {corti}")


@passo("16", origine="C2: «select a service, add it to the cart»")
def p16(c):
    compra_un_servizio(c)
    n = c.conta("cart-item")
    c.atteso(n == 1, f"esattamente 1 cart-item ({n})")


@passo("17", origine="C2: «proceed to checkout, enter payment details, and receive a confirmation message»",
       dipende=("16",))
def p17(c):
    compra_un_servizio(c)
    paga(c)
    c.atteso(c.visibile("order-confirmation"), "order-confirmation visibile entro 5 s")


@passo("18", origine="contratto POST /api/orders: carrello svuotato dopo l'ordine", dipende=("17",))
def p18(c):
    compra_un_servizio(c)
    paga(c)
    c.atteso(c.visibile("order-confirmation"), "ordine confermato")
    c.ricarica()
    vai(c, "cart")
    n = c.conta("cart-item")
    c.atteso(n == 0, f"0 cart-item dopo l'ordine ({n})")


# ── Test diretti sulle rotte ───────────────────────────────────────────────

def _catalogo(c):
    r = c.api("GET", "/api/catalog")
    c.atteso(r.status == 200 and isinstance(r.json, list), f"GET /api/catalog 200 con elenco ({r.status})")
    return r.json


def _id_di(c, tipo="service"):
    voce = next((v for v in _catalogo(c) if isinstance(v, dict) and v.get("type") == tipo), None)
    if voce is None:
        raise Fallito(f"nel catalogo non c'e' un {tipo}")
    return voce


def _aggiungi(c, item_id):
    r = c.api("POST", "/api/cart", json={"itemId": item_id})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"POST /api/cart 201 con id ({r.status})")
    return r.json


def _voci(c):
    r = c.api("GET", "/api/cart")
    c.atteso(r.status == 200 and isinstance(r.json, dict) and isinstance(r.json.get("items"), list),
             f"GET /api/cart 200 con items ({r.status})")
    return r.json["items"]


@rotta("T1", origine="contratto: catalogo")
def t1(c):
    catalogo = _catalogo(c)
    tipi = {v.get("type") for v in catalogo if isinstance(v, dict)}
    c.atteso({"service", "workshop"} <= tipi, f"almeno un service e un workshop ({tipi})")
    c.atteso(all(isinstance(v, dict) and {"id", "type", "title", "price"} <= v.keys()
                 and isinstance(v["price"], (int, float)) for v in catalogo), "ogni voce ha id, type, title, price")


@rotta("T2", origine="contratto: crea (POST /api/cart)")
def t2(c):
    voce = _id_di(c)
    v = _aggiungi(c, voce["id"])
    c.atteso(v.get("quantity") == 1 and v.get("itemId") == voce["id"], f"quantity 1 e itemId giusto ({v})")


@rotta("T3", origine="contratto: leggi (GET /api/cart)")
def t3(c):
    v = _aggiungi(c, _id_di(c)["id"])
    c.atteso(any(x.get("id") == v["id"] for x in _voci(c)), "il carrello contiene la voce creata")


@rotta("T4", origine="contratto: modifica (PATCH /api/cart/{id})")
def t4(c):
    v = _aggiungi(c, _id_di(c)["id"])
    r = c.api("PATCH", f"/api/cart/{v['id']}", json={"quantity": 3})
    c.atteso(r.status == 200, f"PATCH 200 ({r.status})")
    riletta = next((x for x in _voci(c) if x.get("id") == v["id"]), {})
    c.atteso(riletta.get("quantity") == 3, f"quantity 3 dopo la rilettura ({riletta})")


@rotta("T5", origine="contratto: cancella (DELETE /api/cart/{id})")
def t5(c):
    v = _aggiungi(c, _id_di(c)["id"])
    c.atteso(c.api("DELETE", f"/api/cart/{v['id']}").status == 204, "DELETE 204")
    c.atteso(all(x.get("id") != v["id"] for x in _voci(c)), "la voce non c'e' piu'")
    c.atteso(c.api("DELETE", f"/api/cart/{v['id']}").status == 404, "secondo DELETE 404")


@rotta("T6", origine="contratto: input sbagliato")
def t6(c):
    c.atteso(c.api("POST", "/api/orders", json={"card": "4242"}).status == 400, "ordine con carrello vuoto: 400")
    c.atteso(c.api("POST", "/api/cart", json={"itemId": "inesistente"}).status == 400, "itemId inesistente: 400")
    c.atteso(c.api("POST", "/api/cart", json={}).status == 400, "corpo vuoto: 400")
    v = _aggiungi(c, _id_di(c)["id"])
    c.atteso(c.api("PATCH", f"/api/cart/{v['id']}", json={"quantity": 0}).status == 400, "quantity 0: 400")
    c.atteso(c.api("POST", "/api/orders", json={"card": ""}).status == 400, "carta vuota: 400")


@rotta("T7", origine="contratto: ordine (POST /api/orders, GET /api/orders/{id})")
def t7(c):
    voce = _id_di(c)
    _aggiungi(c, voce["id"])
    r = c.api("POST", "/api/orders", json={"card": CARTA})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"POST /api/orders 201 ({r.status})")
    ordine = r.json
    c.atteso([(x.get("itemId"), x.get("quantity")) for x in ordine.get("items") or []] == [(voce["id"], 1)],
             f"l'ordine contiene la voce ({ordine.get('items')})")
    c.atteso(ordine.get("total") == voce["price"], f"total = prezzo x quantita' ({ordine.get('total')})")
    letto = c.api("GET", f"/api/orders/{ordine['id']}")
    c.atteso(letto.status == 200 and (letto.json or {}).get("id") == ordine["id"], f"GET ordine 200 ({letto.status})")
    c.atteso(_voci(c) == [], "carrello vuoto dopo l'ordine")


@rotta("T8", origine="contratto: persistenza dopo il riavvio")
def t8(c):
    voce = _id_di(c)
    _aggiungi(c, voce["id"])
    ordine = c.api("POST", "/api/orders", json={"card": CARTA}).json or {}
    c.atteso("id" in ordine, "ordine creato")
    v = _aggiungi(c, voce["id"])
    c.riavvia_server()
    c.atteso(any(x.get("id") == v["id"] for x in _voci(c)), "la voce del carrello resta dopo il riavvio")
    c.atteso(c.api("GET", f"/api/orders/{ordine['id']}").status == 200, "l'ordine resta dopo il riavvio")


@rotta("T9", origine="contratto: id inesistente")
def t9(c):
    c.atteso(c.api("GET", "/api/orders/inesistente").status == 404, "GET ordine inesistente: 404")
    c.atteso(c.api("PATCH", "/api/cart/inesistente", json={"quantity": 1}).status == 404, "PATCH inesistente: 404")
