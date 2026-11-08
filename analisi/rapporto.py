"""Analisi della campagna MVP da dati.json: tabelle, intervalli, grafici SVG, rapporto.

Uso: venv/bin/python -m analisi.rapporto  (dopo `python -m analisi.estrai`). Nessuna chiamata a modelli.
Scrive `runs/analisi-mvp/rapporto.md` e i grafici, copiati anche in `docs/figure/mvp/` per la tesi.
"""

import collections
import json
import math
import random
import re
import statistics as st
import subprocess
import tempfile
from pathlib import Path

from analisi.statistica import EXACT_MAX_N, SEED, bootstrap, paired_t

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "runs" / "analisi-mvp"
FIGURES = ROOT / "docs" / "figure" / "mvp"
D = json.loads((HERE / "dati.json").read_text())
REC = D["records"]
TASKS = sorted({r["task"] for r in REC})
ARMS = ["B", "C", "D"]
BY = {(r["arm"], r["task"]): r for r in REC}
# Durate attraversate dallo stop del Mac (regola «Guasti della macchina»): non valide come tempo.
WALL_INVALID = {("B", "000058"), ("C", "000098"), ("C", "000058"), ("D", "000058")}
PRICES = {"opus-5-5": {"input_tokens": 4.0, "output_tokens": 20.0, "cached_input_tokens": 0.20, "cache_write_tokens": 5.0},
          "kimi-k3-1-pro": {"input_tokens": 2.0, "output_tokens": 10.0, "cached_input_tokens": 0.20},
          "deepseek-v4-1-flash": {"input_tokens": 0.15, "output_tokens": 0.60, "cached_input_tokens": 0.003}}
COLORS = {"B": "#3b6fb6", "C": "#c8553d", "D": "#5b8c5a", "V": "#8a6bb1"}
OUT_LINES: list[str] = []
RESULTS: dict = {}


def out(text=""):
    OUT_LINES.append(text)


def fmt(x, nd=2, sign=False):
    if x is None:
        return "n.d."
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",")


# --- statistica (analisi/statistica.py) ---

def boot(values_by_task, stat):
    return bootstrap(len(values_by_task), stat)


def t_test(diffs):
    mean, p, interval = paired_t(diffs)
    return mean, None, p, interval


# --- dati di base ---

def cost(arm, task):
    return BY[(arm, task)]["manifest_cost"]


def fun(arm, task):
    return BY[(arm, task)]["funziona"]


VOTE = {}
for j in D["judgments"]:
    pair, task = j["item"].split("/")
    VOTE[(pair[0], task)] = j["value"]


def piace(arm, task):
    return VOTE.get((arm, task))


# V: si tiene il sito di D se il cancello lo accetta, altrimenti B da zero (D49)
V = {}
for task in TASKS:
    d = BY[("D", task)]
    accepted = bool(d["gate_accepted"])
    V[task] = {"accepted": accepted,
               "cost": cost("D", task) + (0 if accepted else cost("B", task)),
               "fun": fun("D", task) if accepted else fun("B", task),
               "piace": piace("D", task) if accepted else 0.0}


def arm_cost(a, t):
    return V[t]["cost"] if a == "V" else cost(a, t)


def arm_fun(a, t):
    return V[t]["fun"] if a == "V" else fun(a, t)


def arm_piace(a: str, t: str) -> float:
    # Ogni coppia della campagna ha un voto: un voto mancante e' un errore dei dati, non un pari.
    if a == "B":
        return 0.0
    value = V[t]["piace"] if a == "V" else VOTE[(a, t)]
    if value is None:
        raise ValueError(f"voto non valutabile per {a}-B/{t}")
    return float(value)


# --- grafici SVG ---

def svg_scatter(path, title, xlab, ylab, points, *, xlog=False, ylim=None, hline=None, means=None):
    W, H, L, R, T, B = 640, 440, 70, 20, 62, 55
    xs = [p[0] for p in points] + ([m[0] for m in means] if means else [])
    ys = [p[1] for p in points] + ([m[1] for m in means] if means else [])
    if xlog:
        tx = lambda v: math.log10(v)
        x0, x1 = math.floor(min(map(tx, xs)) * 2) / 2, math.ceil(max(map(tx, xs)) * 2) / 2
    else:
        tx = lambda v: v
        x0, x1 = 0, max(xs) * 1.08
    y0, y1 = ylim if ylim else (min(ys) - 0.1 * abs(min(ys) or 1), max(ys) * 1.05)
    px = lambda v: L + (tx(v) - x0) / (x1 - x0) * (W - L - R)
    py = lambda v: T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>',
         f'<line x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}" stroke="#333"/><line x1="{L}" y1="{T}" x2="{L}" y2="{H-B}" stroke="#333"/>',
         f'<text x="{(L+W-R)/2}" y="{H-12}" text-anchor="middle">{xlab}</text>',
         f'<text x="16" y="{(T+H-B)/2}" text-anchor="middle" transform="rotate(-90 16 {(T+H-B)/2})">{ylab}</text>']
    if xlog:
        v = x0
        while v <= x1 + 1e-9:
            e.append(f'<line x1="{px(10**v)}" y1="{H-B}" x2="{px(10**v)}" y2="{H-B+5}" stroke="#333"/>'
                     f'<text x="{px(10**v)}" y="{H-B+18}" text-anchor="middle">{10**v:.2g} $</text>')
            v += 0.5
    else:
        for i in range(6):
            v = x0 + (x1 - x0) * i / 5
            e.append(f'<text x="{px(v)}" y="{H-B+18}" text-anchor="middle">{v:.1f}</text>')
    for i in range(6):
        v = y0 + (y1 - y0) * i / 5
        e.append(f'<line x1="{L}" y1="{py(v)}" x2="{W-R}" y2="{py(v)}" stroke="#eee"/>'
                 f'<text x="{L-6}" y="{py(v)+4}" text-anchor="end">{v:.1f}</text>')
    if hline is not None:
        e.append(f'<line x1="{L}" y1="{py(hline[0])}" x2="{W-R}" y2="{py(hline[0])}" stroke="#999" stroke-dasharray="5,4"/>'
                 f'<text x="{W-R-4}" y="{py(hline[0])-5}" text-anchor="end" fill="#666">{hline[1]}</text>')
    for x, y, arm, label in points:
        e.append(f'<circle cx="{px(x)}" cy="{py(y)}" r="5" fill="{COLORS[arm]}" fill-opacity="0.55"/>'
                 f'<text x="{px(x)+7}" y="{py(y)-6}" font-size="9" fill="#555">{label}</text>')
    merged: dict = {}
    for x, y, arm in means or []:
        merged.setdefault((round(x, 6), round(y, 6)), []).append(arm)
    for (x, y), arms in merged.items():
        e.append(f'<rect x="{px(x)-8}" y="{py(y)-8}" width="16" height="16" fill="{COLORS[arms[0]]}" stroke="black"/>'
                 f'<text x="{px(x)+12}" y="{py(y)+4}" font-weight="bold">{" = ".join(arms)}</text>')
    lx = L + 10
    for arm in [a for a in ["B", "C", "D", "V"] if any(p[2] == a for p in points)]:
        e.append(f'<circle cx="{lx}" cy="{T-16}" r="5" fill="{COLORS[arm]}"/><text x="{lx+9}" y="{T-12}">{arm}</text>')
        lx += 45
    e.append(f'<text x="{W-R}" y="{T-12}" text-anchor="end" fill="#666">punto = un compito; quadrato = media sui 5 compiti</text>' if means else "")
    e.append("</svg>")
    path.write_text("\n".join(e), encoding="utf-8")


