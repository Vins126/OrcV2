"""Script d'esempio per le prove reali dell'interprete (sito `sito_items`)."""

from valutazione.libreria import passo, rotta


@passo("1", origine="esempio: si aggiunge una voce dall'interfaccia")
def aggiungi(c):
    c.apri()
    c.scrivi("item-input", "pane")
    c.clicca("item-add")
    c.atteso(c.visibile("item", testo="pane"), "la voce 'pane' compare nell'elenco")


@passo("2", origine="esempio: le voci preparate via rotte si vedono")
def elenco(c):
    c.prepara("POST", "/api/items", json={"name": "latte"})
    c.apri()
    c.atteso(c.conta("item") == 1, "una sola voce: lo stato riparte pulito a ogni passo")


@passo("3", origine="esempio: la voce resta dopo il riavvio del server", dipende=("1",))
def persistenza(c):
    c.prepara("POST", "/api/items", json={"name": "uova"})
    c.riavvia_server()
    c.apri()
    c.atteso(c.visibile("item", testo="uova"), "la voce resta dopo il riavvio")


@rotta("R1", origine="esempio: input sbagliato rifiutato")
def sbagliato(c):
    c.atteso(c.api("POST", "/api/items", json={}).status == 400, "400 senza nome")


@rotta("R2", origine="esempio: crea e leggi")
def crea(c):
    r = c.api("POST", "/api/items", json={"name": "sale"})
    c.atteso(r.status == 201, "201 alla creazione")
    c.atteso([v["name"] for v in c.api("GET", "/api/items").json] == ["sale"], "la voce si rilegge")


def vetrina(c):
    """Dati d'esempio per gli screenshot."""
    for nome in ("pane", "latte", "uova"):
        c.prepara("POST", "/api/items", json={"name": nome})
