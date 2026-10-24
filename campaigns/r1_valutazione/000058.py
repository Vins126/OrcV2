"""Compito 000058 (WebGen-Bench): coaching uno a uno fra coach e utenti.

Testo originale (estratto): «Users should be able to complete a personality
assessment, create and manage their profiles, search for and select suitable
coaches, schedule coaching sessions, and set and track goals. Set the
background to beige, and apply saddle brown to components.»

Bozza R1.3 con 12 marcatori, NON ancora approvata: le scelte fatte applicandola
sono elencate in fondo a `000058.md`. Ogni passo riparte da un sito pulito; i
dati preparati via rotte, se la rotta fallisce, rendono il passo «non
valutabile» (PROTOCOLLO §6). Tutti i marcatori stanno nella pagina `/`.
"""

import time
from urllib.parse import quote

from valutazione.libreria import NonValutabile, passo, rotta

BEIGE = "rgb(245, 245, 220)"
SADDLE_BROWN = "rgb(139, 69, 19)"
TRASPARENTE = ("rgba(0, 0, 0, 0)", "transparent")
PULSANTI = ("assessment-submit", "profile-save", "session-submit", "goal-add")


# ── Funzioni d'appoggio ────────────────────────────────────────────────────

def finche(condizione, secondi=5.0):
    """Riprova `condizione` fino a `secondi`; True appena e' vera.

    Serve perche' il sito salva e ridisegna in modo asincrono: un controllo
    secco subito dopo il clic premierebbe o punirebbe a caso.
    """
    scadenza = time.monotonic() + secondi
    while True:
        try:
            if condizione():
                return True
        except Exception:
            pass
        if time.monotonic() >= scadenza:
            return False
        time.sleep(0.25)


def elenco(c, percorso):
    """Il JSON di una GET se e' una lista, altrimenti lista vuota."""
    dati = c.api("GET", percorso).json
    return dati if isinstance(dati, list) else []


def profilo(c):
    dati = c.api("GET", "/api/profile").json
    return dati if isinstance(dati, dict) else {}


def completa_test(c):
    """Clicca la prima opzione di ogni domanda, poi invia; torna il testo del risultato."""
    opzioni = c.elementi("assessment-option")
    c.atteso(c.visibile("assessment-option"), "almeno un assessment-option visibile")
    for i in range(opzioni.count()):
        opzioni.nth(i).click(timeout=5_000)
    c.clicca("assessment-submit")
    letto = {"testo": ""}

    def pieno():
        letto["testo"] = c.testo("assessment-result").strip()
        return bool(letto["testo"]) and c.elemento("assessment-result").is_visible()
    c.atteso(finche(pieno), "assessment-result visibile con testo non vuoto")
    return letto["testo"]


def colore_di(c, marcatore):
    """I colori calcolati (sfondo, testo, bordi) del primo elemento visibile con quel marcatore."""
    if not c.visibile(marcatore, attesa_ms=1_000):
        return set()
    return set(c.elemento(marcatore).evaluate(
        "e => { const s = getComputedStyle(e); return [s.backgroundColor, s.color, s.borderTopColor,"
        " s.borderRightColor, s.borderBottomColor, s.borderLeftColor]; }", timeout=5_000))


def vetrina(c):
    """Dati d'esempio per gli screenshot del giudice (regola della vetrina, PROTOCOLLO §6):
    profilo con nome e test fatto, una sessione, un obiettivo al 40%."""
    c.prepara("PUT", "/api/profile", json={"name": "Giulia Test 58", "bio": "Voglio crescere come manager",
                                           "preferences": "leadership, sessioni serali"})
    c.prepara("POST", "/api/assessment", json={"answers": [0, 1, 0]})
    coach = c.prepara("GET", "/api/coaches").json or []
    if coach:
        c.prepara("POST", "/api/sessions", json={"coachId": coach[0]["id"], "datetime": "2026-12-01T10:00"})
    c.prepara("POST", "/api/goals", json={"title": "Correre 5 km", "progress": 40})


# ── Passi d'interfaccia ────────────────────────────────────────────────────