def svg_bars(path, title, groups, series, values, ylab, *, ymin=0, ymax=None, fmtv=lambda v: f"{v:.0f}"):
    W, H, L, R, T, B = 680, 380, 60, 20, 45, 50
    ymax = ymax if ymax is not None else max(v for v in values.values() if v is not None) * 1.1
    gw = (W - L - R) / len(groups)
    bw = gw * 0.8 / len(series)
    py = lambda v: T + (1 - (v - ymin) / (ymax - ymin)) * (H - T - B)
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>',
         f'<text x="16" y="{(T+H-B)/2}" text-anchor="middle" transform="rotate(-90 16 {(T+H-B)/2})">{ylab}</text>']
    for i in range(6):
        v = ymin + (ymax - ymin) * i / 5
        e.append(f'<line x1="{L}" y1="{py(v)}" x2="{W-R}" y2="{py(v)}" stroke="#eee"/><text x="{L-6}" y="{py(v)+4}" text-anchor="end">{fmtv(v)}</text>')
    zero = py(max(ymin, 0))
    for gi, g in enumerate(groups):
        for si, s in enumerate(series):
            v = values.get((s, g))
            if v is None:
                continue
            x = L + gi * gw + gw * 0.1 + si * bw
            top, bottom = (py(v), zero) if v >= 0 else (zero, py(v))
            e.append(f'<rect x="{x}" y="{top}" width="{bw-2}" height="{max(bottom-top,1)}" fill="{COLORS.get(s, "#888")}"/>'
                     f'<text x="{x+bw/2-1}" y="{top-3 if v>=0 else bottom+11}" text-anchor="middle" font-size="9">{fmtv(v)}</text>')
        e.append(f'<text x="{L+gi*gw+gw/2}" y="{H-B+18}" text-anchor="middle">{g}</text>')
    e.append(f'<line x1="{L}" y1="{zero}" x2="{W-R}" y2="{zero}" stroke="#333"/>')
    lx = L + 10
    for s in series:
        e.append(f'<rect x="{lx}" y="{T-12}" width="10" height="10" fill="{COLORS.get(s, "#888")}"/><text x="{lx+14}" y="{T-3}">{s}</text>')
        lx += 60
    e.append("</svg>")
    path.write_text("\n".join(e), encoding="utf-8")


def svg_stack(path, title, rows, parts, colors, xlab):
    W, H, L, R, T = 680, 60 + 34 * len(rows), 110, 30, 50
    xmax = max(sum(v.values()) for _, v in rows) * 1.08
    px = lambda v: L + v / xmax * (W - L - R)
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H+30}" font-family="Helvetica,Arial,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H+30}" fill="white"/>',
         f'<text x="{W/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>']
    for i, (label, vals) in enumerate(rows):
        y = T + i * 34
        x = L
        e.append(f'<text x="{L-8}" y="{y+16}" text-anchor="end">{label}</text>')
        for part in parts:
            v = vals.get(part, 0)
            if v <= 0:
                continue
            w = px(v) - L
            e.append(f'<rect x="{x}" y="{y}" width="{w}" height="24" fill="{colors[part]}"/>')
            if w > 28:
                e.append(f'<text x="{x+w/2}" y="{y+16}" text-anchor="middle" fill="white" font-size="10">{v:.2f}</text>')
            x += w
        e.append(f'<text x="{x+4}" y="{y+16}" font-size="10">{sum(vals.values()):.2f} $</text>')
    lx = L
    for part in parts:
        e.append(f'<rect x="{lx}" y="{H}" width="10" height="10" fill="{colors[part]}"/><text x="{lx+14}" y="{H+9}">{part}</text>')
        lx += 150
    e.append(f'<text x="{W-R}" y="{H+24}" text-anchor="end" fill="#666">{xlab}</text></svg>')
    path.write_text("\n".join(e), encoding="utf-8")


# --- colori dagli screenshot (sips -> BMP) ---

def pixels(png, width=240):
    with tempfile.TemporaryDirectory() as tmp:
        bmp = Path(tmp) / "x.bmp"
        subprocess.run(["sips", "-s", "format", "bmp", "--resampleWidth", str(width), str(png), "--out", str(bmp)],
                       capture_output=True, check=True)
        data = bmp.read_bytes()
    off = int.from_bytes(data[10:14], "little")
    w = int.from_bytes(data[18:22], "little", signed=True)
    h = int.from_bytes(data[22:26], "little", signed=True)
    bpp = int.from_bytes(data[28:30], "little")
    step = bpp // 8
    row = (w * step + 3) // 4 * 4
    px = []
    for y in range(abs(h)):
        base = off + y * row
        for x in range(w):
            b, g, r = data[base + x * step: base + x * step + 3]
            px.append((r, g, b))
    return px


