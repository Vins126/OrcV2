# ORC — Memoria completa della tesi (documento master)

> **Cos'è:** il dump definitivo di tutto ciò che abbiamo capito sulla tesi — fatti, scelte di
> design, stato dell'arte e **collegamenti profondi** ricavati ragionando. Companion tecnico:
> `M2_routing_design.md` (diagrammi dettagliati). Aggiornato: giugno 2026.

---

## 0. La tesi in una frase (e come ottimizzazione)

> *Un **sistema multi-agente** che affida il lavoro a **modelli economici** e decide quando passare al modello forte
> **verificando il sito eseguito**, invece di prevederlo, ottiene una **riduzione di costo significativa** **a parità
> di qualità** rispetto a una **baseline mono-modello** (Opus 5.5), nella **generazione di siti web**; e la tesi
> misura **quanto del risparmio spiega ciascuna leva** rispetto a politiche più semplici con gli stessi modelli.*

Formulazione del 23 ottobre 2026 (D48, D49). Quella precedente diceva «sistema multi-agente con **cost-routing**»:
il routing che prevede in anticipo il modello sufficiente esce dal piano (§3, motivi in D48).

Formulata come problema: **minimizza il costo, soggetto a qualità ≥ soglia τ.**
```
   min  Σ costo(modello_i)        s.t.   qualità(output) ≥ τ
```
Questa singola funzione obiettivo **unifica tutto il sistema**:
- il **cancello eseguibile** (avvio, errori, test propri dell'agente: controlli gratuiti) dice se il lavoro
  dell'economico regge;
- l'**escalation** passa al forte solo quando il cancello o il critico lo rifiutano;
- la **decomposizione** abbassa il costo necessario per raggiungere τ;
- la **valutazione** è ciò che *definisce e misura* τ, ed è separata dal cancello: il cancello non vede mai gli
  script né le domande del giudice.
Senza la metà "qualità ≥ τ", "minimizza il costo" è banale (scegli sempre il più scadente).

> **Revisione del 23 ottobre 2026 (D48-D50).** Un'analisi dei router già pronti (Switchyard, NadirClaw, Conduit,
> RouteLLM, Not Diamond, Arch-Router, RouteFM, router di OpenRouter; §7.3) ha cambiato due cose. (1) **Meccanismo
> (D48):** sul codice prevedere quale modello basta rende poco, verificare il risultato rende; il renderer di R1
> diventa anche il cancello del sistema. (2) **Confronto (D49):** oltre a B, C e D si misurano due politiche
> semplici che sono le obiezioni più prevedibili allo sciame, la cascata **V** (D, poi B se il cancello rifiuta) e
> **Plan/Execute H** (Opus pianifica, l'economico esegue). La prova principale resta C contro B; le altre politiche
> stanno sul piano costo-qualità con il loro intervallo. La tesi regge così qualunque esito: se vince una politica
> semplice, il risultato è *quale* leva basta. Superati di conseguenza §2.2 (flywheel), la parte OFFLINE di §6 e la
> decisione di §3; il loro testo resta come storia.

> **Riprogettazione del 18 ottobre 2026 (D35-D44, `PIANO_completo.md` §10).** Il terreno sperimentale sono i siti web
> (D35, conferma D16). Il contributo non è più il solo router appreso (D13, sostituita): è **il sistema** e **la
> scomposizione misurata del risparmio** fra le leve (scomposizione in sezioni, modelli economici con verifica,
> strumenti di design, ottimizzazione dell'harness), con un confronto equo in cui Opus 5.5 riceve gli stessi strumenti
> (D36, D39). La valutazione resta co-centrale, a tre livelli e verificata con voti umani (D41). Il router appreso
> diventa facoltativo. La condizione di convenienza `m / r + q < 1` è dichiarata prima delle misure (D37).
> Da riscrivere di conseguenza: §1 (gerarchia dei pilastri), §3 (routing), §7 (posizionamento: AgentCARD, AgentRouter,
> STORM, CAID, Kim et al., WebGen-Agent, WebDevJudge).

### 0.1 Quando lo sciame conviene (ipotesi dichiarata prima delle misure, D37)

Scritta il 21 ottobre 2026, prima di qualunque esecuzione della campagna, perché la misura possa smentirla.

Sia `C_B` il costo di un sito fatto da Opus 5.5 da solo con gli strumenti (braccio B). Lo sciame (braccio C)
spende in due modi:
- le **foglie** (worker economici) consumano `m` volte i token che consumerebbe il singolo forte, pagati a un prezzo
  `r` volte più basso: costano `(m / r) · C_B`;
- il **planner** e le **escalation** a Opus costano una quota `q` del singolo: `q · C_B`.

Quindi `C_C = (m / r + q) · C_B`, e lo sciame costa meno del singolo se e solo se

```
   m / r + q < 1
```

Dove:
- `m` = token delle foglie rispetto al singolo forte. A parità di modello un sistema multi-agente consuma da 1,5 a
  4,4 volte l'agente singolo (letteratura, `ROADMAP.md` R0): ci si aspetta `m` in quell'intervallo;
- `r` = rapporto di prezzo fra Opus 5.5 e il modello economico, **pesato sulla miscela reale** di input, input da
  cache e output. Con i listini del 21 ottobre 2026 (Opus 5.5 4 / 20 $/M, lettura da cache 0,20; DeepSeek V4.1
  Flash 0,15 / 0,60, cache 0,003) il rapporto vale circa 27 sull'input, 33 sull'output, 67 sulla cache;
- `q` = quota di planner ed escalation sul costo del singolo.

**Previsione.** Con `m ≤ 4,4` e `r ≈ 30`, il termine delle foglie vale al massimo circa 0,15: il risparmio dipende
quasi solo da `q`. Lo sciame conviene finché planner ed escalation restano sotto circa l'85% del costo del singolo;
la voce che può smentire l'ipotesi è la **frequenza delle escalation**, non il prezzo delle foglie.

**Come si presenta il risultato.** I prezzi cambiano ogni mese: il risparmio si riporta **in funzione di `r`**,
con i valori di `m` e `q` misurati nella campagna, così il lettore può ricalcolarlo con i listini del momento. La
condizione riguarda solo il costo: la qualità si giudica a parte, con le regole di `PROTOCOLLO.md`.

### 0.2 Quando conviene una politica più semplice (ipotesi dichiarata prima delle misure, D49)

Scritta il 23 ottobre 2026, prima di qualunque esecuzione, con la stessa notazione di §0.1. Sono calcoli su
ipotesi, non misure: il pilota di R2 (D50) dà i primi valori.

**Cascata V (prima D, poi B se il cancello rifiuta).** Sia `c_D = m_D / r` il costo del sito di D rispetto a
quello di B (`m_D` = token di D rispetto a B) e `a` la quota di compiti in cui il sito di D supera il cancello.
B ricomincia da zero, quindi

```
   C_V / C_B = c_D + (1 − a)        conviene se  a > c_D
```

Con `r ≈ 30` e `m_D ≤ 4,4`, `c_D ≤ 0,15`: V costa meno di B appena D supera il cancello in più del 15% dei
compiti. Per esempio `a = 0,5` dà `C_V / C_B` fra 0,53 e 0,65. Il rischio di V non è il costo ma la qualità: il
cancello vede l'avvio, gli errori e i test propri, non l'aspetto, quindi può accettare un sito che funziona e non
piace. Lo misura la coppia D-B nei compiti in cui il cancello ha accettato.

**Plan/Execute H.** Sia `q_H` la quota di spesa di Opus fino alla prima scrittura di un file e `m_H` i token
dell'economico dopo il passaggio: `C_H / C_B = q_H + m_H / r`. Riferimento pubblicato: su DeepSWE v1.1 il
Plan/Execute di Switchyard costa $180,51 contro $720,95 del forte da solo. Se la parte economica non costa più di
una run intera dell'economico da solo ($50,02), la parte forte vale almeno $130,49, cioè `q_H ≥ 0,18` (calcolo
con quell'ipotesi). **Previsione per i siti:** chi costruisce un sito scrive il primo file presto, quindi il
passaggio arriva presto, `q_H` resta basso e la qualità di H si avvicina a quella di D («D con un piano di Opus»).
Se è così, H è un riferimento e il rivale vero di C è V.

**Lo sciame contro la cascata.** Confrontando §0.1 con V, C costa meno di V se `m / r + q < c_D + (1 − a)`. Con i
termini delle foglie piccoli, in prima approssimazione:

```
   q < 1 − a
```

Cioè la spesa di Opus nello sciame (planner più escalation) deve restare sotto la quota di compiti in cui
l'economico da solo non passa il cancello. Sulla qualità, C deve fare meglio di V proprio dove V accetta il sito di
D: è lì che scomposizione e critico devono valere qualcosa. Il risultato si riporta, come in §0.1, in funzione di
`r`, con `a`, `q`, `q_H`, `m` misurati.

---

## 1. Le parti fondamentali (gerarchia)

```
            ┌──────────────── LA TESI ────────────────┐
   PILASTRI │ 1.Economici + verifica eseguibile  2.Valutazione  3.Validazione │
   CO-CENTR.│        (stanno o cadono INSIEME)                            │
            └──────────────────────────────────────────────────────────┘
  SUBSTRATO │ 4.Architettura multi-agente  5.Decomposizione              │
            │ 6.Coordinamento/Blackboard   7.Resilienza (Pilastro C)     │
  SUPPORTI  │ 8.Sicurezza/isolamento  9.Contesto/RAG  10.Osservabilità   │
```
- **Modelli economici con verifica eseguibile** (fino al 22 ottobre 2026: «cost-routing»): il lavoro va
  all'economico, un cancello gratuito che esegue il sito decide se tenerlo o passare al forte (D48). È il "come" del
  risparmio.
- **Valutazione**: il "*a parità di qualità*" — co-centrale, la più difficile, dove il professore spingerà. Usa lo
  stesso renderer del cancello, ma con script e domande che il sistema non vede mai.
- **Validazione**: baseline vs sistema, variabili controllate → rende il lavoro **scienza**. Dal 23 ottobre 2026
  comprende la **scala di politiche** B, D, V, H, C (D49): il sistema si confronta anche con le alternative più
  semplici, non solo col forte da solo.
- L'errore classico: innamorarsi del meccanismo di scelta del modello e sotto-costruire la valutazione → claim
  infalsificabile.

---

## 2. ⭐ I COLLEGAMENTI PROFONDI (le intuizioni chiave)

### 2.1 Il giudizio di qualità è la SPINA DORSALE (non un pilastro a latere)
Lo stesso pattern "valuta qualità → agisci" riappare a **ogni scala** del sistema:
| Livello | Segnale di qualità | Azione |
|---|---|---|
| micro (Pilastro C) | l'errore/output di un tool è ok? | auto-correzione |
| task (cascade) | l'output del worker regge τ? | accetta o escala modello |
| routing (reward model) | quale modello dà più qualità/€? | scegli il modello |
| training frontier (RLHF) | quale risposta preferiscono gli umani? | aggiorna i pesi |
→ **Il "giudice" è la spina su cui tutto è appeso.** La tesi è, in fondo, *operazionalizzare un
segnale di qualità per il software open-ended* e usarlo per guidare routing/escalation/correzione.

### 2.2 Il FLYWHEEL: cascade → dati → router → cascade più economica

> **Superata il 23 ottobre 2026 (D48).** Il flywheel serve ad addestrare un router predittivo, che esce dal piano:
> con 5 compiti di sviluppo non c'è niente da imparare, e sul codice la previsione rende poco. Resta come lavoro
> futuro (§3). La parte che sopravvive è la cascata stessa, ora con un cancello eseguibile (§0, §0.2).

```
   cascade (cheap-first, escala) ──► log (task, modello, qualità, costo)
        ▲                                     │
        │ router riduce il costo              ▼
   DPO/reward model ◄────────────── dataset di preferenza
```
Il sistema **si auto-migliora**: più gira, più dati, miglior router, cascade più economica.
E **risponde all'obsolescenza**: quando esce un modello nuovo, ri-esegui la cascade sui nuovi
candidati → nuovi dati → ri-train. Il flywheel **è** la pipeline anti-invecchiamento.

### 2.3 Decomposizione ↔ routing: un OTTIMO ECONOMICO a U
- Decomporre più fine → foglie più semplici → bastano modelli economici (costo/foglia ↓)…
- …ma più foglie → più chiamate fisse + coordinamento/integrazione (overhead ↑).
- **Costo totale = curva a U.** L'ottimo è dove *il risparmio marginale da modelli più economici
  = il costo marginale di coordinamento*. → decompositore e router vanno **ottimizzati insieme**
  (il decompositore dovrebbe puntare alla granularità che minimizza il costo totale atteso a τ).
- Corollario: "più sotto-task possibile" è **sbagliato** (oltre l'ottimo, il costo risale).

### 2.4 L'artefatto condiviso cambia COSA è la qualità
Con la topologia "team su repo condiviso" (no merge), la qualità non si misura sui singoli output
isolati, ma sullo **stato del progetto ai checkpoint**: *builda? i test passano? è in linea coi
requisiti?* → la valutazione diventa **valutazione di STATO** (come i gate CI/CD), e l'escalation
della cascade riguarda "il progetto è in carreggiata?", non "questa singola risposta è bella?".

### 2.5 La sicurezza/isolamento ha TRE rese (un investimento, tre payoff)
La sandbox Docker + workspace isolato serve a:
1. **Safety** (differenziatore: OI-MAS lo dichiara come limite);
2. **Riproducibilità della misura** (ambiente controllato → costo/qualità misurabili in modo valido);
3. **Parallelismo dello swarm** (isolamento → agenti che non si calpestano).
→ ciò che sembrava "supporto" abilita due dei tre pilastri.

### 2.6 Tutto è un'ottimizzazione VINCOLATA (vedi §0)
Non "minimizza il costo" ma "minimizza il costo *a qualità ≥ τ*" → frontiera di Pareto costo/qualità.
Ogni componente serve questo: router (cheapest ≥ τ), cascade (escala se < τ), decomposizione (abbassa
il costo per raggiungere τ), valutazione (definisce/misura τ).

### 2.7 L'osservabilità è il SISTEMA NERVOSO
Gli stessi log costo+qualità alimentano **tre** cose: la prova sperimentale (pilastro 3), il dataset
del router (pilastro 1), e la decisione di escalation a runtime (cascade). Ciò che abbiamo costruito
come "logging" è in realtà il substrato del flywheel di apprendimento.

---

## 3. Routing (pilastro 1)

> **Decisione rivista il 23 ottobre 2026 (D48).** La «Decisione» in fondo a questa sezione (cascade → dati → router
> appreso) è superata. Delle strategie sotto restano **cascata/escalation** (ora con cancello eseguibile),
> **capability-aware** (filtro per capacità, già nel registro dei modelli) e **role-based** (planner forte, worker
> economici). Il router appreso e il classificatore che prevede in anticipo diventano lavoro futuro, per tre
> motivi: (1) le prove raccolte in §7.3 mostrano che sul codice la previsione separa male i casi (AUROC ≈ 0,62 per
> un classificatore che legge solo la richiesta, NadirClaw) mentre la verifica del risultato rende; (2) con 5
> compiti di sviluppo non ci sono dati per addestrare; (3) i router con pesi pronti leggono il primo turno e sono
> addestrati su coppie di modelli del 2024 (RouteLLM), quindi andrebbero comunque riprovati sul dominio. La
> granularità della scelta resta per pezzo (planner, worker, critico, escalation), non per turno.

**Strategie** (con la lente swarm):
- *Keyword/euristica* → fragile.
- *LLM-classifier* → coarse, statico.
- *Cascade/escalation* → non predice, **scopre** (prova cheap, escala su qualità < τ). Si sposa col
  Pilastro C come giudice. Base: FrugalGPT.
- *Router appreso (reward model)* → economico a runtime; **serve dataset** → lo fornisce il flywheel. Base: RouteLLM.
- *Capability-aware* → filtra per capacità richieste (vision/contesto/tool) PRIMA del costo.
- *Role-based* → meta forte, worker economici.

**Perché NON i "tier":** comprimono la scelta su un asse (facile↔difficile); la realtà è
multidimensionale (vision, contesto lungo, tool). Vista corretta: **capacità (filtro hard) +
frontiera di Pareto costo/qualità**. I tier al massimo come *prior morbido*.

**Decisione:** ibrido **cascade → genera dati → router appreso**, con routing **per-sotto-task**
(dinamico), filtro per capacità, e ruolo (meta/worker). Misura a stadi: baseline → cascade → router.

---

## 4. Architettura & topologia (substrato)

**Principio:** NON Map-Reduce con merge finale. Il software è un **artefatto condiviso interdipendente
che cresce incrementalmente** → modello **"team su git"**:
- **Planner/Tech-lead** (modello forte): decompone a **granularità ottimale** (validata), governa il
  DAG delle dipendenze, indìce i review — e fissa il **sistema di stile** (palette, tipografia,
  spaziature, tono) *prima* che i worker partano. È l'art director del team: la coerenza fra le
  sezioni diventa un vincolo di specifica, non un effetto emergente (§5.9, D15).
- **Router** (per sotto-task): assegna il modello.
- **Worker** specializzati (= Agent M1 + modello + sandbox): scrivono/leggono **incrementalmente**
  nel **Workspace condiviso + Blackboard** (interfacce/convenzioni/contratti → prevengono collisioni).
- **Review/Validazione** ai checkpoint (sync + DevOps gate): *non fonde output, valida l'insieme*.
- Conflitti su file → risoluzione **incrementale stile git**, non merge monolitico.
- **NO mesh** (O(N²) = caos): gerarchico + Blackboard.
- Ispirazione: **MetaGPT** (azienda software simulata, SOP + documenti condivisi), **ChatDev** (ruoli a fasi).
- Caveat onesto: "simulare gli umani" non è gratis (costo, chiacchiericcio, finto-accordo) → serve struttura.

I residui reali di coordinamento (non spariscono col no-merge): **ordinamento dipendenze (DAG)**,
**risoluzione conflitti** (incrementale), **validazione dell'insieme** (build/test).

---

## 5. Valutazione (pilastro 2 — il vero nodo)

### 5.1 La qualità è un VETTORE per-categoria (non un numero)
| Tipo task | Oggettive (auto, gratis) | Soggettive (giudice) |
|---|---|---|
| Frontend | build, **Lighthouse** (perf/a11y), **axe-core**, bundle size | gerarchia visiva, spaziatura, colori, coerenza |
| Backend/logica | test pass@k, type-check, lint, complessità, performance | leggibilità, idiomaticità |
| Refactor | test ancora verdi, complessità ↓, dimensione diff | "pulizia" percepita |
| Trasversali | **costo** (token×prezzo), latenza, completamento autonomo | — |
Anche il "gusto" ha **proxy oggettivi** (Lighthouse/axe) → catturane una fetta gratis.

### 5.2 Misurare il soggettivo = trasformarlo in PREFERENZE
La soggettività si quantifica come **classificazione binaria di preferenza** (A > B): non serve
definire matematicamente "bellezza", basta sapere che la maggioranza preferisce A a B. È così che i
frontier model hanno imparato il "gusto" → ed è così che lo impara il **tuo** giudice/router.

**Metodi (LLM-as-a-judge):**
- *Pairwise comparison* (A vs B anonimi) — più affidabile dei voti assoluti; dà **ranking** (ciò che serve al router). Principio di LMSYS Chatbot Arena.
- *Single-answer grading* (1-5 su rubrica).
- *G-Eval* (il giudice genera i criteri con Chain-of-Thought, poi vota) — alta correlazione con gli umani.

**Bias del giudice + rimedi:**
- *Posizionale* (preferisce il primo) → scambia l'ordine, media.
- *Verbosity* (premia il lungo) → penalità esplicita nella rubrica / vincoli di token.
- *Egocentrico/self-preference* (premia sé stesso/la sua famiglia) → giudice **terzo** o **panel** di modelli diversi.

**Framework pronti:** DeepEval (unit-test LLM, G-Eval), Promptfoo (prompt/sicurezza), RAGAS (RAG, faithfulness), Langfuse/Opik (osservabilità + voti in produzione).

### 5.3 Come i frontier model hanno imparato la soggettività (e come lo farai tu)
1. **Pre-training**: predice la parola successiva (grammatica, fatti). Nessun concetto di "buona risposta".
2. **SFT (Supervised Fine-Tuning)**: imita coppie [prompt → risposta desiderata] curate. Rigido.
3. **Alignment / Preference Tuning** (la "magia" della soggettività):
   - **RLHF**: umani **ordinano** gli output → si addestra un **Reward Model** → **PPO** ottimizza il modello per massimizzare il reward.
   - **DPO**: ottimizza **direttamente** sulle coppie (chosen/rejected), **niente reward model separato né RL** → più semplice/economico. **← la via giusta per la tesi.**
   - **RLAIF / Constitutional AI** (Anthropic): un **modello forte fa da labeler** al posto degli umani (AI feedback), data una "costituzione". **← come generi i dati senza budget umano.**

### 5.4 Il limite vero del soggettivo: anche gli UMANI dissentono
Su "questo frontend è bello" due esperti non concordano → **non esiste un ground truth netto**. Mossa
scientifica: **misurare l'accordo tra annotatori** (Cohen's/Fleiss' **kappa**) e dichiararlo. Puoi
rivendicare qualità **solo fino al soffitto dell'accordo umano**. Così una debolezza ("è soggettivo!")
diventa **rigore** ("ho misurato quanto è soggettivo e calibrato il giudice di conseguenza").

### 5.5 I due layer appresi (da non confondere)
- **Layer 1 — Giudice/Reward model**: impara la *qualità* da preferenze (DPO, dati via RLAIF + piccolo set umano calibrato con kappa).
- **Layer 2 — Router**: impara a *scegliere il modello* che massimizza `(qualità_Layer1 − costo)`, allenato sulle etichette del Layer 1.
Il Giudice **alimenta** il Router.

### 5.6 Aggregazione dei giudizi paralleli (gate + Bradley-Terry)
Più giudici **paralleli** (sicurezza, accuratezza, stile…) — niente catena sequenziale che propaga errori.
1. **Standardizzazione (JSON):** ogni giudice risponde con *structured output* a schema rigido
   (es. `{"safe": true, "toxic_score": 0.1}`, `{"accuracy_score": 4}`). Non si aggregano testi liberi.
2. **Layer di vincoli HARD (gate ON/OFF):** safety/etica **e capacità** (es. serve vision) non sono
   mediabili. Se un vincolo hard fallisce → punteggio globale = **0**, a prescindere dal resto.
   (La sicurezza tossica ma "ben scritta" deve fare 0, non una media.)
3. **Sintesi dei criteri SOFT — attenzione:** la *media ponderata di punteggi ASSOLUTI* è l'anello
   debole: (a) i voti assoluti non sono **calibrati** tra giudici/task e portano bias (verbosity, scala);
   (b) i pesi scelti a mano reintroducono soggettività. **Fix:** ricava lo scalare dai **confronti a
   coppie** via **Bradley-Terry / Elo** (come Chatbot Arena) → rating calibrato; e i **pesi dei criteri
   apprendili/derivali** dai dati, non a occhio.
4. **Target del Router:** per ogni prompt, `argmin costo s.t. qualità ≥ τ` (la scelta Pareto-ottima) —
   è la §0 resa dataset. Il "vincitore" è il più economico sopra soglia.
5. **Promemoria:** il Router predice dal **prompt (pre-esecuzione)** una qualità misurata *dopo* →
   sbaglierà → la **cascade** è la rete di sicurezza che copre gli errori di predizione.

### 5.7 Che modello usare come Router
Principio guida: **il Router gira per OGNI sotto-task → overhead trascurabile** o ti mangi il risparmio.
| Opzione | Verdetto |
|---|---|
| LLM generativo 1-3B (Phi, Llama-3B) | ❌ overkill: il routing è classificazione, non generazione; aggiunge latenza/costo dove devi risparmiare |
| Encoder fine-tuned (DistilBERT/MiniLM + testa) | ✅ leggero/veloce; è la variante BERT di RouteLLM, funziona |
| **Embedding + testa leggera** (logistic/MLP/kNN, o matrix factorization) | ✅✅ quasi costo-zero a runtime; più robusto all'obsolescenza |

- **Raccomandazione:** embedding del prompt + testa leggera (o piccolo encoder fine-tuned). Vicino a costo zero.
- **Formulazione anti-obsolescenza:** NON un classificatore a **N-vie fisso** (aggiungere un modello = ri-train).
  Invece **scoring per coppia `(prompt, modello)`**: un modello nuovo = lo *scori e basta*. È la proprietà
  di *transfer* di RouteLLM. Flywheel + scoring-per-coppia = router che invecchia lentamente.
- Conferma: **ELHSR** (reward head **lineare** su LLM congelato) → "testa leggera su rappresentazione
  pre-calcolata" è la via giusta per un reward/router economico.

### 5.8 Due livelli di giudizio (settembre 2026, D14)

Il problema di partenza è una tensione. La **valutazione** vorrebbe artefatti piccoli, giudicabili in
pochi secondi e attribuibili a chi li ha prodotti. La **tesi** ha bisogno di task grandi e composti,
che *richiedono* uno swarm: un componente isolato si genera con una chiamata sola, e senza niente da
scomporre non c'è niente da instradare. Ridurre il task a componenti avrebbe risolto la valutazione
svuotando la tesi (D16).

La tensione si scioglie separando i **livelli**, non i task. Il task resta il sito intero; il
giudizio si fa in due momenti, con due scopi diversi:

| Livello | Quando | Cosa si giudica | A cosa serve |
|---|---|---|---|
| **Sezione** | durante il lavoro | una sezione prodotta da un sotto-task (hero, prezzi, testimonianze), da sola | **addestrare** il router |
| **Pagina** | a lavoro finito | la pagina intera, contro quella della baseline | **dimostrare** la tesi |

Due problemi si risolvono insieme:
- **Attribuzione del merito.** Se si giudicasse solo la pagina, un buon risultato andrebbe ripartito
  fra sei contributi senza modo di dire quale scelta di modello l'ha prodotto. Il giudizio di sezione
  *è* l'etichetta del sotto-task che l'ha generata.
- **Validazione circolare.** Se lo stesso giudice producesse le etichette di addestramento e misurasse
  la campagna, il sistema risulterebbe buono secondo una metrica che è stato addestrato a soddisfare.
  Qui il router impara dalle sezioni ed è verificato sulle pagine: due metriche diverse.

### 5.9 La coerenza si specifica, non si impara (D15)

Sei sezioni ognuna ben fatta possono comporre una pagina incoerente: palette, tipografie e stili che
non c'entrano l'uno con l'altro. Il router, addestrato sezione per sezione, **non vede** questo
difetto e non potrebbe impararlo.

La coerenza va quindi imposta a monte, come fa un team di design reale:

| Ruolo umano | Nel sistema | Decide |
|---|---|---|
| Art director | planner | il sistema di stile, prima di iniziare |
| Designer | worker | le singole sezioni, dentro quel sistema |
| Revisore | giudice di pagina | se l'insieme regge |

Il planner restituisce **due uscite in una sola chiamata** — la scomposizione e il sistema di stile —
invece di essere diviso in due agenti. Un art director separato aggiungerebbe una chiamata al modello
forte nel punto già più caro del sistema, e i due ruoli sono accoppiati (il layout cambia la
scomposizione e viceversa), quindi dovrebbero iterare. Separarli converrebbe solo se esistesse un
modello più adatto *ed* economico per il design: a settembre 2026 nessuna classifica pubblica isola
quella capacità, e in cima alle classifiche di sviluppo web ci sono solo modelli di fascia alta. Resta
un esperimento misurabile, non un'assunzione.

Nota: la divisione rafforza la tesi invece di complicarla. Senza scomposizione un modello solo fa
tutto e non c'è niente da ottimizzare; con la scomposizione, le decisioni globali (poche e cruciali)
vanno a un modello forte e le sezioni possono andare a modelli economici. È il contrasto di costo su
cui si regge l'intero claim.

### 5.10 Il giudice va verificato prima di usarlo

Un lavoro di maggio 2026 — *Visual Aesthetic Benchmark: Can Frontier Models Judge Beauty?*
(2605.12684) — ha testato venti modelli multimodali di punta sul giudizio estetico. Il migliore
raggiunge il **26,5%** di accuratezza contro il **68,9%** degli esperti umani.

Due cautele prima di trarne conclusioni: il dominio è arte, fotografia e illustrazione, non
interfacce — che hanno regole più condivise (allineamenti, contrasto, gerarchia) e sono verosimilmente
più facili; e la misura è severa, perché chiede di indovinare *sia* il migliore *sia* il peggiore in
un gruppo, in tre ordini diversi, non di scegliere fra due. Ma la direzione è chiara: **chiedere a un
modello forte «quale è più bello?» e fidarsi non basta.**

La stessa ricerca contiene però la notizia che conta per questa tesi: addestrando un modello più
piccolo sui giudizi degli esperti, le sue prestazioni si avvicinano a quelle di uno dieci volte più
grande. **Il segnale estetico si insegna.** È esattamente il Layer 1 di §5.5: non usare un giudice
pronto, ma addestrarne uno sulle preferenze.

La procedura che ne discende:
1. poche centinaia di confronti **umani**, fatti da due annotatori sulle stesse coppie;
2. dal loro accordo si ricava il **kappa** — quanto concordano due persone, tolto il caso (con due sole
   opzioni si è d'accordo metà delle volte per fortuna). Il kappa **richiede almeno due annotatori**:
   con uno solo non c'è accordo da misurare;
3. si misura quanto il giudice automatico concorda con loro;
4. solo se l'accordo si avvicina a quello fra gli umani, il giudice si usa sul resto.

E una leva che precede tutte le altre: **la precisione della domanda.** «Quale è più bello?» è la
domanda peggiore possibile, per un modello come per un umano. Criteri espliciti alzano l'accordo di
entrambi — cioè alzano il soffitto oltre il quale la tesi non può rivendicare nulla (§5.4).

### 5.11 Il vero vincolo: il costo del giudizio

**Un giudizio può costare più del lavoro che giudica.** Con un giudice di fascia alta un confronto
costa circa $0.015; con quattro candidati per una sezione servono circa otto confronti, cioè $0.12 —
mentre un task intero, nello scenario ottimizzato, costa $0.045. Il sistema risparmierebbe sulla
generazione e restituirebbe il risparmio nel giudizio.

**Nel soggettivo, il dataset di addestramento non è gratuito.** Per il codice deterministico la
cascade etichetta da sola: i test passano, quindi il modello economico è bastato. Per l'estetica il
gate deterministico dà solo un pavimento — una sezione può compilare ed essere brutta. Etichettare
«il modello economico è bastato» richiede di generare anche la versione di confronto e di farle
giudicare:

| Etichetta | costo, calcolato sul listino |
|---|---|
| deterministica — cascade con 35% di escalation | $0.0225 |
| soggettiva — modello economico + baseline + un giudizio economico | $0.0587 |

**La baseline è il metro.** Bradley-Terry produce un punteggio relativo, come l'Elo: dice che A batte
B, non quanto vale A in assoluto. «Qualità ≥ τ» ha senso solo rispetto a un riferimento, e l'unico
disponibile è la baseline mono-modello. Per questo ogni etichetta richiede la baseline eseguita sullo
stesso sotto-task — non come condizione da confrontare alla fine, ma come unità di misura.

**Le etichette soggettive sono rumorose.** Servono all'incirca il triplo degli esempi per la stessa
accuratezza, e c'è un soffitto: il router non può superare l'accordo fra gli umani.

Ne seguono due scelte di metodo:
- **Curva di apprendimento** — il numero di etichette necessarie non si stima a priori: si addestra
  su un primo lotto, si misura l'accuratezza su dati tenuti fuori, si aggiunge e si ripete, fermandosi
  quando la curva si appiattisce. È incrementale e interrompibile in ogni momento, ed è essa stessa un
  risultato: risponde a «quanti dati servono per un router utile?», che i lavori censiti non riportano.
- **Apprendimento attivo** — dopo il primo lotto, i nuovi esempi si generano dove il router è meno
  sicuro, invece che uniformemente. Tipicamente riduce di 2-5 volte le etichette necessarie.

Tutto questo pesa di più ora che il router appreso (S3) è riconosciuto come **essenziale** e non come
traguardo facoltativo (D13): è lì che sta il contributo di ricerca, e il suo costo è dominato dal
giudizio.

> **Il principio che ne risulta:** la regola di fondo della tesi — mandare ogni compito al modello più
> economico capace di svolgerlo — va applicata **anche al giudice**. È il punto in cui il costo della
> tesi si decide davvero.

### 5.12 Il metodo di valutazione costruito in R1 (abbozzo, 26 ottobre 2026)

> Le sezioni 5.1-5.11 raccolgono il ragionamento da cui si e' partiti. Questa descrive lo strumento di misura
> che esiste davvero nel codice dopo R1 ed e' la base del capitolo «metodo di valutazione». Le regole vincolanti
> stanno in `PROTOCOLLO.md` §6-§7; qui c'e' l'ordine dell'esposizione.

**1. Che cosa si misura.** Due metriche affiancate, nessun voto unico (§7 del protocollo): **funziona**
(punteggio 0-100 da controlli eseguiti) e **piace** (voto di un giudice a coppie, −2..+2). C e' «non inferiore» a B
solo se lo e' su entrambe. Il motivo della separazione: un sito bello che non funziona e un sito spoglio che
funziona non devono potersi compensare.

**2. Il compito e le regole uguali per tutti.** Cinque compiti di sviluppo estratti con un seme da
ArtifactsBench e WebGen-Bench (`webtasks.py`), con verdetto scritto per ogni compito letto. Ogni braccio riceve lo
stesso prompt (`webprompt.py`): testo del compito, contratto delle rotte, fino a 12 marcatori `data-testid`
obbligatori, un solo `start.sh` su porta fissa. Tutto cio' che lo script usera' per misurare e' scritto
**prima** di generare qualunque sito.

**3. L'esecuzione.** Il sito si avvia in un container senza rete, con server e Chromium insieme (immagine
`orc-renderer`, versioni bloccate), e si apre a 375, 768 e 1440 px. Ne escono screenshot, errori JavaScript,
sbordo orizzontale e violazioni axe-core gravi. Ripetibilita' verificata con Docker vero: lo stesso sito statico
da' screenshot identici byte per byte, lo stesso sito con server da' passo per passo lo stesso esito.

**4. «Funziona».** Uno script Python per compito, scritto prima della generazione partendo dai casi di prova
delle due fonti, eseguito da un interprete unico. Punteggio = passi superati / passi valutabili × 100; un passo
fallito trascina quelli che ne dipendono; un passo la cui preparazione via rotte fallisce e' «non valutabile» ed
esce dal denominatore. I test diretti sulle rotte formano la metrica secondaria «funziona-server». Taratura degli
script: 0 sul sito vuoto per tutti e 5, 100 sui siti di riferimento.

**5. «Piace»: il giudice.** GPT-6.1 Sol via Codex CLI (D52), di una famiglia che non e' in gara. Vede i sei
screenshot dei due siti e le stesse schede per compito date ai votanti umani, ed e' cieco: nomi neutri delle
immagini, nessun accesso a file o comandi, tentativo scartato se usa strumenti. Vota ogni coppia **nei due ordini**
e si tiene la media, cosi' la preferenza per una posizione si annulla (sulle 150 coppie di calibrazione e'
comparsa in 13). Ogni giudizio registra modello, sforzo, versione di Codex, impronte sha256 delle istruzioni e
delle schede, durata e token.

**6. Il giudice si valida prima di usarlo.** 150 coppie votate alla cieca da 7-8 persone con un'app web. Regola
fissata e registrata prima di vedere i voti: accordo sul segno a tre classi con **Scott's π**, accordo umani-umani
come riferimento (non come tetto), Δ = π(giudice-umani) − π(umani-umani), intervalli bootstrap sulle coppie.
Il giudice si usa se i limiti bassi al 95% di π(umani-umani) e π(giudice-umani) sono sopra 0 e quello di Δ sopra
−0,10. Altrimenti piano B: in R6 le coppie C-B le votano persone. *Esito: da scrivere dopo il 28 ottobre.*

**7. Limiti da dichiarare.**
- Con 150 coppie e 7 votanti un giudice di poco peggiore di un votante umano passa circa una volta su due
  (simulazione): la regola esclude i giudici cattivi, non certifica quelli quasi buoni.
- Il giudice vede screenshot, non usa il sito: l'interazione la misura solo «funziona».
- Gli script coprono le funzioni scritte nel compito, non tutto cio' che un utente farebbe.
- Il giudice e' un servizio in abbonamento che cambia nel tempo: la versione e' registrata, ma la stessa versione
  potrebbe non essere piu' disponibile per chi rifa' l'esperimento.
- Code aperte nel codice, senza effetto sui numeri: riga troncata in coda al file dei giudizi dopo un arresto,
  π non definito su un votante con una sola categoria (saltato e contato), α ordinale come media a coppie.


---

## 6. Pipeline completa (dal task al risultato + apprendimento)

> **Aggiornata il 23 ottobre 2026 (D48).** Nella parte RUNTIME il «Router(per foglia)» è l'assegnazione per ruolo
> del registro, e la «cascade» usa il cancello eseguibile prima del critico. La parte OFFLINE (dataset, DPO, reward
> model, router) è lavoro futuro.

```
RUNTIME:
  task → Planner(forte) → sotto-task (DAG) → Router(per foglia) → Worker(modello scelto, sandbox)
       → Workspace/Blackboard condiviso (cresce) → Review/Validazione ai checkpoint → output
       [cascade come rete di sicurezza: qualità<τ → escala]   [contabilità costi su ogni chiamata]

OFFLINE (flywheel):
  benchmark-harness: stessi task × più modelli
    ├─ oggettive: build, test pass@k, Lighthouse/axe, costo, latenza
    └─ giudice (frontier, pairwise, RLAIF, bias-mitigato) → preferenze
         → dataset → DPO → Reward model (Layer1) → Router (Layer2)
         → calibrazione su piccolo set umano (kappa)
```

---

## 7. Stato dell'arte & posizionamento

| Lavoro | Cosa fa | Relazione con la tesi |
|---|---|---|
| **OI-MAS** (2601.04861) | router RL a 2 stadi (ruolo+scala modello), confidence-aware, task verificabili, sequenziale | **vicino**; tu: software open-ended, artefatto condiviso, modelli commerciali, valutazione execution/multimodale, **safety+memoria** (loro limiti dichiarati) |
| **MasRouter** (2502.11133) | routing per multi-agent systems | dichiara che il routing classico è single-agent; tuo prior diretto, definisci il delta |
| **RouteLLM** (2406.18665) | router appreso da preferenze, **transfer tra coppie di modelli** | base per Layer 2; il transfer attenua l'obsolescenza |
| **FrugalGPT** | cascade + quality estimator (fino a 98% risparmio) | base della tua cascade |
| **Differentiable MoA** (2605.15706) | pesi differenziabili per **fondere** output (ensemble per qualità) | **contrasto**: fondere≠routing per costo; differenziabilità non regge su API commerciali |
| **MetaGPT / ChatDev** | team-azienda simulati, ruoli + SOP + docs condivisi | base della topologia ad artefatto condiviso |
| **LLM-as-a-judge** (Zheng 2023; survey 2025) | giudice LLM (~>80% accordo umano, con bias) | metodo di valutazione del soggettivo |
| **RLHF / DPO / RLAIF** | preference tuning | come alleni Giudice e Router |

### 7.1 Rassegna di agosto 2026 (lavori successivi alla prima stesura)

| Lavoro | Cosa fa | Relazione con la tesi |
|---|---|---|
| **DeLM** (2606.10662) | Agenti paralleli senza agente principale: contesto condiviso + coda di task. **Tre versioni molto diverse.** v1 (9 giu): contesto verificato da un LLM prima dell'ammissione, memoria gerarchica gist → riassunto → grezzo; SWE-bench Verified con Gemini 3 Flash 77.4% Pass@4 a $0.12 "per task" (Tab. 1, p. 8), contro 75.1% del baseline più forte a Pass@4 (mini-SWE-agent). v3 (4 ott): il gate di ammissione centralizzato è rimosso (verifica distribuita, p. 6), la tesi diventa la latenza; su SWE-bench gli stessi $0.12 sono **Cost/Submission**, il costo per task è $0.24 (n=2) e $0.47 (n=4) (Tab. 5, p. 10). Tutti gli agenti usano **lo stesso modello** (p. 7) | Vicino sull'architettura, **non sul routing**: non sceglie fra modelli. Utile come dato sul costo di coordinamento: i sotto-agenti nativi di Codex e Claude Code costano 1,5-2,9× l'agente singolo a parità di accuratezza (v3 Tab. 2, p. 8). Il cambio di significato dello stesso $0.12 fra v1 e v3 è l'argomento migliore per una metrica unica (§7.2) |
| **FlyRoute** (2605.22057) | Profili testuali degli agenti aggiornati da un ciclo: un giudice LLM accetta le risposte con voto ≥ 0.7, ogni 20 successi la descrizione dell'agente viene riscritta, il router legge descrizione + esempi simili (BM25). 72.6% → 89.8% di accuratezza di instradamento (Tab. 2, p. 6) | Prior sul flywheel di *competenze apprese*, ma: instrada verso agenti di dominio, non verso modelli con un prezzo; **nessun costo misurato**, nemmeno quello del giudice; competenze binarie e testuali; agenti mai cambiati durante l'esperimento (p. 7); dati non pubblici. Il delta difendibile è la tabella numerica legata al prezzo, su categorie soggettive |
| **AgentCARD** (2606.20629, mag 2026) | Team planner → esecutore: tutte le combinazioni di 4 modelli API più modelli self-hosted, su 5 benchmark (SWE-bench compreso); costo per task in dollari, frontiera di Pareto, incertezza ±2-3 punti per cella | **Il vicino più stretto di S1.** I team eterogenei stanno sulla frontiera (GPT-5.4 planner + MiniMax-M2.7 esecutore: 76.2% a $0.021 contro 68.2% di GPT-5.4 da solo, Tab. 4, p. 15), ma **la coppia conta**: Claude-Opus-4.6 planner + MiniMax-M2.7 fa 60.1%, sotto Opus da solo (66.4%). Scegliere la coppia su metà dei task funziona sull'altra metà in 4 benchmark su 5 (p. 22). Un verificatore aggiunto aiuta solo se pianifica meglio del planner (p. 9). Tratta il *deployment* (API / self-hosted) come secondo asse del costo |
| **SWE-Router** (2607.00053, workshop ICML 2026) | Il modello economico lavora qualche turno; una testa appresa legge la traiettoria parziale e decide se continuare o passare al modello forte | Contro i router che leggono solo la descrizione: +12-15 punti di Route-AUC su 100 task SWE-bench tenuti fuori (p. 4, p. 9), non confermato sul secondo dataset (Tab. 2, p. 9). Teorema: condizionare sulla traiettoria non peggiora mai la scelta ottima. Alternativa per D6 (S3) |
| **Agentic Routing / OpenSquilla** (2607.11399, rapporto tecnico) | Routing per passo condizionato dallo stato dell'harness; ogni decisione produce un record (query, stato, scelta, esito, costo) che addestra router successivi | Stessa idea del flywheel di §2.2, **ma il flywheel non è sperimentato** (si valuta solo il primo router, una run per configurazione, configurazioni scelte a mano). Utile per lo schema dei record: separare ciò che il router credeva, ciò che ha scelto e l'esito, e registrare se la scelta era un'esplorazione, come richiede l'apprendimento off-policy |
| **Cost-of-Pass** (2504.13359, ICLR 2026) | Costo atteso per ottenere una soluzione corretta: costo medio diviso tasso di successo (eq. 2, p. 4); frontiera rispetto al costo di un esperto umano | **Anticipa CPT-τ** (§7.2). Prevede già costo della verifica, tentativi falliti e overhead (App. D.1, p. 22); lascia aperto il successo continuo o graduato (p. 23-24). Avverte che con criteri indulgenti un sistema economico che tira a indovinare sembra ottimo (App. C.8, p. 21-22) |
| **Harness Tokenomics** (2609.28919, set 2026) | Router dentro gli harness di coding che non rompe la prompt cache; regola per quando un cambio di modello a metà lavoro ripaga le scritture in cache (eq. 1, p. 6); ricalcolo di circa 10.000 sessioni reali | Anticipa la **dimensione del percorso** (§7.2): le stesse famiglie open-weight costano 0,10-0,27× Opus 5 dove la cache ha un prezzo e 0,70-0,90× su Bedrock, che non lo prevede (p. 16-17); un gateway che toglie i marcatori di cache fa pagare tutto come input non in cache (p. 17). Calcolato sul listino, non sulle fatture. Il risparmio del 13-21% viene da scenari scritti dagli autori (p. 21) |
| **Model Equality Testing** (Gao, Liang, Guestrin, ICLR 2025) | Verifica statistica di quale modello un'API sta davvero servendo | Il percorso può cambiare anche **il modello servito**, quindi la qualità, non solo il costo. Citato da Cost-of-Pass (p. 24), che consiglia di trattare ogni coppia fornitore-modello come una strategia distinta |
| **LLM-as-a-Verifier** (2607.05391, Stanford) | Punteggi continui dall'attesa sui **logit** invece del voto intero; *Probabilistic Pivot Tournament*: ordina N candidati in **O(Nk)** anziché O(N²) | Risolve i **pareggi** che affliggono i giudici a scala 1-5, e rende economico il confronto fra molti candidati. Materiale diretto per il Judge L2 |
| **GoAgent** (2603.19677) | Genera la **topologia di comunicazione** trattando i gruppi come unità atomiche; information bottleneck sulla comunicazione fra gruppi. −17% token | Ortogonale: loro instradano *l'informazione fra agenti*, la tesi instrada *il task verso il modello*. Utile come contrasto, non come concorrente |
| **Blackboard LLM** (2510.01285) | Lavagna a **volontariato**: l'agente centrale pubblica, i subordinati si auto-candidano per capacità. +13-57% di successo end-to-end | Versione 2026 dell'idea di lavagna. **Non adottata** (§7.2), ma va citata: risolve un problema — il coordinatore che ignora le capacità — che qui non si pone perché il registro le conosce per costruzione |
| **Comunicazione latente** (2606.05711) | Gli agenti si scambiano embedding / hidden state / KV-cache invece di testo | **Non applicabile**: richiede accesso agli interni del modello, impossibile con API commerciali. Da citare come direzione futura |
| **Survey protocolli** (2505.02279) | MCP, A2A, ACP, ANP: interoperabilità fra agenti di organizzazioni diverse | Non adottati: gli agenti sono tutti dello stesso sistema, nello stesso processo |
| **Agentic plan caching** (2506.14852) | Riuso dei piani fra task simili; la fase di pianificazione è la maggior parte del costo di calcolo | Rilevante perché nel sistema instradato **l'orchestratore diventa la voce di costo dominante**: qualunque leva sul planner domina le altre |
| **Visual Aesthetic Benchmark** (2605.12684, mag 2026) | 20 modelli multimodali di punta sul giudizio estetico comparativo: il migliore **26,5%** contro **68,9%** degli esperti umani; un modello più piccolo addestrato sui giudizi esperti si avvicina a uno dieci volte più grande | Il risultato più rilevante per il pilastro della valutazione: un giudice pronto non basta, uno addestrato sì. Dominio arte/fotografia, non interfacce (§5.10) |
| **Jev** (TypeSafe AI, accesso anticipato dal 15 set 2026) | Modello non generativo: invece di produrre testo restituisce un valore tipizzato con una confidenza. $0.042 per milione in input, output gratuito | Inutile come worker, non conveniente come router (l'embedding costa meno), **candidato come giudice**: ~180× più economico di un giudizio frontier. Da verificare su estetica e immagini (§5.11) |
| **WebDev Arena / Design Arena** (classifiche a preferenza umana cieca) | Classifiche Elo su interfacce generate, votate da umani senza sapere quale modello le ha prodotte | Confermano che il confronto a coppie cieco è lo standard del settore (§5.2). **Nessuna isola la capacità di art direction**: misurano lo stile e il codice insieme (§5.9) |

### 7.2 Tre rivendicazioni della rassegna di agosto, ridimensionate a ottobre

Ad agosto erano proposte come novità. Lette per intero DeLM e FlyRoute e i lavori
di §7.1, nessuna delle tre regge come idea nuova: due sono anticipate, una è nota.
Resta a ciascuna un margine più stretto.

1. **Il percorso, oltre al modello.** *Anticipata.* Che lo stesso modello costi
   diverso a seconda della strada è già mostrato: Harness Tokenomics ricalcola
   sessioni reali su percorsi con e senza prezzo della cache (p. 16-17); AgentCARD
   tratta il deployment come secondo asse; Cost-of-Pass, citando Gao et al. (ICLR
   2025), nota che il fornitore può cambiare anche il modello servito (p. 24); DeLM
   stesso, chiamando tutto via OpenRouter, segnala in nota un costo di circa $1 per
   task quando la cache non passa (v1 Tab. 1, p. 8). **Margine rimasto:** tutti
   *calcolano* sul listino; qui si **misura** per chiamata, separando chi è chiamato
   da chi fattura (`api_provider`, `billing_provider` dello `UsageRecord`), e lo si
   confronta con il costo addebitato. È un contributo di misura, e regge solo se
   M2s.4 lo produce. Il 2,25× di opus-5 è calcolato come i loro.
2. **Token e dollari non sono la stessa metrica.** *Nota.* DeLM riporta dollari e
   mostra lo stesso fenomeno (contesti di dimensione simile pesano l'1,7-3,7% della
   spesa con un modello e il 7,7-17,7% con un altro, v3 Tab. 6, p. 14); Agentic
   Routing osserva costi in calo con token in aumento (p. 15); Harness Tokenomics apre
   con «List price is the wrong metric» (p. 1). Diventa una **nota di metodo**: la
   tesi riporta dollari, i token solo come dato ausiliario. Il conto «−17% di token
   ≈ −2,5% di spesa» per GoAgent presuppone che i token risparmiati fossero in cache:
   va verificato su GoAgent prima di usarlo.
3. **CPT-τ.** *Anticipata nella forma.* È il **Cost-of-Pass** (Erol et al., ICLR
   2026) con «corretto» sostituito da «qualità ≥ τ». **Margine rimasto:** il successo
   definito da un giudice su una qualità **graduata e soggettiva**, che Cost-of-Pass
   lascia a lavoro futuro (p. 23-24), con il costo del giudizio e dell'escalation
   misurati e non stimati. Differenza tecnica da dichiarare: Cost-of-Pass fa la media
   dei rapporti per problema (eq. 8, p. 5); qui si usa il rapporto dei totali
   (costo della campagna / task riusciti), così un task mai riuscito non manda il
   risultato all'infinito. Rischio da gestire: con τ basso o un giudice indulgente,
   un modello scadente ed economico ottiene un costo per successo basso (Cost-of-Pass
   App. C.8, p. 21-22). La verifica del giudice (§5.10) e la scelta di τ servono
   anche a questo.

---

**Gap difendibile (ottobre 2026):** cost-routing in uno **swarm di coding-agent** su
**artefatto condiviso**, con valutazione **execution-based + multimodale del soggettivo**,
flywheel cascade→router e isolamento/sicurezza. Nessuno dei lavori letti combina
artefatto condiviso, giudizio soggettivo e costo misurato in fattura. I singoli pezzi
hanno invece vicini precisi: S1 → AgentCARD, S2 → SWE-Router, S3 e flywheel → Agentic
Routing e FlyRoute, metrica → Cost-of-Pass, percorso → Harness Tokenomics.

### 7.3 Router pronti e politiche agentiche (rassegna del 22 ottobre 2026)

Domanda di partenza: esistono router già pronti o già addestrati da usare invece di costruirne uno? Sì; ma letti
sul sorgente fissato a commit, cambiano soprattutto il **disegno della prova** (D48, D49), non il codice di OrcV2.
Verifiche documentali e statiche, nessun router eseguito.

| Lavoro (versione letta) | Cosa fa davvero | Cosa cambia per la tesi |
|---|---|---|
| **Switchyard** (NVIDIA-NeMo, commit `7558a1d`, Apache-2.0, pre-1.0) | Libreria e servizio di routing durante il lavoro di un agente. Politiche senza addestramento: **Plan/Execute** (il forte fino alla prima modifica di un file, poi l'economico; basta anche una modifica fallita, `plan_execute.rs:90`), **Stage** (regole su errori degli strumenti, modifiche e stallo), **Escalation** (turno economico, giudice, eventuale forte: si pagano tutti e tre), **Advisor** (il forte rilegge la trascrizione e propone una correzione), **VGR** (verifica del candidato prima di servirlo: sperimentale, mai misurata) | Su DeepSWE v1.1 (113 compiti, 3 esecuzioni) Plan/Execute GPT-5.6 Sol → Luna: 60,8% a $180,51 contro Sol 62,8% a $720,95 e Luna 51,0% a $50,02; Advisor 57,5% a $208; costi ricalcolati sul listino OpenRouter del 9 set 2026. È il braccio **H** (D49). Sul campione SWE-Atlas (40 compiti) economico, forte e router corretto risolvono tutti 15 compiti e il router costa il 77% in più dell'economico (prezzi sintetici): motivo per tenere D |
| **Switchyard su OpenRouter** (`nvidia/switchyard`, pagina letta il 23 ott 2026) | Servizio ospitato: capability, stage, auto, composite, random, passthrough; **non** Plan/Execute, Advisor, Escalation. Al massimo tre candidati, livelli assegnati per prezzo | Il giudice riceve una proiezione ridotta della richiesta con le **immagini sostituite da segnaposto** e una scheda che dà l'economico per inaffidabile sui lavori di codice sostanziali: sui siti manderebbe quasi tutto al forte. Le chiamate del giudice sono generazioni a parte. Non adatto alla prova |
| **NadirClaw** (v0.25.1, PolyForm Noncommercial) | Proxy con classificatore della richiesta, cascata economico → verificatore → forte in libreria (non collegata al server standard) | Classificatore che legge solo la richiesta: AUROC ≈ 0,62 fuori famiglia; verificatore testuale AUROC 0,65 sul codice, scavalcato dalle regole del prodotto appena compare `def `. Il 98,3% di qualità e il 60% di risparmio su RouterBench valgono con la risposta del forte già disponibile al verificatore (limite di ricerca, dichiarato nel README). Prova per D48 |
| **Conduit** (ashita-ai, archiviato il 23 apr 2026, MIT) | Bandit (Thompson Sampling, LinUCB) che sceglie un modello per domanda e impara da un voto | Il default non usa il contenuto della richiesta; il premio è una somma pesata di qualità, costo e latenza, non un vincolo `qualità ≥ τ`; il voto automatico è un'euristica testuale. Utile solo come esempio di separazione fra scelta ed esito |
| **RouteLLM** (2406.18665, commit `0b64fda`) | Router forte/economico appresi da preferenze, pesi pubblici | Il controller legge solo l'ultimo messaggio (addestrato sul primo turno); i pesi stimano la coppia GPT-4 / Mixtral. Sulla rosa del 2026 sarebbe una prova di trasferimento |
| **RouteFM** (2609.37362, v1.0.1) | Router preaddestrato che riceve esiti osservati dei candidati e una nuova richiesta | «Senza riaddestramento» non vuol dire «senza dati»: servono esiti per candidato. Lo split dimostrativo è scelto a posteriori (dichiarato nel README) |
| **Arch-Router-1.5B** (2506.16655, licenza Katanemo non commerciale) | Abbina la richiesta a rotte descritte a parole | Riconosce la categoria, non dice se l'economico ce la farà su quel compito |
| **Not Diamond**, **OpenRouter Auto / Pareto Code** | Selettori commerciali via API | Rosa di OrcV2 non nel catalogo statico; comportamento che cambia nel tempo (Auto usa la spesa aggregata degli ultimi 7 giorni); non congelabili per una campagna |
| **LangChain**, studio su Switchyard (145 compiti agentici) | Opus 86% a $11,45; routing 80% a $3; economico 77,7% a $0,72 | Il guadagno del router sull'economico è piccolo rispetto alla variazione fra prove; il giudice pesa il 21% del costo del braccio instradato |

**Cosa se ne ricava.** (1) Lo schema «il forte pianifica, l'economico esegue» è un meccanismo già pubblicato e
misurato: la tesi non lo rivendica e lo usa come rivale (H). (2) Sul codice, prevedere in anticipo rende poco e
verificare il risultato rende: nessuno dei router esaminati esegue però il prodotto, il cancello di OrcV2 sì
(D48). (3) Il modello economico da solo è spesso competitivo: D e V sono necessari. (4) Le spese interne di un
router (giudici, risposte scartate, cache persa al cambio di modello) possono annullare il risparmio, e vanno nel
ledger. (5) Il replay su tracce registrate ricalcola il costo di una scelta, non ciò che sarebbe successo con
un'altra: non sostituisce l'esecuzione.

**Gap difendibile (aggiornato al 23 ottobre 2026):** un confronto equo sul dominio dei siti web con server fra il
forte da solo, l'economico da solo, due politiche semplici (cascata con cancello eseguibile, Plan/Execute) e uno
sciame con verifica eseguibile, con qualità validata da voti umani e costo misurato per chiamata; più la
scomposizione del risparmio fra le leve. Da controllare prima della stesura: la letteratura sulla generazione web
con verifica a ciclo chiuso (WebGen-Agent e simili), per stabilire se il cancello eseguibile come criterio di
escalation è già pubblicato.

---

## 8. Stato implementazione

- **M1 COMPLETO + hardening + test** (atomo solido):
  - Agent (classe, DI), loop ReAct, max-iter, retry+backoff, degradazione elegante.
  - Resilienza: errori→osservazioni→auto-correzione (Pilastro C).
  - Loop detection consecutiva + enum Alerts (OK/AVVISA/FERMA) + escalation avvisa-poi-ferma.
  - Tool (ABC/Strategy): bash→DockerExecutor (sandbox: no-net, non-root, read-only, effimero, limiti),
    read/write→Workspace (guardia path-traversal).
  - config centralizzata, logging professionale, requirements pinnati, **7 test pytest verdi**.
- **M2a COMPLETO — osservabilita' dei costi** (dettaglio in §9):
  listino TOML, `UsageRecord`, contabile con contratto astratto, mapper per
  provider, gateway LLM, ledger per run (JSONL + summary), budget guard e
  report di fine run.
  Resta scoperto solo l'agganciamento delle unita' non testuali
  (immagini/video/audio/3D), gia' previsto dallo schema ma non ancora esercitato
  su chiamate reali.
- **M2s IN CORSO — instradamento statico per ruolo** (3 task su 4):
  - *M2s.1* ✅ ruoli in `models.toml` (`planner` → modello frontier, `worker` →
    modello economico) con le capacita' che ogni mestiere richiede; il registro
    **verifica al caricamento** che il modello assegnato le possieda, quindi
    un'assegnazione sbagliata fallisce all'avvio e non a meta' di una run pagata.
  - *M2s.2* ✅ percorso **diretto** ai fornitori e secondo gateway. Il contratto
    fra gateway e agente, fino a qui implicito nella forma dell'SDK OpenAI, e'
    stato reso esplicito: `Agent` lavora su tipi del progetto e il secondo
    fornitore e' entrato **senza toccarlo**. E' la verifica sul campo della
    proprieta' che rende possibile lo swarm.
  - *M2s.3* ✅ fabbrica di agenti: dato un ruolo costruisce un agente **persistente**
    col modello assegnato dal registro, raggiunto attraverso il suo fornitore, con
    contabile, workspace e guardiano del budget propri. L'agente ha una finestra di
    contesto che cresce incarico dopo incarico e vive finche' chi lo ha creato non lo
    elimina; ogni incarico ha il suo ledger, il contabile somma tutta la vita. `main.py` la usa: `--role` sceglie il ruolo e il
    modello arriva dal registro. Il percorso vecchio via proxy resta con `--via-proxy` fino alla
    prima misura di M2s.4, che confronta i due percorsi.
  - *M2s.4* ⬜ prima misura reale.
- **195 test verdi**, nessuno dei quali tocca la rete o consuma budget; CI su ogni
  push. La roadmap esecutiva, inclusi i requisiti espliciti per
  immagini/video/audio/3D/RAG, vive in `M2_routing_design.md` §0 e in `ROADMAP.md`.

---

## 9. Contabilità e osservabilità (M2a — implementato)

> **Perché è un capitolo e non un dettaglio implementativo.** Il claim della tesi (§0) è
> *«riduzione di costo a parità di qualità»*. Un claim del genere è **falsificabile solo se il
> costo è misurato in modo riproducibile**: senza un apparato di misura, "costa meno" è
> un'opinione. Questa sezione descrive l'apparato. È anche il primo giro del flywheel (§2.2):
> gli stessi log servono a tre cose diverse — prova sperimentale, dataset del router,
> decisione di escalation a runtime (§2.7).

### 9.1 Tre responsabilità separate, tre oggetti

| Oggetto | Domanda a cui risponde | Non sa |
|---|---|---|
| `UsageRecord` | *quanto è stato consumato?* (quantità grezze) | quanto costa |
| `ModelRegistry` | *quanto costano le cose?* (listino da `models.toml`) | cosa è successo |
| `Accountant` | *quanto si è speso?* (la moltiplicazione) | come si chiama l'SDK |

La separazione non è estetica: produce una proprietà che serve alla tesi.

**Ricomputabilità.** Nei log finiscono le **quantità grezze**, non solo i dollari. Se un listino
cambia — e in una campagna sperimentale che dura mesi cambia — oppure se si scopre un errore di
prezzo, i costi si **ricalcolano sui log storici** senza rieseguire nulla. Rieseguire costerebbe
di nuovo denaro e, peggio, produrrebbe output diversi: la campagna non sarebbe più la stessa.

### 9.2 Le due trappole del conteggio

Entrambe producono **errori silenziosi**: nessuna eccezione, solo numeri sbagliati.

- `reasoning_tokens` è **già incluso** in `output_tokens`. Sommarlo farebbe pagare due volte la
  parte di ragionamento — e proprio sui modelli forti, che ragionano di più: l'errore sarebbe
  **sistematico e sbilanciato a sfavore del baseline costoso**, cioè nella direzione che
  gonfierebbe artificialmente il risultato della tesi.
- I token serviti dalla **cache** sono un sottoinsieme di quelli di input ma hanno **tariffa
  propria** (≈0.1× il prezzo pieno). Vanno scorporati: 350 token di cui 200 da cache sono
  `{input: 150, cached: 200}`, mai `{input: 350, cached: 200}`, che ne conterebbe 550.

Per questo `reasoning_tokens` vive **fuori** da `quantities`, dove entra solo ciò che viene
davvero moltiplicato per un prezzo.

### 9.3 Unità eterogenee, un solo dollaro

Il registro dichiara le unità e la loro base di prezzo: token (per milione), immagine, secondo di
video, credito, minuto audio, carattere. Un asset 3D fatturato a crediti e una chiamata testuale
fatturata a token diventano **confrontabili** perché il registro normalizza entrambi in dollari.
È il presupposto del routing capability-aware: il filtro per **capacità precede** quello sul
prezzo — un modello privo della capacità richiesta non è confrontabile sul costo, per quanto
economico.

### 9.4 `measurement_source`: distinguere «zero» da «non lo so»

Un provider che non restituisce l'usage **non ha erogato un servizio gratuito**. Il record marca
quindi la provenienza della misura: `reported` (dichiarata dal provider), `derived` (ricavata da
un parametro contrattuale o dall'output), `missing` (non affidabile).

Un consumo non prezzabile diventa **evento**, non riga di costo. Conseguenza: non gonfia né
sgonfia il totale, resta visibile nel ledger, e il summary lo conta in `unpriced_count`. Senza
questa distinzione, una chiamata senza usage entrerebbe nel dataset del flywheel come *chiamata
gratis* — un dato falso che il router poi imparerebbe.

> **Nota metodologica (difetto reale, trovato in verifica).** Un modello del listino non
> dichiarava il prezzo dei token da cache. La prima risposta con prompt cache attiva — condizione
> **ordinaria**, non caso limite — faceva fallire la prezzatura *dopo* che la chiamata era stata
> pagata, e la run veniva archiviata con `total_cost: 0`. Una spesa reale, invisibile nei dati.
> La correzione ha agito su due livelli: il prezzo mancante (il dato) e il comportamento (la
> struttura) — ogni fallimento di prezzatura è ora un evento che **conserva le quantità
> osservate**, così il costo resta ricomputabile invece di sparire. È l'illustrazione concreta
> del perché §9.1 conta.

### 9.5 Il ledger per run: lo schema iniziale del dataset

```
runs/<run_id>/
  usage.jsonl    consumi prezzati, append-only, una riga per chiamata
  events.jsonl   fatti che NON sono consumi: errore provider, budget, usage non prezzabile
  summary.json   esito, durata, iterazioni, costo totale, costo per modello e per operazione
```

Tre scelte di design con conseguenze sui dati:

1. **Consumi ed eventi sono separati.** Un errore di provider o uno stop per budget non sono
   record di costo. Se lo fossero, il costo medio per chiamata risulterebbe falsato da righe a
   costo zero che chiamate non sono.
2. **Il summary è derivato rileggendo i JSONL**, non da un contatore parallelo. Un contatore
   sarebbe una **seconda fonte di verità** per lo stesso dato, e prima o poi divergerebbe.
3. **Nessun prompt, nessuna chiave.** Del task si conserva l'hash. Il costo di questa scelta è
   dichiarato: dal log non si può rileggere il testo del task. È una politica esplicita, non una
   dimenticanza.

### 9.6 Il budget guard e il suo limite intrinseco

Il tetto è espresso in **USD, mai in numero di passi**: una chiamata al modello frontier può
costare venti volte una chiamata al modello economico, quindi "massimo N passi" non è un budget.
Il controllo vive nel gateway, **prima** della chiamata, sul costo già osservato.

> **Il limite, da dichiarare in tesi.** Il costo di una chiamata si conosce solo **dopo** averla
> fatta. Il controllo pre-chiamata non può quindi impedire che l'ultima chiamata sfori il tetto:
> può solo impedire di farne un'altra. Con un solo agente **lo sforamento massimo è il costo di
> una singola chiamata**. Con N agenti che condividono un tetto, ciascuno può leggere «sotto
> soglia» prima che gli altri abbiano registrato la propria spesa: **lo sforamento massimo
> diventa la somma di N chiamate in volo**. Nelle campagne il tetto totale conta anche la spesa
> prenotata per le run in corso (D28), e lo sforamento torna a una chiamata per run; il tetto di
> squadra, che legge la spesa senza prenotazione, resta esposto al caso peggiore di N chiamate.
> Il costo di una chiamata non è un valore fisso (sui modelli frontier del pool, misurato, da
> $0,007 a $0,040): lo sforamento si dichiara come intervallo ed è riportato per ogni run
> (`overrun_usd`). Non è un difetto dell'implementazione: è una proprietà della fatturazione a
> consumo, che il parallelismo amplifica.

**Scelta metodologica deliberata:** alla soglia morbida il sistema **non inietta** messaggi nel
contesto del modello (del tipo *«concludi presto»*). Lo farebbe volentieri un prodotto; una
tesi no — altererebbe invisibilmente la politica dell'agente e sporcherebbe la baseline
sperimentale. Lo strumento di misura non deve perturbare l'oggetto misurato. Solo log ed evento.

### 9.7 Perché l'osservabilità viene PRIMA del routing

È la giustificazione dell'ordine `M2a → M2s → M3/M4 → M2b`, ed è difendibile al colloquio:

- **Senza contabilità non esiste né baseline né prova.** Il pilastro 3 (validazione) si regge
  sull'apparato di misura, quindi l'apparato viene prima.
- **Addestrare il router su dati di un agente singolo riprodurrebbe il limite che MasRouter
  denuncia** (§7): il routing classico è single-agent. Il dataset del router deve nascere da uno
  swarm reale, altrimenti il delta rivendicato dalla tesi si dissolve.
- Ne segue: prima si **misura**, poi si instrada per ruolo in modo statico (M2s), poi si
  costruisce lo **swarm** (M4), e solo allora si apprende il router (M2b) sui dati che lo swarm
  ha prodotto.

### 9.8 Limiti dichiarati della misura

Onestà metodologica — ciascuno è una risposta pronta a un'obiezione:

| Limite | Perché esiste | Come è trattato |
|---|---|---|
| Costi fissi (abbonamenti) esclusi dal costo per chiamata | Sono costi affondati: non variano con le scelte del router, quindi non devono influenzarle | Dichiarati a parte nel capitolo sperimentale (`monthly_fee`); ignorarli sottostimerebbe il costo di sistema |
| Costo **di listino**, non fatturato | Sconti, tier e minimi di fatturazione non sono modellati | Il confronto è fra sistemi sotto lo stesso listino, quindi il bias è comune a baseline e sistema |
| Sforamento residuo del budget | §9.6 | Quantificato e riportato per ogni run |
| Consumi non prezzabili | Provider che non dichiara l'usage, o unità senza listino | Il totale è una **sottostima nota e quantificata** (`unpriced_count`), non un valore silenziosamente sbagliato |

### 9.9 Dal claim al codice

| Ciò che la tesi afferma | Meccanismo che lo rende verificabile |
|---|---|
| «costa meno» | costo per chiamata, per modello, per operazione, per run |
| «a parità di qualità» | `finish_reason == length` = risposta troncata: segnale di qualità a costo zero, e motivo di escalation nella cascade |
| «riproducibile» | quantità grezze + hash del task + schema versionato → ricalcolo senza rieseguire |
| «il flywheel apprende» | `usage.jsonl` è già il formato del dataset di M2b |
| «il sistema è controllabile» | budget in USD con limite intrinseco dichiarato |

---

## 10. Rischi & domande aperte (per il colloquio)
1. **Valutazione open-ended**: il capitolo più rischioso (è ciò che OI-MAS evita con task verificabili).
2. **Bias del giudice** (self-preference) → contamina valutazione *e* training. Mitigazioni: panel, pairwise, position-swap, giudice terzo.
3. **Validità del soggettivo** → misurare l'accordo annotatori (kappa); rivendicare fino a quel soffitto. Il kappa richiede almeno due annotatori: **disponibili** (settembre 2026).
4. **Dati di training** → RLAIF + DPO a scala di tesi. Aggravante: un'etichetta soggettiva costa ~2,6× una deterministica ed è rumorosa (§5.11). Mitigazione: curva di apprendimento e apprendimento attivo.
5. **Obsolescenza modelli** → il flywheel (ri-valutazione ripetibile) + transfer dei router (RouteLLM).
6. **Granularità di decomposizione** → ottimo a U; come la stima il Planner?
7. **Rappresentatività del benchmark** → pochi task non generalizzano; metodologia > scala.
8. **Il giudice automatico non è affidabile sull'estetica se usato così com'è** (§5.10) → verifica contro gli umani prima dell'uso, criteri espliciti, addestramento sulle preferenze.
9. **Il costo del giudizio può superare il risparmio** (§5.11) → giudice economico, pochi candidati per slot, gate deterministico a monte.
10. **«Migliore» non è ancora definito** — bellezza, chiarezza o efficacia sono domande diverse con risposte diverse. È il primo problema aperto della ROADMAP, e condiziona tutti gli altri.
11. **τ ha due significati** — soglia sul singolo output (§5.6.4) e non-inferiorità di campagna. Va ancorata alla baseline (§5.11).
12. **Punti ciechi dello screenshot** — mobile, interazione, animazioni non compaiono in un'immagine ferma.
13. **Varianza fra esecuzioni** — lo stesso modello produce pagine diverse: decide quante ripetizioni servono.
14. **Una politica semplice raggiunge lo sciame** (D49) — se V o H costano quanto C a qualità pari, il risultato è
    «basta la verifica» o «basta il piano»: la tesi lo riporta come esito, non come fallimento (§0.2).
15. **Il cancello accetta siti che funzionano ma non piacciono** (D48) — un controllo eseguibile non vede
    l'aspetto. Si misura sulle coppie D-B dei compiti accettati; se la perdita su «piace» è grande, il cancello
    di C e V va completato con il critico visivo.
16. **Originalità del cancello eseguibile** — da verificare sulla letteratura della generazione web con verifica
    prima di rivendicarla (§7.3).

---

## 11. Glossario rapido
- **Cost-routing**: instradare ogni (sotto-)task al modello più economico che soddisfa τ. Dal 23 ottobre 2026 la
  tesi non lo fa prevedendo, ma verificando (D48).
- **Cancello eseguibile**: controllo gratuito sul sito prodotto (si avvia, nessun errore JavaScript, i test scritti
  dall'agente passano) che decide se tenere il lavoro dell'economico; non vede mai script né domande della
  valutazione (D48).
- **Cascata V**: politica «prima l'economico da solo, poi il forte da zero se il cancello rifiuta» (D49, §0.2).
- **Plan/Execute (H)**: politica di un agente singolo: il forte lavora fino alla prima scrittura di un file, poi
  passa all'economico con tutta la storia (D49, §7.3).
- **Scala di politiche**: B, D, V, H, C riportati sullo stesso piano costo-qualità; la prova principale resta
  C contro B (D49).
- **Replay**: rigiocare scelte o prezzi su tracce già registrate. Ricalcola un costo, non dice cosa sarebbe
  successo con un'altra scelta (§7.3).
- **Cascade**: prova cheap → escala su qualità insufficiente (scopre, non predice).
- **Reward model**: rete che assegna un punteggio di qualità appreso da preferenze.
- **DPO**: preference tuning diretto sulle coppie (no reward model separato, no RL).
- **RLHF/PPO**: reward model + reinforcement learning; **RLAIF**: feedback da AI invece che da umani.
- **LLM-as-a-judge**: modello forte che valuta output (pairwise / single / G-Eval).
- **Blackboard**: spazio condiviso da cui gli agenti leggono/scrivono (anti-mesh).
- **Pareto costo/qualità**: a parità di qualità, scegli il più economico (e viceversa).
- **kappa (Cohen/Fleiss)**: misura dell'accordo tra annotatori, **tolto quello dovuto al caso** (con due opzioni si concorda metà delle volte per fortuna) → soffitto di validità del soggettivo. Richiede almeno due annotatori.
- **Pilastro C**: resilienza/auto-correzione (errore → osservazione → riprova).
- **Ricomputabilità**: proprietà dei log che conservano le *quantità* e non solo i dollari → i
  costi si ricalcolano su dati storici quando cambia un listino, senza rieseguire nulla (§9.1).
- **`measurement_source`**: provenienza della misura di consumo — `reported` / `derived` /
  `missing`; distingue «zero» da «non lo so» ed evita che una chiamata senza usage entri nel
  dataset come gratuita (§9.4).
- **Ledger di run**: archivio append-only per singola esecuzione (`usage.jsonl` + `events.jsonl`
  + `summary.json`); è lo schema iniziale del dataset del flywheel (§9.5).
- **Sforamento residuo**: quanto una run può superare il tetto di budget — al massimo il costo di
  una singola chiamata con un agente solo, fino a N chiamate con N agenti che condividono un tetto
  senza prenotazione, perché il costo si conosce solo a chiamata avvenuta (§9.6).
- **Giudizio a coppie**: si mostrano due output dello stesso task senza dire chi li ha prodotti e si
  chiede quale sia migliore. Un giudizio = un confronto = una risposta, A oppure B (§5.2).
- **Curva di apprendimento**: accuratezza del router in funzione del numero di etichette. Dice quando
  aggiungere dati smette di servire (§5.11).
- **Apprendimento attivo**: generare nuovi esempi dove il modello è più incerto, invece che a caso.
  Riduce le etichette necessarie (§5.11).
