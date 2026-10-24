"""Compito 684 (ArtifactsBench): gestione di file con etichette e filtri.

Testo originale: «Create a file tag management platform where users can upload
files and add multiple tags (such as 'work', 'important', etc.) to each file,
supporting quick filtering of files by tags.»

Approvato dall'autore il 23 ott 2026 (bozza R1.3 con 12 marcatori, CRUD anche
nell'interfaccia, vetrina per gli screenshot). Ogni passo riparte da un sito
pulito; i dati preparati via rotte, se la rotta fallisce, rendono il passo «non
valutabile» (PROTOCOLLO §6). I file di prova stanno in `file/`.
"""

from valutazione.libreria import passo, rotta

#: Dati della vetrina e dei passi sui filtri: nome del file -> etichette.
TRIO = {"nota.txt": ["work", "important"], "foto.png": ["work"], "relazione.pdf": ["personal"]}


# ── Funzioni d'appoggio ────────────────────────────────────────────────────

def file_item(c, nome):
    """Il `file-item` il cui `file-name` ha esattamente quel testo."""
    nome_esatto = c.pagina.get_by_test_id("file-name").get_by_text(nome, exact=True)
    return c.pagina.get_by_test_id("file-item").filter(has=nome_esatto)


def visibile_file(c, nome, attesa_ms=5_000):
    try:
        file_item(c, nome).first.wait_for(state="visible", timeout=attesa_ms)
        return True
    except Exception:
        return False


def etichette(c, nome):
    """Testi dei `file-tag` di un file, senza il testo dei loro `tag-remove`."""
    item = file_item(c, nome).first
    try:
        item.wait_for(state="visible", timeout=5_000)
    except Exception:
        return set()
    return set(item.get_by_test_id("file-tag").evaluate_all(
        "els => els.map(e => { const k = e.cloneNode(true);"
        " k.querySelectorAll('[data-testid=tag-remove]').forEach(x => x.remove());"
        " return k.textContent.trim(); })"))


def carica_da_interfaccia(c, nome):
    c.carica_file("upload-input", nome)
    c.clicca("upload-submit")


def crea_via_rotte(c, nome, tag=None):
    """Carica un file con la rotta del contratto e, se richiesto, gli da' le etichette."""
    r = c.prepara("POST", "/api/files", file=nome)
    id_ = r.json["id"]
    if tag is not None:
        c.prepara("PUT", f"/api/files/{id_}/tags", json={"tags": tag})
    return id_


def vetrina(c):
    """Dati d'esempio per gli screenshot del giudice (regola della vetrina, PROTOCOLLO §6)."""
    for nome, tag in TRIO.items():
        crea_via_rotte(c, nome, tag)


# ── Passi d'interfaccia ────────────────────────────────────────────────────

@passo("1", origine="testo: «users can upload files»")
def p1(c):
    c.apri()
    try:  # l'input dei file puo' essere nascosto sotto un pulsante disegnato: basta che esista
        c.elementi("upload-input").first.wait_for(state="attached", timeout=5_000)
        presente = True
    except Exception:
        presente = False
    c.atteso(presente, "esiste upload-input")
    c.atteso(c.visibile("upload-submit"), "upload-submit visibile")


@passo("2", origine="testo: «upload files»; checklist 0: «Is the file upload system fully implemented?»")
def p2(c):
    c.apri()
    carica_da_interfaccia(c, "nota.txt")
    c.atteso(visibile_file(c, "nota.txt"), "nota.txt compare nella lista")
    elenco = c.api("GET", "/api/files").json or []
    c.atteso([f.get("name") for f in elenco] == ["nota.txt"], "il server ha un file, nota.txt")


@passo("3", origine="checklist 0: «Check if multiple file formats are supported»")
def p3(c):
    c.apri()
    carica_da_interfaccia(c, "foto.png")
    c.atteso(visibile_file(c, "foto.png"), "foto.png compare")
    carica_da_interfaccia(c, "relazione.pdf")
    c.atteso(visibile_file(c, "relazione.pdf"), "relazione.pdf compare")


@passo("4", origine="checklist 3: «proper data storage»")
def p4(c):
    c.apri()
    carica_da_interfaccia(c, "nota.txt")
    c.atteso(visibile_file(c, "nota.txt"), "nota.txt caricato")
    c.ricarica()
    c.atteso(visibile_file(c, "nota.txt"), "nota.txt c'e' ancora dopo la ricarica")