def near(p, c, tol):
    return (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2 <= tol * tol


REQUIRED = {"000098": ("papaya whip", (255, 239, 213), "dark orange", (255, 140, 0)),
            "000040": ("light cyan", (224, 255, 255), "cadet blue", (95, 158, 160)),
            "000058": ("beige", (245, 245, 220), "saddle brown", (139, 69, 19))}


# ========================= RAPPORTO =========================

out("# Analisi della campagna MVP (8 nov 2026)")
out()
out("Fonte: manifesti `runs/campaigns/mvp-*.jsonl`, registri delle run (`runs/<run_id>/`), registri dello sciame, "
    "`valutazione.json`, workspace dei siti, giudizi `runs/giudizio-mvp/giudizi.jsonl`. Script: `analisi/estrai.py` e "
    f"`analisi/rapporto.py` nel repository. Bootstrap esatto sui 5 compiti (tutti i 5^5 = 3125 ricampionamenti, regola di PROTOCOLLO §10 "
    f"fino a {EXACT_MAX_N} compiti; oltre, seme {SEED}). "
    "Le cifre sono una **stima su 5 compiti** (D55): nessuna e' una dimostrazione statistica, tranne dove indicato con la regola del §10.")
out()

# 1. tabella principale
out("## 1. Tabella principale (PROTOCOLLO §7 e §10)")
out()
out("| Braccio | Costo totale $ | Costo medio $ | Funziona medio | Piace medio (vs B) | Costo / B |")
out("|---|---|---|---|---|---|")
tot_b = sum(cost("B", t) for t in TASKS)
main = {}
for a in ["B", "C", "D", "V"]:
    c = [arm_cost(a, t) for t in TASKS]
    f = [arm_fun(a, t) for t in TASKS]
    pz = [arm_piace(a, t) for t in TASKS]
    main[a] = (sum(c), st.mean(f), st.mean(pz))
    out(f"| {a} | {fmt(sum(c))} | {fmt(st.mean(c))} | {fmt(st.mean(f),1)} | {fmt(st.mean(pz),2,True) if a!='B' else '0 (rif.)'} | {fmt(sum(c)/tot_b,3)} |")
out()
RESULTS["main"] = main
out("Per compito:")
out()
out("| Compito | B $ | C $ | D $ | V $ | B f | C f | D f | V f | piace C | piace D | piace V | D accettato dal cancello |")
out("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for t in TASKS:
    out(f"| {t} | {fmt(cost('B',t))} | {fmt(cost('C',t))} | {fmt(cost('D',t))} | {fmt(V[t]['cost'])} | "
        f"{fmt(fun('B',t),1)} | {fmt(fun('C',t),1)} | {fmt(fun('D',t),1)} | {fmt(V[t]['fun'],1)} | "
        f"{fmt(piace('C',t),1,True)} | {fmt(piace('D',t),1,True)} | {fmt(V[t]['piace'],1,True)} | {'si' if V[t]['accepted'] else 'no'} |")
out()

# 2. confronti con intervallo
out("## 2. Confronti con B: intervalli bootstrap e test t appaiato (§10)")
out()
out("Regole del §10: C non inferiore su «funziona» se il limite basso al 2,5% della differenza supera −τ = −10; "
    "«costa meno» dimostrato se tutto l'intervallo del rapporto di costo sta sotto 1. Test t appaiato come controllo. "
    "Per D e V solo descrittivo.")
out()
out("| Confronto | Stima | IC bootstrap 95% | Test t: IC 95% | p (t) | Esito §10 |")
out("|---|---|---|---|---|---|")
cmp_res = {}
for a in ["C", "D", "V"]:
    diffs = [arm_fun(a, t) - fun("B", t) for t in TASKS]
    lo, hi = boot(diffs, lambda ix: st.mean(diffs[i] for i in ix))
    m, tt, p, (tlo, thi) = t_test(diffs)
    verdict = ""
    if a == "C":
        verdict = "non inferiore" if lo > -10 and tlo > -10 else ("non dimostrato" if lo <= -10 or tlo <= -10 else "")
    out(f"| funziona {a} − B (punti) | {fmt(m,1,True)} | [{fmt(lo,1,True)}; {fmt(hi,1,True)}] | [{fmt(tlo,1,True)}; {fmt(thi,1,True)}] | {fmt(p,3) if p is not None else 'n.d.'} | {verdict or 'descrittivo'} |")
    cmp_res[f"fun_{a}"] = (m, lo, hi, tlo, thi, p)
    ca = [arm_cost(a, t) for t in TASKS]
    cb = [cost("B", t) for t in TASKS]
    ratio = sum(ca) / sum(cb)
    rlo, rhi = boot(ca, lambda ix: sum(ca[i] for i in ix) / sum(cb[i] for i in ix))
    logd = [math.log(ca[i] / cb[i]) for i in range(5)]
    lm, lt, lp, (llo, lhi) = t_test(logd)
    verdict = ("costa meno: dimostrato" if rhi < 1 else "non dimostrato") if a == "C" else "descrittivo"
    out(f"| costo {a} / B | {fmt(ratio,3)} | [{fmt(rlo,3)}; {fmt(rhi,3)}] | media geometrica {fmt(math.exp(lm),3)} [{fmt(math.exp(llo),3)}; {fmt(math.exp(lhi),3)}] | {fmt(lp,4)} | {verdict} |")
    cmp_res[f"cost_{a}"] = (ratio, rlo, rhi)
    if a != "V" or True:
        pz = [arm_piace(a, t) for t in TASKS]
        plo, phi = boot(pz, lambda ix: st.mean(pz[i] for i in ix))
        pm, pt, pp, (pplo, pphi) = t_test(pz)
        out(f"| piace {a} vs B (−2..+2) | {fmt(pm,2,True)} | [{fmt(plo,2,True)}; {fmt(phi,2,True)}] | [{fmt(pplo,2,True)}; {fmt(pphi,2,True)}] | {fmt(pp,3) if pp is not None else 'n.d.'} | descrittivo (§6); τ_piace −1: limite basso {'sopra' if plo > -1 else 'sotto'} |")
        cmp_res[f"piace_{a}"] = (pm, plo, phi)
out()
RESULTS["cmp"] = cmp_res
# sensibilita': senza il compito peggiore
diffs_c = {t: fun("C", t) - fun("B", t) for t in TASKS}
worst = min(diffs_c, key=lambda t: diffs_c[t])
rest = [v for t, v in diffs_c.items() if t != worst]
out(f"**Sensibilita'.** Il limite basso di «funziona» di C dipende da un solo compito: su {worst} C perde "
    f"{fmt(-diffs_c[worst],1)} punti; sugli altri quattro la differenza media e' {fmt(st.mean(rest),1,True)} "
    f"(min {fmt(min(rest),1,True)}). Con 5 compiti, un compito vale il 20% della media.")
out()
# quanti compiti servirebbero
sd_c = st.stdev(diffs_c.values())
n_need = math.ceil(((1.96 * sd_c) / (st.mean(diffs_c.values()) + 10)) ** 2) if st.mean(diffs_c.values()) > -10 else None
out(f"**Potenza (calcolo, non misura).** Scarto tipico delle differenze di «funziona» C−B: {fmt(sd_c,1)} punti. "
    f"Se la differenza vera fosse quella osservata ({fmt(st.mean(diffs_c.values()),1,True)}), per avere il limite basso "
    f"sopra −10 servirebbero circa {n_need} compiti con l'approssimazione normale (con la t di Student circa 10: "
    "`TESI_master.md` §5.14).")
out()

# 3. dominanza
out("## 3. Chi domina chi, compito per compito")
out()
out("Un braccio domina un altro su un compito se costa meno e non funziona peggio.")
out()
for a, b in [("C", "B"), ("D", "B"), ("D", "C"), ("V", "B"), ("V", "C")]:
    dom = [t for t in TASKS if arm_cost(a, t) < arm_cost(b, t) and arm_fun(a, t) >= arm_fun(b, t)]
    out(f"- **{a} domina {b}** su {len(dom)}/5 compiti ({', '.join(dom) or 'nessuno'}).")
out()
wins = {a: collections.Counter() for a in ["C", "D"]}
for a in ["C", "D"]:
    for t in TASKS:
        df_ = fun(a, t) - fun("B", t)
        wins[a]["meglio" if df_ > 0 else "peggio" if df_ < 0 else "pari"] += 1
out(f"«Funziona» rispetto a B: C meglio/pari/peggio = {wins['C']['meglio']}/{wins['C']['pari']}/{wins['C']['peggio']}; "
    f"D = {wins['D']['meglio']}/{wins['D']['pari']}/{wins['D']['peggio']}.")
out()
svg_scatter(HERE / "costo_funziona.svg", "Costo e «funziona» per compito", "costo della run (dollari, scala log)",
            "funziona (0-100)",
            [(arm_cost(a, t), arm_fun(a, t), a, t) for a in ["B", "C", "D"] for t in TASKS],
            xlog=True, ylim=(50, 102), hline=(main["B"][1] - 10, "media B − τ (10 punti)"),
            means=[(main[a][0] / 5, main[a][1], a) for a in ["B", "C", "D", "V"]])
svg_scatter(HERE / "costo_piace.svg", "Costo e «piace» (voto del giudice contro B)", "costo della run (dollari, scala log)",
            "piace: voto medio dei due ordini",
            [(arm_cost(a, t), arm_piace(a, t), a, t) for a in ["C", "D"] for t in TASKS],
            xlog=True, ylim=(-2.2, 2.2), hline=(-1, "τ_piace = −1"),
            means=[(main[a][0] / 5, main[a][2], a) for a in ["B", "C", "D", "V"]])
svg_bars(HERE / "funziona_compito.svg", "«Funziona» per compito e braccio", TASKS, ARMS,
         {(a, t): fun(a, t) for a in ARMS for t in TASKS}, "punteggio 0-100", ymax=110)
svg_bars(HERE / "costo_compito.svg", "Costo per compito e braccio", TASKS, ARMS,
         {(a, t): cost(a, t) for a in ARMS for t in TASKS}, "dollari", fmtv=lambda v: f"{v:.2f}")

# 4. V
out("## 4. Cascata V (D → B)")
out()
acc = [t for t in TASKS if V[t]["accepted"]]
out(f"Il cancello accetta il sito di D su {len(acc)}/5 compiti (`a` = {fmt(len(acc)/5,1)}): V coincide con D "
    f"{'ovunque' if len(acc)==5 else 'su ' + ', '.join(acc)}. Costo V {fmt(main['V'][0])} $, funziona {fmt(main['V'][1],1)}, "
    f"piace {fmt(main['V'][2],2,True)}. **Il cancello (avvio, stato HTTP, errori JavaScript) non distingue i siti di D "
    "che funzionano peggio**: accetta anche D su 000040 (61 punti) e 000058 (80 punti).")
out()
out("C contro V (la domanda centrale di D55):")
cv = [fun("C", t) - V[t]["fun"] for t in TASKS]
cvlo, cvhi = boot(cv, lambda ix: st.mean(cv[i] for i in ix))
cc = [cost("C", t) for t in TASKS]; vc = [V[t]["cost"] for t in TASKS]
out(f"- funziona C − V: {fmt(st.mean(cv),1,True)} punti [{fmt(cvlo,1,True)}; {fmt(cvhi,1,True)}];")
out(f"- costo C / V: {fmt(sum(cc)/sum(vc),1)} volte;")
out(f"- piace: C {fmt(main['C'][2],2,True)}, V {fmt(main['V'][2],2,True)} (stesso riferimento B; C e V non giudicati direttamente).")
out(f"- In dollari: C spende {fmt(sum(cc)-sum(vc))} $ in piu' di V per {fmt(st.mean(cv),1,True)} punti medi di «funziona»: "
    f"{fmt((sum(cc)-sum(vc))/max(st.mean(cv),1e-9)/5,2)} $ per punto per compito.")
out()

# 5. costo scomposto
out("## 5. Dove vanno i soldi")
out()
tok = {a: collections.Counter() for a in ARMS}
for r in REC:
    for x in r["runs"]:
        for k, v in x["quantities"].items():
            tok[r["arm"]][k] += v
out("Token per braccio (somma sui 5 compiti):")
out()
out("| Braccio | ingresso | lettura cache | scrittura cache | uscita | quota di ingresso servita dalla cache |")
out("|---|---|---|---|---|---|")
for a in ARMS:
    q = tok[a]
    inp = q["input_tokens"] + q["cached_input_tokens"] + q["cache_write_tokens"]
    out(f"| {a} | {q['input_tokens']/1e6:.2f} M | {q['cached_input_tokens']/1e6:.2f} M | {q['cache_write_tokens']/1e6:.2f} M | {q['output_tokens']/1e6:.2f} M | {fmt(100*q['cached_input_tokens']/inp,1)}% |")
out()
# controfattuale cache e quota di uscita
for a in ARMS:
    actual = 0.0; nocache = 0.0; outc = 0.0
    for r in REC:
        if r["arm"] != a:
            continue
        for x in r["runs"]:
            # per modello: si ripartiscono i token con il costo per modello solo per i bracci a un modello
            pass
    # per B e D un solo modello: calcolo diretto
    if a in ("B", "D"):
        model = "opus-5-5" if a == "B" else "deepseek-v4-1-flash"
        pr = PRICES[model]; q = tok[a]
        actual = sum(q[k] * pr.get(k, 0) for k in q) / 1e6
        nocache = ((q["input_tokens"] + q["cached_input_tokens"] + q["cache_write_tokens"]) * pr["input_tokens"] + q["output_tokens"] * pr["output_tokens"]) / 1e6
        outc = q["output_tokens"] * pr["output_tokens"] / 1e6
        out(f"- **{a}**: costo dal listino {fmt(actual)} $ (registro {fmt(sum(cost(a,t) for t in TASKS))} $); senza cache "
            f"sarebbe {fmt(nocache)} $ (×{fmt(nocache/actual,1)}). L'uscita pesa il {fmt(100*outc/actual,0)}% del costo.")
        RESULTS[f"cache_{a}"] = (actual, nocache)
out()
# C per ruolo
out("Sciame C, costo per ruolo (dal registro `swarm.jsonl`: piano = Opus che pianifica, correzione = Opus che corregge "
    "il sito finale, worker economico = DeepSeek V4.1 Flash, worker = Kimi K3.1 Pro):")
out()
out("| Compito | piano $ | worker DeepSeek $ | worker Kimi $ | correzione $ | totale $ | quota Opus | pezzi | ondate | correzione partita |")
out("|---|---|---|---|---|---|---|---|---|---|")
role_tot = collections.Counter()
stack_rows = []
for t in TASKS:
    sw = BY[("C", t)]["swarm"]
    plan_ids = set(sw["plan_agents"])
    parts = collections.Counter()
    for agent, v in sw["breakdown"].items():
        if agent in plan_ids:
            parts["piano (Opus)"] += v["cost"]
        elif agent.startswith("planner"):
            parts["correzione (Opus)"] += v["cost"]
        elif agent.startswith("worker_cheap"):
            parts["worker DeepSeek"] += v["cost"]
        else:
            parts["worker Kimi"] += v["cost"]
    role_tot.update(parts)
    total = sum(parts.values())
    opus = parts["piano (Opus)"] + parts["correzione (Opus)"]
    stack_rows.append((t, dict(parts)))
    out(f"| {t} | {fmt(parts['piano (Opus)'])} | {fmt(parts['worker DeepSeek'])} | {fmt(parts['worker Kimi'])} | {fmt(parts['correzione (Opus)'])} | "
        f"{fmt(total)} | {fmt(100*opus/total,0)}% | {len(sw['pieces'])} | {sw['waves']} | {'si' if sw['escalated'] else 'no'} |")
tot_c = sum(role_tot.values())
out(f"| **totale** | {fmt(role_tot['piano (Opus)'])} | {fmt(role_tot['worker DeepSeek'])} | {fmt(role_tot['worker Kimi'])} | {fmt(role_tot['correzione (Opus)'])} | {fmt(tot_c)} | "
    f"{fmt(100*(role_tot['piano (Opus)']+role_tot['correzione (Opus)'])/tot_c,0)}% | | | |")
out()
RESULTS["c_roles"] = dict(role_tot)
out(f"**Lettura.** I worker DeepSeek fanno quasi tutto il codice ma costano {fmt(100*role_tot['worker DeepSeek']/tot_c,0)}% della spesa di C; "
    f"Opus (piano e correzione) pesa {fmt(100*(role_tot['piano (Opus)']+role_tot['correzione (Opus)'])/tot_c,0)}%; "
    f"i due pezzi affidati a Kimi (000040 `ui-cart`, 842 `operation-replay`) da soli costano {fmt(role_tot['worker Kimi'])} $ "
    f"({fmt(100*role_tot['worker Kimi']/tot_c,0)}%). La correzione di Opus, quando parte, e' la voce piu' cara della run "
    "(000040: 1,05 $ su 2,76). Il risparmio di C su B viene quindi da quanto poco scrive Opus, non da quanto lavorano i worker.")
out()
svg_stack(HERE / "costo_sciame.svg", "Sciame C: costo per ruolo e compito", stack_rows,
          ["piano (Opus)", "worker DeepSeek", "worker Kimi", "correzione (Opus)"],
          {"piano (Opus)": "#c8553d", "worker DeepSeek": "#5b8c5a", "worker Kimi": "#d9a441", "correzione (Opus)": "#7a2e22"},
          "dollari")
pieces = [p for t in TASKS for p in BY[("C", t)]["swarm"]["pieces"]]
pst = collections.Counter(p["status"] for p in pieces)
pmod = collections.Counter(p["model"] for p in pieces)
out(f"**Pezzi dello sciame.** {len(pieces)} pezzi in tutto (media {fmt(len(pieces)/5,1)} a compito); modelli scelti dal planner: "
    + ", ".join(f"{m} {n}" for m, n in pmod.most_common()) + "; esito: " + ", ".join(f"{s} {n}" for s, n in pst.most_common()) + ". "
    "Su 000098 lo scheletro termina con il sito non avviabile (`service_unavailable`) e gli altri 9 pezzi vengono saltati: "
    "il sito consegnato e' quello dello scheletro: anche la correzione di Opus (0,08 $) si interrompe dopo aver caricato le skill, senza scrivere file. Questa run e' attraversata dallo stop notturno del Mac (regola «Guasti della macchina»: arrivata alla fine, conta com'e'): su 000098 C e' di fatto «piano di Opus + scheletro DeepSeek», non uno sciame, e va dichiarato. Lo scheletro fermato dal limite di "
    "80 iterazioni (000040, 000058) e' il pezzo che fa partire la correzione: su quei due compiti C ha speso 1,05 e 0,29 $ in correzione.")
out()

# 6. tempo
out("## 6. Tempo")
out()
out("Tempo dall'avvio alla consegna (solo le run non attraversate dallo stop del Mac) e tempo di attesa del modello "
    "(somma delle latenze delle chiamate, valido per tutte):")
out()
out("| Braccio | " + " | ".join(TASKS) + " | mediana del tempo valido |")
out("|---|" + "---|" * (len(TASKS) + 1))
for a in ARMS:
    cells = []
    valid = []
    for t in TASKS:
        r = BY[(a, t)]
        lat = sum(x["latency_sum_s"] for x in r["runs"]) / 60
        if (a, t) in WALL_INVALID:
            cells.append(f"(stop) · modello {fmt(lat,0)} min")
        else:
            cells.append(f"{fmt(r['wall_s']/60,0)} min · modello {fmt(lat,0)} min")
            valid.append(r["wall_s"] / 60)
    out(f"| {a} | " + " | ".join(cells) + f" | {fmt(st.median(valid),0)} min |")
out()
par = []
for t in TASKS:
    if ("C", t) in WALL_INVALID:
        continue
    r = BY[("C", t)]
    par.append(sum(x["latency_sum_s"] for x in r["runs"]) / r["wall_s"])
out(f"Per C il tempo di modello supera quello reale: le ondate lavorano in parallelo (fattore medio {fmt(st.mean(par),1)}×, "
    "somma delle latenze / tempo reale). **C e' piu' lento di B** di un fattore 2-5 sul tempo reale: costa meno ma consegna dopo.")
out()

# 7. iterazioni, chiamate, D al limite
out("## 7. Iterazioni, chiamate e lavoro dopo la consegna")
out()
calls = {a: [sum(x["calls"] for x in BY[(a, t)]["runs"]) for t in TASKS] for a in ARMS}
out("Chiamate al modello per run: " + "; ".join(f"{a} {', '.join(map(str, calls[a]))} (media {fmt(st.mean(calls[a]),0)})" for a in ARMS) + ".")
out()
out("B chiude sempre da solo (`stop`) dopo 26-42 iterazioni; D arriva sempre al limite di 80 (`max_iterations`). "
    "Quanto spende D dopo l'ultima scrittura di un file (stima: ogni chiamata dichiara quanti strumenti chiede, e cosi' si "
    "attribuisce l'ultima `write_file` alla sua chiamata):")
out()
out("| Compito | ultima write_file alla chiamata | chiamate dopo | costo dopo $ | quota della run |")
out("|---|---|---|---|---|")
waste = []
for t in TASKS:
    x = BY[("D", t)]["runs"][0]
    seq = x["tool_sequence"]
    last_write = max((i for i, tool in enumerate(seq) if tool in ("write_file", "edit_file")), default=None)
    cum, idx = 0, None
    for ci, n in enumerate(x["n_tool_calls_per_call"]):
        cum += n
        if last_write is not None and cum > last_write and idx is None:
            idx = ci
    after = x["call_costs"][idx + 1:] if idx is not None else []
    waste.append(sum(after) / x["cost"])
    out(f"| {t} | {idx+1 if idx is not None else 'n.d.'} di {x['calls']} | {len(after)} | {fmt(sum(after),3)} | {fmt(100*sum(after)/x['cost'],0)}% |")
out()
out(f"In media il {fmt(100*st.mean(waste),0)}% della spesa di D cade dopo l'ultima modifica ai file (controlli ripetuti, "
    "letture, `view_site`): e' il problema aperto «l'agente si ferma solo quando il modello chiude da se'». "
    "Costa pochi centesimi, ma con un modello caro sarebbe rilevante.")
out()

# 8. strumenti
out("## 8. Strumenti usati")
out()
tools_by_arm = {a: collections.Counter() for a in ARMS}
errs_by_arm = {a: collections.Counter() for a in ARMS}
views = {a: 0 for a in ARMS}
skills_ok = {a: 0 for a in ARMS}
agents = {a: 0 for a in ARMS}
for r in REC:
    for x in r["runs"]:
        tools_by_arm[r["arm"]].update(x["tools"])
        errs_by_arm[r["arm"]].update(x["tool_errors"])
        views[r["arm"]] += x["view_site_shots"]
        agents[r["arm"]] += 1
        if x["skills"]:
            skills_ok[r["arm"]] += 1
names = sorted({k for c in tools_by_arm.values() for k in c})
out("| Strumento | " + " | ".join(ARMS) + " |")
out("|---|" + "---|" * len(ARMS))
for n in names:
    out(f"| `{n}` | " + " | ".join(f"{tools_by_arm[a][n]} ({errs_by_arm[a][n]} err.)" for a in ARMS) + " |")
out(f"| agenti (run) | " + " | ".join(str(agents[a]) for a in ARMS) + " |")
out(f"| agenti che hanno caricato skill | " + " | ".join(f"{skills_ok[a]}/{agents[a]}" for a in ARMS) + " |")
out()
tot_calls = {a: sum(tools_by_arm[a].values()) for a in ARMS}
tot_err = {a: sum(errs_by_arm[a].values()) for a in ARMS}
out("Quota di chiamate a strumenti finite in errore: " + ", ".join(f"{a} {fmt(100*tot_err[a]/tot_calls[a],1)}%" for a in ARMS) +
    ". Auto-verifica visiva (`view_site`) per compito: " + ", ".join(f"{a} {fmt(views[a]/5,1)}" for a in ARMS) + ".")
out()
rf_err = sum(errs_by_arm[a]["read_file"] for a in ARMS); rf_tot = sum(tools_by_arm[a]["read_file"] for a in ARMS)
out(f"**Limite dell'harness trovato nei registri.** {rf_err} chiamate a `read_file` su {rf_tot} falliscono: quasi tutte sono "
    "tentativi di aprire come testo i PNG degli screenshot che l'agente si e' fatto con Playwright (`UnicodeDecodeError`), "
    "o file delle skill fuori dal workspace. Gli agenti vogliono guardare le proprie immagini: `read_file` non lo permette, "
    "`view_site` si'. Lavoro futuro: un `read_file` che restituisca le immagini al modello.")
out()
skill_counts = collections.Counter(s for r in REC for x in r["runs"] for s in x["skills"])
out("Skill caricate (volte): " + ", ".join(f"`{s}` {n}" for s, n in skill_counts.most_common()) + ".")
out()

# 9. passi della valutazione
out("## 9. «Funziona» passo per passo")
out()
by_type = {a: collections.Counter() for a in ARMS}
fails = []
for r in REC:
    for s in r["steps"]:
        by_type[r["arm"]][(s["tipo"], s["stato"])] += 1
        if s["stato"] != "superato":
            fails.append((r["arm"], r["task"], s["id"], s["tipo"], s["motivo"]))
types = sorted({k[0] for c in by_type.values() for k in c})
out("| Braccio | " + " | ".join(f"{t}: superati/totali" for t in types) + " |")
out("|---|" + "---|" * len(types))
for a in ARMS:
    cells = []
    for t in types:
        tot = sum(v for k, v in by_type[a].items() if k[0] == t)
        ok = by_type[a][(t, "superato")]
        cells.append(f"{ok}/{tot} ({fmt(100*ok/tot,0) if tot else 'n.d.'}%)")
    out(f"| {a} | " + " | ".join(cells) + " |")
out()


def cause(m):
    low = m.lower()
    if "dipende dal passo" in low:
        return "conseguenza di un passo precedente fallito"
    if any(w in low for w in ("sfondo", "cadet blue", "dark orange", "saddle brown", "light cyan", "beige", "rgb(")):
        return "colore imposto non rispettato"
    if "timeout" in low and "get_by_test_id" in low:
        return "elemento atteso non trovato (data-testid mancante o nascosto)"
    if "cambia" in low or "->" in m:
        return "l'interfaccia non reagisce all'azione"
    if any(w in low for w in ("esattamente", "contiene", "nessuna sessione", "una sola", "ha ")):
        return "dati o stato sbagliati dopo l'azione"
    if re.search(r"\b[45]\d\d\b|stato", low):
        return "rotta: stato HTTP inatteso"
    return "altro"


out("Passi non superati e causa (classificata dal messaggio dello script):")
out()
out("| Braccio | Compito | Passo | Tipo | Causa |")
out("|---|---|---|---|---|")
for a, t, sid, tp, m in fails:
    out(f"| {a} | {t} | {sid} | {tp} | {cause(m)} |")
out()
cause_count = {a: collections.Counter(cause(m).split(":")[0] for b, _, _, _, m in fails if b == a) for a in ARMS}
out("Per braccio: " + "; ".join(f"{a}: " + (", ".join(f"{c} {n}" for c, n in cause_count[a].most_common()) or "nessuno") for a in ARMS) + ".")
out()

# 10. controlli automatici
out("## 10. Controlli automatici alle tre larghezze")
out()
out("| Braccio | violazioni a11y (somma) | errori JavaScript | larghezze con overflow |")
out("|---|---|---|---|")
for a in ARMS:
    a11y = sum(w["a11y"] for t in TASKS for w in BY[(a, t)]["widths"].values())
    er = sum(w["errors"] for t in TASKS for w in BY[(a, t)]["widths"].values())
    ov = sum(1 for t in TASKS for w in BY[(a, t)]["widths"].values() if w["overflow"])
    out(f"| {a} | {a11y} | {er} | {ov}/15 |")
out()

# 11. codice
out("## 11. Il codice dei siti")
out()
out("Righe di codice scritte (esclusi `node_modules`, `dist`, dati e test), file, dipendenze, dimensione della build:")
out()
out("| Braccio | righe (media) | file (media) | componenti JSX (media) | dipendenze (media) | build JS kB (media) | `data-testid` (media) | file di test (somma) |")
out("|---|---|---|---|---|---|---|---|")
code_stats = {}
for a in ARMS:
    cs = [BY[(a, t)]["code"] for t in TASKS]
    code_stats[a] = cs
    out(f"| {a} | {fmt(st.mean(c['lines'] for c in cs),0)} | {fmt(st.mean(c['files'] for c in cs),0)} | {fmt(st.mean(c['components'] for c in cs),0)} | "
        f"{fmt(st.mean(len(c['dependencies']) for c in cs),1)} | {fmt(st.mean(c['dist_js_bytes'] for c in cs)/1000,0)} | "
        f"{fmt(st.mean(c['data_testid'] for c in cs),0)} | {sum(c['test_files'] for c in cs)} |")
out()
deps = collections.Counter(d for r in REC for d in r["code"]["dependencies"])
out("Dipendenze piu' usate: " + ", ".join(f"`{d}` {n}/15" for d, n in deps.most_common(10)) + ".")
out()
out("Costo per mille righe consegnate: " + ", ".join(
    f"{a} {fmt(1000*sum(cost(a,t) for t in TASKS)/sum(c['lines'] for c in code_stats[a]),3)} $" for a in ARMS) +
    ". Righe per dollaro: " + ", ".join(f"{a} {fmt(sum(c['lines'] for c in code_stats[a])/sum(cost(a,t) for t in TASKS),0)}" for a in ARMS) + ".")
out()
out("Piu' righe non vuol dire meglio: D scrive in media piu' codice di B e funziona peggio. B e' l'unico braccio che scrive "
    "file di test propri con regolarita'.")
out()

# 12. colori richiesti
out("## 12. Rispetto dei colori imposti dal compito (dagli screenshot a 1440 px)")
out()
out("Tre compiti impongono sfondo e colore dei componenti. Quota dei pixel dello screenshot vicini al colore richiesto "
    "(distanza RGB ≤ 12 per lo sfondo, ≤ 40 per i componenti; immagine ridotta a 240 px):")
out()
out("| Compito | colore | B | C | D |")
out("|---|---|---|---|---|")
color_res = {}
for t, (bgn, bg, cn, cc_) in REQUIRED.items():
    row_bg, row_c = [], []
    for a in ARMS:
        px = pixels(Path(BY[(a, t)]["screenshots"]["1440"]))
        fb = sum(near(p, bg, 12) for p in px) / len(px)
        fc = sum(near(p, cc_, 40) for p in px) / len(px)
        color_res[(a, t)] = (fb, fc)
        row_bg.append(f"{fmt(100*fb,0)}%")
        row_c.append(f"{fmt(100*fc,1)}%")
    out(f"| {t} | sfondo {bgn} | " + " | ".join(row_bg) + " |")
    out(f"| {t} | componenti {cn} | " + " | ".join(row_c) + " |")
out()
out("Misura grezza: dice se il colore c'e' e quanto, non se e' usato bene. Utile per vedere chi segue alla lettera "
    "l'istruzione e chi la reinterpreta (es. sfondo con una sfumatura vicina).")
out()

# 13. giudice
out("## 13. Il giudice")
out()
js = D["judgments"]
opp = sum(1 for j in js if j["forward"] is not None and j["backward"] is not None and (j["forward"] * j["backward"] < 0))
same = sum(1 for j in js if j["forward"] == j["backward"] and j["forward"] != 0)
zero = sum(1 for j in js if j["forward"] == 0 or j["backward"] == 0)
out(f"20 chiamate, 10 coppie, 0 non valutabili, 0 tempi scaduti, {sum(j['seconds'] for j in js):.0f} s, "
    f"{sum(j['usage'].get('input_tokens',0) for j in js)/1000:.0f}k token d'ingresso. Ordini opposti come atteso in {opp}/10; "
    f"stessa posizione preferita in entrambi gli ordini in {same}/10 (D-B/842); un voto 0 in {zero}/10. "
    "In calibrazione (R1.9) gli ordini opposti erano 124/150 (83%), qui 90%.")
first = sum(1 for j in js for v in (j["forward"], j["backward"]) if v is not None and v < 0)
second = sum(1 for j in js for v in (j["forward"], j["backward"]) if v is not None and v > 0)
out(f"Preferenza per posizione sui 20 voti: prima proposta {first}, seconda {second}, pari {20-first-second}.")
out()
mag = collections.Counter(abs(v) for j in js for v in (j["forward"], j["backward"]) if v is not None)
out("Forza dei voti (valore assoluto): " + ", ".join(f"{k}: {n}" for k, n in sorted(mag.items())) + ". Il giudice usa "
    "spesso il gradino estremo (2), segno che vede differenze nette fra i siti.")
out()
# accordo giudice - funziona
agree = []
for a in ["C", "D"]:
    for t in TASKS:
        dfun = fun(a, t) - fun("B", t)
        p = piace(a, t)
        if p is None:
            continue
        agree.append((a, t, dfun, p))
same_sign = sum(1 for _, _, dfu, p in agree if dfu * p > 0)
conflict = [(a, t, dfu, p) for a, t, dfu, p in agree if dfu * p < 0]
neutral = len(agree) - same_sign - len(conflict)
out(f"«Piace» e «funziona» vanno nella stessa direzione in {same_sign}/10 coppie, in direzioni opposte in {len(conflict)} "
    + ("(" + "; ".join(f"{a}-B/{t}: funziona {fmt(dfu,1,True)}, piace {fmt(p,1,True)}" for a, t, dfu, p in conflict) + ")" if conflict else "")
    + f", e in {neutral} una delle due e' pari. Le due metriche misurano cose diverse: il giudice vede solo immagini statiche.")
out()

# 14. spesa vera
out("## 14. Quanto e' costato davvero l'esperimento")
out()
by_c = collections.Counter()
valid_cost = sum(cost(a, t) for a in ARMS for t in TASKS)
for r in D["all_rows"]:
    by_c[r["campaign"]] += r["cost"]
total_all = sum(by_c.values())
out(f"Righe delle campagne `mvp-*`: {len(D['all_rows'])}, di cui 15 valide. Spesa registrata di tutte le righe: "
    f"{fmt(total_all)} $; delle valide {fmt(valid_cost)} $; persa per guasti, ripetizioni e piani falliti: "
    f"{fmt(total_all-valid_cost)} $ ({fmt(100*(total_all-valid_cost)/total_all,0)}%).")
out()
out("| Campagna | spesa $ | righe | esiti |")
out("|---|---|---|---|")
for cpg in sorted(by_c):
    rows = [r for r in D["all_rows"] if r["campaign"] == cpg]
    out(f"| {cpg} | {fmt(by_c[cpg])} | {len(rows)} | " + ", ".join(f"{r['task']} {r['status']}" for r in rows) + " |")
out()
out("Una run di C esclusa per guasto (`mvp-C-r`, 000098, codice vecchio) si era chiusa con il sito non avviabile a 375 px "
    "(funziona 8,3): non entra nei dati, ma ricorda che una sola esecuzione per compito nasconde la variabilita'.")
out()

# 15. auto-dichiarazione
out("## 15. Quello che l'agente dichiara e quello che si misura")
out()
claims = []
for r in REC:
    msg = " ".join(x["final_message"] for x in r["runs"] if x["final_message"])
    every = bool(re.search(r"(pass(ed|es)? (every|all)|all (checks|tests) pass|every check|everything checked out|0 failures)", msg, re.I))
    claims.append((r["arm"], r["task"], every, r["funziona"]))
out("Run il cui messaggio finale dichiara che tutti i controlli dell'agente sono passati, con il «funziona» misurato:")
out()
for a, t, every, f in claims:
    if every:
        out(f"- {a} {t}: dichiara tutto superato, misura {fmt(f,1)}")
out()
over = [c for c in claims if c[2] and c[3] < 100]
out(f"D non scrive mai un messaggio finale: si ferma sempre al limite di iterazioni. B 000040 si ferma alla rete di 5 $ senza messaggio.")
out()
out(f"In {len(over)} casi l'agente dichiara di aver superato tutti i propri controlli e la valutazione nascosta trova passi falliti: "
    "i test che l'agente si scrive non coprono i passi del compito. E' l'argomento per tenere la valutazione invisibile ai bracci (R1).")
out()

# 16. aspetto
out("## 16. Aspetto dei siti (dagli screenshot e dai workspace)")
out()


def dims(png):
    o = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(png)], capture_output=True, text=True).stdout.split()
    return int(o[-3]), int(o[-1])


