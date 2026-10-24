"""Compito 000098 (WebGen-Bench): piattaforma di noleggio auto.

Testo originale: «Please implement a comprehensive car rental platform for booking
car rental services. [...] Users should be able to browse different types of
cars, select rental dates and times, book selected cars, and view booking
records. The platform should support multiple payment methods and provide order
management functionality. Set the background to papaya whip, and apply dark
orange to components.»

Approvato dall'autore il 23 ott 2026 (bozza con 12 marcatori). Ogni passo
riparte da un sito pulito; i dati preparati via rotte, se la rotta fallisce,
rendono il passo «non valutabile» (PROTOCOLLO §6). Annullamento e modifica
delle prenotazioni sono provati solo sulle rotte (scelta approvata).
"""

import re
import urllib.parse
from datetime import date, timedelta

from valutazione.libreria import passo, rotta

#: Colori richiesti dal testo: papaya whip (#FFEFD5) e dark orange (#FF8C00).
PAPAYA = "rgb(255, 239, 213)"
ARANCIO = "rgb(255, 140, 0)"


# ── Funzioni d'appoggio ────────────────────────────────────────────────────

def giorno(n: int) -> str:
    """«D+n»: oggi piu' n giorni, alle 10:00, nel formato di `datetime-local` e delle rotte."""
    return (date.today() + timedelta(days=n)).isoformat() + "T10:00"


def numeri(testo: str) -> list[float]:
    """Tutti i numeri di un testo; accetta `1.234,50`, `1,234.50`, `90,00`, `90.00`, `90`."""
    trovati = []
    for grezzo in re.findall(r"\d[\d.,]*", testo):
        t = grezzo.rstrip(".,")
        if "," in t and "." in t:
            # il separatore che compare per ultimo e' quello dei decimali
            t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
        elif "," in t:
            t = t.replace(",", ".") if re.search(r",\d{1,2}$", t) and t.count(",") == 1 else t.replace(",", "")
        elif t.count(".") > 1 or re.search(r"\.\d{3}$", t):
            t = t.replace(".", "")
        try:
            trovati.append(float(t))
        except ValueError:
            pass
    return trovati


def ha_giorno(testo: str, iso: str) -> bool:
    """Il giorno del mese della data compare nel testo come numero a se' (es. `7` o `07`)."""
    g = int(iso[8:10])
    return re.search(rf"(?<!\d)0?{g}(?!\d)", testo) is not None


def auto_della_card(c, cars: list[dict], n: int) -> dict:
    """L'auto di `/api/cars` il cui `name` compare nel testo della card n (il nome piu' lungo, se piu' d'uno)."""
    testo = c.testo("car-card", n=n)
    candidate = [a for a in cars if str(a.get("name", "")) and str(a["name"]) in testo]
    c.atteso(bool(candidate), f"la card {n} contiene il nome di un'auto di /api/cars")
    return max(candidate, key=lambda a: len(str(a["name"])))


def leggi_auto(c) -> list[dict]:
    """Il catalogo letto dalla rotta (lettura, non preparazione: se manca il passo fallisce)."""
    cars = c.api("GET", "/api/cars").json
    c.atteso(isinstance(cars, list) and len(cars) >= 2, "GET /api/cars da' almeno 2 auto")
    return cars


def scegli(c, n: int, inizio: str, fine: str) -> None:
    """Clicca la card n e compila inizio e fine noleggio."""
    c.clicca("car-card", n=n)
    c.scrivi("date-start", inizio)
    c.scrivi("date-end", fine)


def testo_stabile(c, marcatore: str) -> str:
    """Testo del marcatore dopo che ha smesso di cambiare (due letture uguali a 0,5 s), max ~5 s."""
    c.aspetta(0.5)
    prima = c.testo(marcatore).strip()
    for _ in range(9):
        c.aspetta(0.5)
        ora = c.testo(marcatore).strip()
        if ora == prima:
            return ora
        prima = ora
    return prima


def al_riepilogo(c, inizio: str, fine: str) -> None:
    """Prima card, date scelte, clic su `book-car`; il riepilogo deve comparire."""
    c.apri()
    scegli(c, 0, inizio, fine)
    c.aspetta(0.5)
    c.clicca("book-car")
    c.atteso(c.visibile("booking-summary"), "booking-summary visibile dopo book-car")