@passo("1", origine="caso 6: «uses 'beige' as the background color»")
def p1(c):
    c.apri()
    c.atteso(c.visibile("assessment-submit"), "assessment-submit presente (un sito vuoto non conta)")
    sfondo = c.pagina.evaluate(
        "() => { const b = getComputedStyle(document.body).backgroundColor;"
        " return (b === 'rgba(0, 0, 0, 0)' || b === 'transparent')"
        " ? getComputedStyle(document.documentElement).backgroundColor : b; }")
    c.atteso(sfondo == BEIGE, f"sfondo della pagina beige ({sfondo})")


@passo("2", origine="caso 6: «components (such as buttons, cards, headers, etc.) ... 'saddle brown'»")
def p2(c):
    c.apri()
    marroni = [m for m in PULSANTI if SADDLE_BROWN in colore_di(c, m)]
    c.atteso(len(marroni) >= 2, f"almeno 2 dei 4 pulsanti in saddle brown (lo sono: {marroni})")


@passo("3", origine="caso 1: «display an assessment summary or results»")
def p3(c):
    c.apri()
    completa_test(c)


@passo("4", origine="caso 1: «these results should be saved to the user's profile»", dipende=("3",))
def p4(c):
    c.apri()
    risultato = completa_test(c)
    c.atteso(finche(lambda: bool(str(profilo(c).get("assessmentResult") or "").strip())),
             "GET /api/profile ha assessmentResult non vuoto")
    c.ricarica()
    c.atteso(finche(lambda: c.testo("assessment-result").strip() == risultato),
             "dopo la ricarica assessment-result mostra lo stesso risultato")


@passo("5", origine="caso 2: «Updated profile details should be saved correctly and displayed»")
def p5(c):
    c.apri()
    c.scrivi("profile-name", "Giulia Test 58")
    c.clicca("profile-save")
    c.atteso(finche(lambda: profilo(c).get("name") == "Giulia Test 58"),
             "GET /api/profile ha name = Giulia Test 58")
    c.ricarica()
    c.atteso(finche(lambda: c.elemento("profile-name").input_value(timeout=1_000) == "Giulia Test 58"),
             "dopo la ricarica profile-name vale Giulia Test 58")


@passo("6", origine="caso 3: «list suitable coaches based on user preferences and assessment results»")
def p6(c):
    c.prepara("POST", "/api/assessment", json={"answers": [0]})
    c.apri()
    nomi = [x.get("name") for x in elenco(c, "/api/coaches") if isinstance(x, dict) and x.get("name")]
    c.atteso(c.conta("coach-card") >= 1, "almeno una coach-card visibile")
    schede = c.testi("coach-card")
    c.atteso(all(any(n in t for n in nomi) for t in schede),
             "ogni coach-card contiene il nome di un coach di GET /api/coaches")


@passo("7", origine="caso 3: «searching for available coaches»; testo: «search for and select suitable coaches»")
def p7(c):
    coach = c.prepara("GET", "/api/coaches").json
    if not isinstance(coach, list) or not coach or not isinstance(coach[0], dict) or not coach[0].get("specialty"):
        raise NonValutabile("GET /api/coaches non da' un elenco con specialty")
    s = coach[0]["specialty"]
    attesi = [x.get("name") for x in elenco(c, "/api/coaches?q=" + quote(s))]
    c.atteso(len(attesi) >= 1, f"GET /api/coaches?q={s} ha almeno un coach")
    c.apri()
    c.scrivi("coach-search", s)
    c.elemento("coach-search").press("Enter", timeout=5_000)
    c.aspetta(1)

    def giuste():
        schede = [t for i, t in enumerate(c.testi("coach-card")) if c.elemento("coach-card", n=i).is_visible()]
        return len(schede) == len(attesi) and all(any(n in t for n in attesi) for t in schede)
    c.atteso(finche(giuste), f"le coach-card visibili sono i {len(attesi)} coach di ?q={s}")


@passo("8", origine="caso 4: «The session should be added to the user's and coach's calendars»")
def p8(c):
    c.apri()
    c.atteso(c.visibile("coach-card"), "almeno una coach-card")
    scheda = c.testo("coach-card")
    c.clicca("coach-card")
    c.scrivi("session-datetime", "2026-12-01T10:00")
    c.clicca("session-submit")
    sessioni = []

    def una():
        sessioni[:] = [s for s in elenco(c, "/api/sessions") if isinstance(s, dict)]
        return len(sessioni) == 1 and str(sessioni[0].get("datetime", "")).startswith("2026-12-01T10:00")
    c.atteso(finche(una), "GET /api/sessions ha una sola sessione il 2026-12-01T10:00")
    coach = {str(x.get("id")): x.get("name") for x in elenco(c, "/api/coaches") if isinstance(x, dict)}
    nome = coach.get(str(sessioni[0].get("coachId")))
    c.atteso(bool(nome) and nome in scheda, f"il coach della sessione ({nome}) e' quello della scheda cliccata")