@passo("5", origine="testo: «add ... tags (such as 'work' ...) to each file»")
def p5(c):
    crea_via_rotte(c, "nota.txt")
    crea_via_rotte(c, "foto.png")
    c.apri()
    c.scrivi("tag-input", "work", dentro=file_item(c, "nota.txt"))
    c.clicca("tag-add", dentro=file_item(c, "nota.txt"))
    c.aspetta(0.5)
    c.atteso("work" in etichette(c, "nota.txt"), "nota.txt ha l'etichetta work")
    c.atteso("work" not in etichette(c, "foto.png"), "foto.png non ha l'etichetta work")


@passo("6", origine="testo: «add multiple tags (such as 'work', 'important')»")
def p6(c):
    crea_via_rotte(c, "nota.txt", ["work"])
    c.apri()
    c.scrivi("tag-input", "important", dentro=file_item(c, "nota.txt"))
    c.clicca("tag-add", dentro=file_item(c, "nota.txt"))
    c.aspetta(0.5)
    c.atteso(etichette(c, "nota.txt") == {"work", "important"}, "nota.txt ha work e important")


@passo("7", origine="checklist 3: «file metadata management»")
def p7(c):
    id_ = crea_via_rotte(c, "nota.txt")
    c.apri()
    for tag in ("work", "important"):
        c.scrivi("tag-input", tag, dentro=file_item(c, "nota.txt"))
        c.clicca("tag-add", dentro=file_item(c, "nota.txt"))
        c.aspetta(0.5)
    c.ricarica()
    c.atteso(etichette(c, "nota.txt") == {"work", "important"}, "le etichette restano dopo la ricarica")
    salvate = set((c.api("GET", f"/api/files/{id_}").json or {}).get("tags") or [])
    c.atteso(salvate == {"work", "important"}, "il server ha salvato work e important")


@passo("8", origine="testo: «supporting quick filtering of files by tags»")
def p8(c):
    vetrina(c)
    c.apri()
    c.clicca("filter-tag", testo="work")
    c.aspetta(0.5)
    c.atteso(visibile_file(c, "nota.txt") and visibile_file(c, "foto.png"), "visibili nota.txt e foto.png")
    c.atteso(not visibile_file(c, "relazione.pdf", attesa_ms=500), "relazione.pdf nascosto")


@passo("9", origine="testo: «filtering of files by tags»")
def p9(c):
    vetrina(c)
    c.apri()
    c.clicca("filter-tag", testo="important")
    c.aspetta(0.5)
    c.atteso(visibile_file(c, "nota.txt"), "visibile nota.txt")
    c.atteso(not visibile_file(c, "foto.png", attesa_ms=500)
             and not visibile_file(c, "relazione.pdf", attesa_ms=500), "gli altri nascosti")


@passo("10", origine="checklist 2: «Is the file filtering ... accurate?»")
def p10(c):
    vetrina(c)
    c.apri()
    c.clicca("filter-tag", testo="personal")
    c.aspetta(0.5)
    c.clicca("filter-clear")
    c.aspetta(0.5)
    c.atteso(all(visibile_file(c, n) for n in TRIO), "dopo filter-clear si vedono tutti e tre")


@passo("11", origine="testo: filtro sulle etichette aggiunte dall'utente")
def p11(c):
    crea_via_rotte(c, "nota.txt")
    crea_via_rotte(c, "foto.png")
    c.apri()
    c.scrivi("tag-input", "urgent", dentro=file_item(c, "nota.txt"))
    c.clicca("tag-add", dentro=file_item(c, "nota.txt"))
    c.atteso(c.visibile("filter-tag", testo="urgent"), "compare il filtro urgent senza ricaricare")
    c.clicca("filter-tag", testo="urgent")
    c.aspetta(0.5)
    c.atteso(visibile_file(c, "nota.txt") and not visibile_file(c, "foto.png", attesa_ms=500),
             "con il filtro urgent si vede solo nota.txt")


@passo("12", origine="protocollo: CRUD completo, «es. cancellare un file in 684»")
def p12(c):
    crea_via_rotte(c, "nota.txt")
    crea_via_rotte(c, "foto.png")
    c.apri()
    c.clicca("file-delete", dentro=file_item(c, "nota.txt"))
    c.aspetta(0.5)
    c.atteso(not visibile_file(c, "nota.txt", attesa_ms=1_000), "nota.txt sparisce")
    c.atteso(visibile_file(c, "foto.png"), "foto.png resta")
    elenco = c.api("GET", "/api/files").json or []
    c.atteso([f.get("name") for f in elenco] == ["foto.png"], "il server ha solo foto.png")