def paga(c, inizio: str, fine: str) -> str:
    """Prenota dall'interfaccia con il secondo metodo di pagamento; restituisce il testo di `booking-reference`."""
    al_riepilogo(c, inizio, fine)
    c.atteso(c.conta("payment-option") >= 2, "almeno 2 payment-option")
    c.clicca("payment-option", n=1)
    c.clicca("confirm-payment")
    c.atteso(c.visibile("booking-reference"), "booking-reference visibile")
    codice = c.testo("booking-reference").strip()
    c.atteso(codice != "", "booking-reference non vuoto")
    return codice


def prenota_via_rotte(c, auto: dict, inizio: str, fine: str, metodo: str) -> dict:
    r = c.prepara("POST", "/api/bookings", json={"car_id": auto["id"], "start_date": inizio,
                                                  "end_date": fine, "payment_method": metodo})
    return r.json or {}


def vetrina(c):
    """Dati d'esempio per gli screenshot del giudice: il catalogo del sito piu' 2 prenotazioni via rotte."""
    cars = c.prepara("GET", "/api/cars").json
    metodi = c.prepara("GET", "/api/payment-methods").json
    prenota_via_rotte(c, cars[0], giorno(5), giorno(8), metodi[0])
    prenota_via_rotte(c, cars[1], giorno(10), giorno(12), metodi[1])


# ── Passi d'interfaccia ────────────────────────────────────────────────────

@passo("S1", origine="TC1: «Browse the available cars for rental.»")
def s1(c):
    c.apri()
    c.atteso(c.conta("car-card") >= 2, "almeno 2 car-card visibili")


@passo("S2", origine="TC1: «details (e.g., type, price per day), is displayed»")
def s2(c):
    c.apri()
    testi = c.testi("car-card")
    c.atteso(len(testi) >= 2, "almeno 2 car-card")
    c.atteso(all(re.search(r"\d", t) for t in testi), "ogni card contiene un numero (prezzo)")
    cars = leggi_auto(c)
    mancanti = [a.get("name") for a in cars if not any(str(a.get("name")) in t for t in testi)]
    c.atteso(not mancanti, f"ogni auto di /api/cars compare in una card (mancano {mancanti})")
    c.atteso(len(set(testi)) > 1, "i testi delle card non sono tutti uguali")


@passo("S3", origine="TC2: «highlights whether the selected car is available»")
def s3(c):
    c.apri()
    scegli(c, 0, giorno(30), giorno(32))
    c.atteso(c.visibile("availability-status"), "availability-status visibile")
    c.atteso(testo_stabile(c, "availability-status") != "", "availability-status ha un testo")


@passo("S4", origine="TC2: «whether the selected car is available for the chosen dates»")
def s4(c):
    cars = c.prepara("GET", "/api/cars").json or []
    metodi = c.prepara("GET", "/api/payment-methods").json or []
    c.apri()
    auto = auto_della_card(c, cars, 1)
    prenota_via_rotte(c, auto, giorno(40), giorno(42), metodi[0])
    c.ricarica()
    scegli(c, 1, giorno(50), giorno(52))
    libero = testo_stabile(c, "availability-status")
    c.scrivi("date-start", giorno(40))
    c.scrivi("date-end", giorno(42))
    occupato = testo_stabile(c, "availability-status")
    c.atteso(libero != "" and occupato != "", "availability-status ha un testo in entrambi i casi")
    c.atteso(libero != occupato, f"il testo cambia fra date libere e occupate ({libero!r})")


@passo("S5", origine="TC3: «booking summary (car type, rental dates, total cost) is accurately displayed»")
def s5(c):
    c.apri()
    cars = leggi_auto(c)
    auto = auto_della_card(c, cars, 0)
    al_riepilogo(c, giorno(60), giorno(62))
    testo = c.testo("booking-summary")
    c.atteso(str(auto["name"]) in testo, "il riepilogo contiene il nome dell'auto")
    c.atteso(ha_giorno(testo, giorno(60)) and ha_giorno(testo, giorno(62)),
             "il riepilogo contiene il giorno del mese di inizio e di fine")
    p = float(auto["price_per_day"])
    c.atteso(any(abs(x - k * p) < 0.005 for x in numeri(testo) for k in (2, 3)),
             f"il riepilogo contiene un totale pari a 2p o 3p (p = {p:g})")


@passo("S6", origine="TC3: «with options to proceed to payment or edit details»")
def s6(c):
    al_riepilogo(c, giorno(60), giorno(62))
    c.clicca("edit-booking")
    c.atteso(c.visibile("date-start"), "date-start visibile dopo edit-booking")
    c.atteso(c.elemento("date-start").is_editable(), "date-start modificabile")