@passo("9", origine="caso 5: «The goal should be saved successfully»")
def p9(c):
    c.apri()
    c.scrivi("goal-title", "Correre 5 km")
    c.clicca("goal-add")
    c.atteso(finche(lambda: any(isinstance(g, dict) and g.get("title") == "Correre 5 km"
                                for g in elenco(c, "/api/goals"))), "GET /api/goals contiene Correre 5 km")
    c.atteso(c.conta("goal-progress") >= 1, "nella pagina c'e' almeno un goal-progress")


@passo("10", origine="caso 5: «progress updates should reflect accurately in the system»")
def p10(c):
    c.prepara("POST", "/api/goals", json={"title": "Leggere 10 libri"})
    c.apri()
    c.atteso(c.visibile("goal-progress"), "goal-progress visibile")
    campo = c.elementi("goal-progress").last
    campo.fill("60", timeout=5_000)
    campo.press("Enter", timeout=5_000)
    campo.blur(timeout=5_000)  # «cliccare fuori dal campo»: toglie il fuoco, scatta `change`
    c.aspetta(1)
    c.ricarica()
    c.atteso(finche(lambda: c.elementi("goal-progress").last.input_value(timeout=1_000) == "60"),
             "dopo la ricarica l'ultimo goal-progress vale 60")
    obiettivi = [g for g in elenco(c, "/api/goals") if isinstance(g, dict) and g.get("title") == "Leggere 10 libri"]
    c.atteso(len(obiettivi) == 1 and obiettivi[0].get("progress") == 60,
             "GET /api/goals: progress di Leggere 10 libri = 60")


# ── Test diretti sulle rotte ───────────────────────────────────────────────

def _primo_coach(c):
    coach = c.api("GET", "/api/coaches").json
    c.atteso(isinstance(coach, list) and len(coach) >= 1 and isinstance(coach[0], dict), "GET /api/coaches: elenco")
    return coach[0]


def _crea_obiettivo(c, titolo="A", **altro):
    r = c.api("POST", "/api/goals", json={"title": titolo, **altro})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"POST /api/goals 201 con id ({r.status})")
    return r.json


def _crea_sessione(c, coach_id):
    r = c.api("POST", "/api/sessions", json={"coachId": coach_id, "datetime": "2026-12-01T10:00"})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"POST /api/sessions 201 con id ({r.status})")
    return r.json


@rotta("R1", origine="contratto: crea")
def r1(c):
    g = _crea_obiettivo(c)
    c.atteso(g.get("progress") == 0 and g.get("title") == "A", "obiettivo con progress 0")
    s = _crea_sessione(c, _primo_coach(c)["id"])
    c.atteso(s.get("status") == "confirmed", "sessione con status confirmed")
    r = c.api("POST", "/api/assessment", json={"answers": [0, 1]})
    c.atteso(r.status == 201 and isinstance(r.json, dict) and str(r.json.get("assessmentResult") or "").strip() != "",
             f"POST /api/assessment 201 con assessmentResult ({r.status})")


@rotta("R2", origine="contratto: leggi")
def r2(c):
    g = _crea_obiettivo(c)
    primo = _primo_coach(c)
    s = _crea_sessione(c, primo["id"])
    esito = c.api("POST", "/api/assessment", json={"answers": [0, 1]}).json or {}
    c.atteso(any(x.get("id") == g["id"] and x.get("title") == "A" for x in elenco(c, "/api/goals")), "goals contiene A")
    c.atteso(any(x.get("id") == s["id"] for x in elenco(c, "/api/sessions")), "sessions contiene la sessione")
    c.atteso(profilo(c).get("assessmentResult") == esito.get("assessmentResult"), "profilo con lo stesso risultato")
    tutti = elenco(c, "/api/coaches")
    c.atteso(len(tutti) >= 3 and all(isinstance(x, dict) and {"id", "name", "specialty"} <= x.keys() for x in tutti),
             "almeno 3 coach con id, name, specialty")
    filtrati = elenco(c, "/api/coaches?q=" + quote(str(primo["specialty"]).upper()))
    c.atteso(any(x.get("id") == primo["id"] for x in filtrati) and len(filtrati) <= len(tutti),
             "la ricerca in maiuscolo trova il primo coach")