@passo("13", origine="protocollo: modifica delle etichette; checklist 1: «deleting unused tags»")
def p13(c):
    crea_via_rotte(c, "nota.txt", ["work", "important"])
    c.apri()
    work = file_item(c, "nota.txt").get_by_test_id("file-tag").filter(has_text="work")
    c.clicca("tag-remove", dentro=work)
    c.aspetta(0.5)
    c.ricarica()
    c.atteso(etichette(c, "nota.txt") == {"important"}, "resta solo important dopo la ricarica")


# ── Test diretti sulle rotte ───────────────────────────────────────────────

def _crea(c, nome="nota.txt"):
    r = c.api("POST", "/api/files", file=nome)
    c.atteso(r.status == 201 and isinstance(r.json, dict) and "id" in r.json, f"201 con id ({r.status})")
    return r.json


@rotta("R1", origine="contratto: crea")
def r1(c):
    f = _crea(c)
    c.atteso(f.get("name") == "nota.txt" and f.get("size") == 4 and f.get("tags") == [],
             "name, size e tags corretti")


@rotta("R2", origine="contratto: leggi")
def r2(c):
    f = _crea(c)
    elenco = c.api("GET", "/api/files")
    c.atteso(elenco.status == 200 and any(x.get("id") == f["id"] for x in elenco.json or []), "elenco")
    uno = c.api("GET", f"/api/files/{f['id']}")
    c.atteso(uno.status == 200 and (uno.json or {}).get("name") == "nota.txt", "lettura del singolo")
    contenuto = c.api("GET", f"/api/files/{f['id']}/content")
    c.atteso(contenuto.status == 200 and contenuto.testo == "ciao", "contenuto identico")


@rotta("R3", origine="contratto: modifica")
def r3(c):
    f = _crea(c)
    r = c.api("PUT", f"/api/files/{f['id']}/tags", json={"tags": ["work", "important"]})
    c.atteso(r.status == 200, f"PUT 200 ({r.status})")
    c.atteso(set(c.api("GET", f"/api/files/{f['id']}").json["tags"]) == {"work", "important"}, "rilette")
    c.api("PUT", f"/api/files/{f['id']}/tags", json={"tags": ["important"]})
    c.atteso(c.api("GET", f"/api/files/{f['id']}").json["tags"] == ["important"], "sostituite")


@rotta("R4", origine="contratto: filtro")
def r4(c):
    a = _crea(c, "nota.txt")
    _crea(c, "foto.png")
    c.api("PUT", f"/api/files/{a['id']}/tags", json={"tags": ["work"]})
    r = c.api("GET", "/api/files?tag=work")
    c.atteso(r.status == 200 and [x.get("id") for x in r.json or []] == [a["id"]], "solo il file con work")


@rotta("R5", origine="contratto: cancella")
def r5(c):
    f = _crea(c)
    c.atteso(c.api("DELETE", f"/api/files/{f['id']}").status == 204, "DELETE 204")
    c.atteso(c.api("GET", f"/api/files/{f['id']}").status == 404, "poi 404")
    c.atteso(c.api("GET", f"/api/files/{f['id']}/content").status == 404, "contenuto 404")


@rotta("R6", origine="contratto: input sbagliato")
def r6(c):
    f = _crea(c)
    c.atteso(c.api("POST", "/api/files", json={}).status == 400, "POST senza file: 400")
    for corpo in ({"tags": "work"}, {"tags": [""]}, {}):
        c.atteso(c.api("PUT", f"/api/files/{f['id']}/tags", json=corpo).status == 400, f"400 per {corpo}")
    c.atteso(c.api("GET", f"/api/files/{f['id']}").json["tags"] == [], "lo stato non cambia")


@rotta("R7", origine="contratto: id inesistente")
def r7(c):
    c.atteso(c.api("GET", "/api/files/inesistente").status == 404, "GET 404")
    c.atteso(c.api("PUT", "/api/files/inesistente/tags", json={"tags": ["x"]}).status == 404, "PUT 404")
    c.atteso(c.api("DELETE", "/api/files/inesistente").status == 404, "DELETE 404")


@rotta("R8", origine="contratto: persistenza dopo il riavvio")
def r8(c):
    f = _crea(c)
    c.api("PUT", f"/api/files/{f['id']}/tags", json={"tags": ["work"]})
    c.riavvia_server()
    c.atteso(c.api("GET", f"/api/files/{f['id']}").json["tags"] == ["work"], "etichette dopo il riavvio")
    c.atteso(c.api("GET", f"/api/files/{f['id']}/content").testo == "ciao", "contenuto dopo il riavvio")