@passo("S7", origine="TC3: «options to proceed to payment»; testo: «support multiple payment methods»")
def s7(c):
    al_riepilogo(c, giorno(60), giorno(62))
    c.atteso(c.conta("payment-option") >= 2, "almeno 2 payment-option visibili")


@passo("S8", origine="TC4: «booking confirmation screen is shown with a unique booking reference»")
def s8(c):
    c.apri()
    auto = auto_della_card(c, leggi_auto(c), 0)
    codice = paga(c, giorno(70), giorno(72))
    elenco = c.api("GET", "/api/bookings").json or []
    trovate = [b for b in elenco if isinstance(b, dict) and str(b.get("reference") or "") != ""
               and str(b["reference"]) in codice]
    c.atteso(bool(trovate), "GET /api/bookings ha una prenotazione il cui reference compare a schermo")
    b = trovate[0]
    c.atteso(str(b.get("car_id")) == str(auto["id"]), "la prenotazione e' sull'auto scelta")
    c.atteso(str(b.get("start_date", ""))[:10] == giorno(70)[:10]
             and str(b.get("end_date", ""))[:10] == giorno(72)[:10], "la prenotazione ha le date scelte")


@passo("S9", origine="TC4: «unique booking reference»")
def s9(c):
    primo = paga(c, giorno(70), giorno(72))
    secondo = paga(c, giorno(80), giorno(82))
    c.atteso(primo != secondo, f"due prenotazioni hanno codici diversi ({primo!r})")


@passo("S10", origine="testo: «view booking records» e «provide order management functionality»")
def s10(c):
    cars = c.prepara("GET", "/api/cars").json or []
    metodi = c.prepara("GET", "/api/payment-methods").json or []
    b = prenota_via_rotte(c, cars[0], giorno(90), giorno(92), metodi[0])
    codice = str(b.get("reference") or "")
    c.apri()
    c.clicca("nav-bookings")
    c.atteso(c.visibile("booking-row"), "booking-row visibile")
    c.atteso(codice != "" and any(codice in t and str(cars[0]["name"]) in t for t in c.testi("booking-row")),
             "una booking-row contiene il codice e il nome dell'auto")


@passo("S11", origine="TC5: «background color of 'papaya whip'»")
def s11(c):
    c.apri()
    fondo = c.pagina.evaluate(
        "() => { const b = getComputedStyle(document.body).backgroundColor;"
        " return (b === 'rgba(0, 0, 0, 0)' || b === 'transparent')"
        " ? getComputedStyle(document.documentElement).backgroundColor : b; }")
    c.atteso(fondo == PAPAYA, f"sfondo di body (o html) = {PAPAYA} (trovato {fondo})")


def arancione(c, marcatore: str) -> bool:
    try:
        return any(ARANCIO in c.stile(marcatore, p) for p in ("background-color", "border-color", "color"))
    except Exception:
        return False


@passo("S12", origine="TC5: «components (such as buttons, cards, headers, etc.) are styled with the color 'dark orange'»")
def s12(c):
    c.apri()
    scegli(c, 0, giorno(30), giorno(32))
    c.aspetta(1)
    colorati = [m for m in ("car-card", "book-car", "nav-bookings") if arancione(c, m)]
    c.atteso(len(colorati) >= 2, f"almeno 2 fra car-card, book-car, nav-bookings in {ARANCIO} (solo {colorati})")


# ── Test diretti sulle rotte ───────────────────────────────────────────────

def _base(c):
    """Prima auto e metodi di pagamento: se le rotte di lettura non vanno, il test fallisce."""
    cars = c.api("GET", "/api/cars").json
    metodi = c.api("GET", "/api/payment-methods").json
    c.atteso(isinstance(cars, list) and len(cars) >= 2, "GET /api/cars: almeno 2 auto")
    c.atteso(isinstance(metodi, list) and len(metodi) >= 2, "GET /api/payment-methods: almeno 2 metodi")
    return cars[0], metodi


def _crea(c, auto, metodo, inizio=100, fine=102):
    r = c.api("POST", "/api/bookings", json={"car_id": auto["id"], "start_date": giorno(inizio),
                                             "end_date": giorno(fine), "payment_method": metodo})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"POST 201 con id ({r.status})")
    return r.json