@rotta("R3", origine="contratto: modifica")
def r3(c):
    g = _crea_obiettivo(c)
    c.atteso(c.api("PATCH", f"/api/goals/{g['id']}", json={"progress": 40}).status == 200, "PATCH goal 200")
    c.atteso(any(x.get("id") == g["id"] and x.get("progress") == 40 for x in elenco(c, "/api/goals")), "progress 40 riletto")
    s = _crea_sessione(c, _primo_coach(c)["id"])
    c.atteso(c.api("PATCH", f"/api/sessions/{s['id']}", json={"datetime": "2026-12-02T09:00"}).status == 200,
             "PATCH sessione 200")
    c.atteso(any(x.get("id") == s["id"] and str(x.get("datetime", "")).startswith("2026-12-02T09:00")
                 for x in elenco(c, "/api/sessions")), "nuova data riletta")
    c.atteso(c.api("PUT", "/api/profile", json={"name": "B"}).status == 200, "PUT profilo 200")
    c.atteso(profilo(c).get("name") == "B", "name B riletto")


@rotta("R4", origine="contratto: cancella")
def r4(c):
    g = _crea_obiettivo(c)
    c.atteso(c.api("DELETE", f"/api/goals/{g['id']}").status == 204, "DELETE goal 204")
    c.atteso(all(x.get("id") != g["id"] for x in elenco(c, "/api/goals")), "obiettivo sparito")
    s = _crea_sessione(c, _primo_coach(c)["id"])
    c.atteso(c.api("DELETE", f"/api/sessions/{s['id']}").status == 204, "DELETE sessione 204")
    c.atteso(all(x.get("id") != s["id"] for x in elenco(c, "/api/sessions")), "sessione sparita")
    c.atteso(c.api("DELETE", "/api/goals/inesistente").status == 404, "DELETE goal inesistente 404")
    c.atteso(c.api("DELETE", "/api/sessions/inesistente").status == 404, "DELETE sessione inesistente 404")


@rotta("R5", origine="contratto: input sbagliato")
def r5(c):
    g = _crea_obiettivo(c)
    primo = _primo_coach(c)
    casi = [("POST", "/api/goals", {}), ("PATCH", f"/api/goals/{g['id']}", {"progress": 150}),
            ("PUT", "/api/profile", {"name": ""}),
            ("POST", "/api/sessions", {"coachId": "inesistente", "datetime": "2026-12-01T10:00"}),
            ("POST", "/api/sessions", {"coachId": primo["id"], "datetime": "non-una-data"}),
            ("POST", "/api/assessment", {"answers": []})]
    for metodo, percorso, corpo in casi:
        stato = c.api(metodo, percorso, json=corpo).status
        c.atteso(stato == 400, f"{metodo} {percorso} {corpo}: 400 ({stato})")
    c.atteso(elenco(c, "/api/sessions") == [], "nessuna sessione creata dagli input sbagliati")


@rotta("R6", origine="contratto: persistenza dopo il riavvio")
def r6(c):
    c.atteso(c.api("PUT", "/api/profile", json={"name": "Persistente"}).status == 200, "PUT profilo")
    esito = (c.api("POST", "/api/assessment", json={"answers": [0, 1]}).json or {}).get("assessmentResult")
    s = _crea_sessione(c, _primo_coach(c)["id"])
    g = _crea_obiettivo(c, "Persistente", progress=40)
    c.riavvia_server()
    p = profilo(c)
    c.atteso(p.get("name") == "Persistente" and p.get("assessmentResult") == esito and bool(esito),
             "profilo e risultato dopo il riavvio")
    c.atteso(any(x.get("id") == s["id"] and str(x.get("datetime", "")).startswith("2026-12-01T10:00")
                 for x in elenco(c, "/api/sessions")), "sessione dopo il riavvio")
    c.atteso(any(x.get("id") == g["id"] and x.get("progress") == 40 for x in elenco(c, "/api/goals")),
             "obiettivo al 40 dopo il riavvio")