look = {}
for r in REC:
    w, h = dims(r["screenshots"]["1440"])
    px = pixels(Path(r["screenshots"]["1440"]), 120)
    lum = st.mean(0.2126 * a + 0.7152 * b + 0.0722 * c for a, b, c in px) / 255
    ws = Path(r["workspace"])
    photos = [f for f in ws.rglob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".webp")
              and not any(x in f.parts for x in ("node_modules", "dist", ".shots", ".tests", ".taste-skill"))]
    credit = any("wikimedia" in f.read_text(errors="replace").lower() for f in (ws / "src").rglob("*") if f.is_file()) if (ws / "src").exists() else False
    look[(r["arm"], r["task"])] = {"h": h, "lum": lum, "photos": len(photos), "credit": credit}
out("| Compito | Braccio | altezza pagina px | luminosita' media | tema | foto nel sito | crediti Wikimedia |")
out("|---|---|---|---|---|---|---|")
for t in TASKS:
    for a in ARMS:
        l = look[(a, t)]
        out(f"| {t} | {a} | {l['h']}{' (taglio)' if l['h'] >= 4000 else ''} | {fmt(l['lum'],2)} | {'scuro' if l['lum'] < 0.45 else 'chiaro'} | {l['photos']} | {'si' if l['credit'] else 'no'} |")