def _disponibile(c, auto, inizio, fine):
    q = urllib.parse.urlencode({"start": giorno(inizio), "end": giorno(fine)})
    r = c.api("GET", f"/api/cars/{auto['id']}/availability?{q}")
    c.atteso(r.status == 200 and isinstance(r.json, dict) and isinstance(r.json.get("available"), bool),
             f"availability 200 con available booleano ({r.status})")
    return r.json["available"]


@rotta("R1", origine="contratto: crea")
def r1(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    p = float(auto["price_per_day"])
    c.atteso(str(b.get("reference") or "") != "", "reference non vuoto")
    c.atteso(b.get("status") == "confirmed", "status = confirmed")
    c.atteso(isinstance(b.get("total_price"), (int, float))
             and any(abs(b["total_price"] - k * p) < 0.005 for k in (2, 3)), "total_price = 2p o 3p")


@rotta("R2", origine="contratto: leggi")
def r2(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    uno = c.api("GET", f"/api/bookings/{b['id']}")
    c.atteso(uno.status == 200 and (uno.json or {}).get("reference") == b.get("reference"), "lettura del singolo")
    elenco = c.api("GET", "/api/bookings")
    c.atteso(elenco.status == 200 and any(x.get("id") == b["id"] for x in elenco.json or []), "presente nell'elenco")


@rotta("R3", origine="contratto: disponibilita'")
def r3(c):
    auto, metodi = _base(c)
    _crea(c, auto, metodi[0])
    c.atteso(_disponibile(c, auto, 101, 103) is False, "non disponibile su date sovrapposte")
    c.atteso(_disponibile(c, auto, 110, 112) is True, "disponibile su date libere")


@rotta("R4", origine="contratto: modifica")
def r4(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    r = c.api("PATCH", f"/api/bookings/{b['id']}", json={"end_date": giorno(104)})
    c.atteso(r.status == 200, f"PATCH 200 ({r.status})")
    nuova = c.api("GET", f"/api/bookings/{b['id']}").json or {}
    c.atteso(str(nuova.get("end_date", ""))[:10] == giorno(104)[:10], "end_date aggiornata")
    c.atteso(isinstance(nuova.get("total_price"), (int, float)) and nuova["total_price"] > b["total_price"],
             "total_price aumentato")


@rotta("R5", origine="contratto: annulla (status cancelled)")
def r5(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    r = c.api("PATCH", f"/api/bookings/{b['id']}", json={"status": "cancelled"})
    c.atteso(r.status == 200 and (r.json or {}).get("status") == "cancelled", f"PATCH 200 cancelled ({r.status})")
    c.atteso(_disponibile(c, auto, 101, 103) is True, "dopo l'annullamento l'auto e' disponibile")


@rotta("R6", origine="contratto: cancella")
def r6(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    c.atteso(c.api("DELETE", f"/api/bookings/{b['id']}").status == 204, "DELETE 204")
    c.atteso(c.api("GET", f"/api/bookings/{b['id']}").status == 404, "poi 404")


@rotta("R7", origine="contratto: input sbagliato")
def r7(c):
    auto, metodi = _base(c)
    corpi = [
        {"start_date": giorno(100), "end_date": giorno(102), "payment_method": metodi[0]},
        {"car_id": auto["id"], "start_date": giorno(102), "end_date": giorno(100), "payment_method": metodi[0]},
        {"car_id": auto["id"], "start_date": giorno(100), "end_date": giorno(102), "payment_method": "bitcoin-xyz"},
    ]
    for corpo in corpi:
        r = c.api("POST", "/api/bookings", json=corpo)
        c.atteso(r.status == 400, f"400 per {corpo} ({r.status})")


@rotta("R8", origine="contratto: conflitto sulle date")
def r8(c):
    auto, metodi = _base(c)
    _crea(c, auto, metodi[0])
    r = c.api("POST", "/api/bookings", json={"car_id": auto["id"], "start_date": giorno(101),
                                             "end_date": giorno(103), "payment_method": metodi[0]})
    c.atteso(r.status == 409, f"seconda prenotazione sovrapposta: 409 ({r.status})")


@rotta("R9", origine="contratto: persistenza dopo il riavvio")
def r9(c):
    auto, metodi = _base(c)
    b = _crea(c, auto, metodi[0])
    c.riavvia_server()
    r = c.api("GET", f"/api/bookings/{b['id']}")
    c.atteso(r.status == 200 and r.json == b, "stessa prenotazione dopo il riavvio")

