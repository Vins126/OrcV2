"""Compito 842 (ArtifactsBench): «Security Center 3.7», console e audit tracker.

Testo originale (in breve): console di federated learning (stato dei
partecipanti con heartbeat, curva dei tempi di cifratura Paillier) e audit
tracker (riproduzione fotogramma per fotogramma lungo una timeline,
evidenziazione delle differenze prima/dopo una modifica di configurazione).

Bozza R1.3 NON ancora approvata (vedi `842.md`, sezione «Scelte da approvare»).
Nessun contratto delle rotte: i dati sono simulati nel sito, quindi niente
`@rotta` e niente preparazione via rotte. Ogni passo carica la pagina pulita.
"""

from valutazione.libreria import passo


# ── Funzioni d'appoggio ────────────────────────────────────────────────────

def leggi_stato_partecipanti(c):
    """Testo e attributi (class, data-*, title) di tutti gli stati e heartbeat."""
    risultato = []
    for marcatore in ("participant-status", "participant-heartbeat"):
        risultato.append(c.elementi(marcatore).evaluate_all(
            "els => els.map(e => [e.innerText, e.className,"
            " e.getAttribute('title'),"
            " Object.entries(e.dataset).filter(([k]) => k !== 'testid')])"))
    return risultato


def testo_frame(c):
    return c.testo("replay-frame").strip()


def sposta_timeline(c):
    """Porta la timeline alla fine: range -> valore massimo, altrimenti clic al 90%."""
    timeline = c.elemento("replay-timeline")
    timeline.wait_for(state="visible", timeout=5_000)
    e_range = timeline.evaluate("e => e.tagName === 'INPUT' && e.type === 'range'")
    if e_range:
        timeline.evaluate(
            "e => { e.value = e.max || '100';"
            " e.dispatchEvent(new Event('input', {bubbles: true}));"
            " e.dispatchEvent(new Event('change', {bubbles: true})); }")
    else:
        riquadro = timeline.bounding_box()
        c.atteso(riquadro is not None, "replay-timeline ha dimensioni")
        timeline.click(position={"x": riquadro["width"] * 0.9, "y": riquadro["height"] / 2},
                       timeout=5_000)


# ── Passi d'interfaccia ────────────────────────────────────────────────────

@passo("1", origine="testo: «Participant Status Dashboard (Heartbeat Detection)»; "
                    "checklist 0: «participant status dashboard ... proper connection state visualization»")
def p1(c):
    c.apri()
    c.atteso(c.conta("participant-status") >= 2, "almeno 2 participant-status visibili")
    c.atteso(c.conta("participant-heartbeat") >= 2, "almeno 2 participant-heartbeat visibili")
    testi = c.testi("participant-status") + c.testi("participant-heartbeat")
    c.atteso(all(t.strip() for t in testi), "stati e heartbeat con testo non vuoto")


@passo("2", origine="testo: «Heartbeat Detection»; checklist 0: «Score 0 if dashboard lacks real-time updates»")
def p2(c):
    c.apri()
    c.atteso(c.visibile("participant-status") and c.visibile("participant-heartbeat"),
             "participant-status e participant-heartbeat visibili")
    prima = leggi_stato_partecipanti(c)
    c.aspetta(10)
    dopo = leggi_stato_partecipanti(c)
    c.atteso(prima != dopo, "in 10 s senza interazione cambia almeno uno stato o heartbeat")


@passo("3", origine="testo: «Paillier encryption time consumption curves»; "
                    "checklist 0: «Paillier encryption time curves»")
def p3(c):
    c.apri()
    c.atteso(c.visibile("encryption-chart"), "encryption-chart visibile")
    grafico = c.elemento("encryption-chart")
    riquadro = grafico.bounding_box()
    c.atteso(riquadro is not None and riquadro["width"] > 100 and riquadro["height"] > 100,
             f"encryption-chart piu' grande di 100x100 px ({riquadro})")
    disegno = grafico.evaluate(
        "e => ['CANVAS', 'SVG'].includes(e.tagName.toUpperCase())"
        " || e.querySelector('canvas, svg') !== null")
    c.atteso(disegno, "encryption-chart e' o contiene un canvas o un svg")


@passo("4", origine="testo: «Frame-by-frame playback of user operations»; "
                    "checklist 1: «step-by-step operation reconstruction»")
def p4(c):
    c.apri()
    f0 = testo_frame(c)
    p0 = c.testo("replay-position").strip()
    c.clicca("replay-step")
    c.aspetta(0.5)
    f1 = testo_frame(c)
    c.atteso(f1 != "" and f1 != f0, f"replay-frame cambia dopo replay-step ({f0!r} -> {f1!r})")
    p1_ = c.testo("replay-position").strip()
    c.atteso(p1_ != p0, f"replay-position cambia dopo replay-step ({p0!r} -> {p1_!r})")


@passo("5", origine="testo: «along a timeline»; checklist 1: «timeline scrubbing», "
                    "«3 points if timeline navigation is missing»")
def p5(c):
    c.apri()
    f0 = testo_frame(c)
    sposta_timeline(c)
    c.aspetta(0.5)
    f1 = testo_frame(c)
    c.atteso(f1 != f0, f"replay-frame cambia spostando la timeline ({f0!r} -> {f1!r})")


@passo("6", origine="testo: «playback of user operations»; checklist 1: «smooth playback/pause functionality»")
def p6(c):
    c.apri()
    f0 = testo_frame(c)
    c.clicca("replay-play")
    c.aspetta(5)
    f1 = testo_frame(c)
    c.atteso(f1 != f0, f"replay-frame avanza da solo dopo replay-play ({f0!r} -> {f1!r})")


@passo("7", origine="checklist 1: «smooth playback/pause functionality»")
def p7(c):
    c.apri()
    c.clicca("replay-play")
    c.aspetta(2)
    c.clicca("replay-pause")
    f1 = testo_frame(c)
    c.aspetta(5)
    f2 = testo_frame(c)
    c.atteso(f2 == f1, f"replay-frame fermo dopo replay-pause ({f1!r} -> {f2!r})")


@passo("8", origine="testo: «Difference Highlighting»; checklist 2: «color-coded modifications»")
def p8(c):
    c.apri()
    c.atteso(c.visibile("diff-changed"), "almeno un diff-changed visibile")
    evidenziati = c.elementi("diff-changed").evaluate_all(
        "els => els.filter(e => e.offsetParent !== null && e.innerText.trim() !== '').map(e => {"
        " const s = getComputedStyle(e), p = getComputedStyle(e.parentElement);"
        " return ['background-color', 'color', 'border-color']"
        ".some(k => s.getPropertyValue(k) !== p.getPropertyValue(k)); })")
    c.atteso(any(evidenziati), "un diff-changed con testo ha colore, sfondo o bordo diverso dal padre")


@passo("9", origine="testo: «parameter comparison before and after configuration changes»; "
                    "checklist 2: «parameter comparison functionality»")
def p9(c):
    c.apri()
    c.atteso(c.visibile("diff-changed"), "almeno un diff-changed visibile")
    riga = c.elemento("diff-changed")
    c.atteso(c.visibile("diff-before", dentro=riga) and c.visibile("diff-after", dentro=riga),
             "diff-before e diff-after visibili dentro il primo diff-changed")
    prima = c.testo("diff-before", dentro=riga).strip()
    dopo = c.testo("diff-after", dentro=riga).strip()
    c.atteso(prima != "" and dopo != "" and prima != dopo,
             f"valori prima/dopo non vuoti e diversi ({prima!r}, {dopo!r})")