out()
cut = [f"{a} {t}" for (a, t), l in look.items() if l["h"] >= 4000]
out(f"Gli screenshot sono tagliati a 4000 px di altezza (`docker/render_site.py`): a 1440 px sono al limite {', '.join(cut)}; "
    "contando tutte e tre le larghezze le immagini al limite sono 12 su 45 (`TESI_master.md` §5.14). Su C 000058 il "
    "giudice non vede la sezione degli obiettivi, che sta sotto il taglio.")
out()
photo_sites = [f"{a} {t}" for (a, t), l in look.items() if l["photos"]]
out(f"Siti con foto vere scaricate dalla rete (rete `bridge`) e crediti di licenza scritti nella pagina: {', '.join(photo_sites) or 'nessuno'}. "
    "Nessun braccio ha uno strumento per generare immagini (R2.1b, lavoro futuro): chi vuole immagini le cerca su Wikimedia Commons "
    "e cita autore e licenza.")
out()
# bias di quantita'
rows = []
for a in ["C", "D"]:
    for t in TASKS:
        rows.append((look[(a, t)]["h"] - look[("B", t)]["h"], piace(a, t)))
xs = [x for x, _ in rows]; ys = [y for _, y in rows]
mx, my = st.mean(xs), st.mean(ys)
cov = sum((x - mx) * (y - my) for x, y in rows)
r_ = cov / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
out(f"**Bias di quantita' (R1.9).** Correlazione fra differenza di altezza della pagina (braccio − B) e voto del giudice "
    f"sulle 10 coppie: r = {fmt(r_,2,True)}. Con 10 coppie non si vede una preferenza per le pagine piu' lunghe.")
out()
out("**Pagine diverse sotto la stessa rotta.** Lo screenshot e' sempre quello di `/` dopo la «vetrina» (dati d'esempio). "
    "Su 000040 la pagina `/` di D e' il carrello (`renderPage` in `src/App.jsx` del suo workspace restituisce `<Review />` per `/`) "
    "e quella di B mostra la pagina del podcast (causa non chiarita); il giudice confronta quindi pagine non omologhe. "
    "I voti di 000040 (C-B +1,5, D-B +1,0) vanno letti con questa riserva.")
out()

FIGURES.mkdir(parents=True, exist_ok=True)
for svg in HERE.glob("*.svg"):
    (FIGURES / svg.name).write_text(svg.read_text(encoding="utf-8"), encoding="utf-8")
(HERE / "rapporto.md").write_text("\n".join(OUT_LINES) + "\n", encoding="utf-8")
(HERE / "risultati.json").write_text(json.dumps({k: (v if not isinstance(v, tuple) else list(v)) for k, v in RESULTS.items()},
                                                indent=1, default=str), encoding="utf-8")
print("\n".join(OUT_LINES))
