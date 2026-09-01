# ORC — Memoria completa della tesi (documento master)

> **Cos'è:** il dump definitivo di tutto ciò che abbiamo capito sulla tesi — fatti, scelte di
> design, stato dell'arte e **collegamenti profondi** ricavati ragionando. Companion tecnico:
> `M2_routing_design.md` (diagrammi dettagliati). Aggiornato: giugno 2026.

---

## 0. La tesi in una frase (e come ottimizzazione)

> *Un **sistema multi-agente** con **cost-routing** ottiene una **riduzione di costo significativa**
> **a parità di qualità** rispetto a una **baseline mono-modello**, su **task di software engineering**.*

Formulata come problema: **minimizza il costo, soggetto a qualità ≥ soglia τ.**
```
   min  Σ costo(modello_i)        s.t.   qualità(output) ≥ τ
```
Questa singola funzione obiettivo **unifica tutto il sistema**:
- il **router** sceglie il modello più economico con qualità attesa ≥ τ;
- la **cascade** escala quando la qualità misurata < τ;
- la **decomposizione** abbassa il costo necessario per raggiungere τ;
- la **valutazione** è ciò che *definisce e misura* τ.
Senza la metà "qualità ≥ τ", "minimizza il costo" è banale (scegli sempre il più scadente).

---

## 1. Le parti fondamentali (gerarchia)

```
            ┌──────────────── LA TESI ────────────────┐
   PILASTRI │ 1.Cost-routing   2.Valutazione   3.Validazione sperimentale │
   CO-CENTR.│        (stanno o cadono INSIEME)                            │
            └──────────────────────────────────────────────────────────┘
  SUBSTRATO │ 4.Architettura multi-agente  5.Decomposizione              │
            │ 6.Coordinamento/Blackboard   7.Resilienza (Pilastro C)     │
  SUPPORTI  │ 8.Sicurezza/isolamento  9.Contesto/RAG  10.Osservabilità   │
```
- **Routing**: la parte intelligente e affascinante (il "cosa" della ricerca).
- **Valutazione**: il "*a parità di qualità*" — co-centrale, la più difficile, dove il professore spingerà.
- **Validazione**: baseline vs sistema, variabili controllate → rende il lavoro **scienza**.
- L'errore classico: innamorarsi del routing e sotto-costruire la valutazione → claim infalsificabile.

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
  DAG delle dipendenze, indìce i review.
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

---

## 6. Pipeline completa (dal task al risultato + apprendimento)

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
| **DeLM** (2606.10662) | Contesto condiviso **verificato** + coda di task; memoria gerarchica (gist → summary → grezzo) con srotolamento su richiesta; gate di ammissione. **SWE-bench Verified 77.4% pass@4 vs 73.2%, a $0.12/task ≈ metà dei baseline** | **Il vicino più stretto**: stessa forma di claim (meno costo, non meno qualità) sullo stesso dominio. Da leggere per intero. Se ne prende il **gate di ammissione** e l'idea dei riferimenti compatti; il delta va ridefinito rispetto a lui |
| **FlyRoute** (2605.22057) | Profili di capacità degli agenti **auto-evolventi** via data flywheel, per instradamento adattivo | Prior più vicino sull'idea di *competenze apprese* invece che dichiarate. **Da leggere prima di rivendicare novità** su quel punto |
| **LLM-as-a-Verifier** (2607.05391, Stanford) | Punteggi continui dall'attesa sui **logit** invece del voto intero; *Probabilistic Pivot Tournament*: ordina N candidati in **O(Nk)** anziché O(N²) | Risolve i **pareggi** che affliggono i giudici a scala 1-5, e rende economico il confronto fra molti candidati. Materiale diretto per il Judge L2 |
| **GoAgent** (2603.19677) | Genera la **topologia di comunicazione** trattando i gruppi come unità atomiche; information bottleneck sulla comunicazione fra gruppi. −17% token | Ortogonale: loro instradano *l'informazione fra agenti*, la tesi instrada *il task verso il modello*. Utile come contrasto, non come concorrente |
| **Blackboard LLM** (2510.01285) | Lavagna a **volontariato**: l'agente centrale pubblica, i subordinati si auto-candidano per capacità. +13-57% di successo end-to-end | Versione 2026 dell'idea di lavagna. **Non adottata** (§7.2), ma va citata: risolve un problema — il coordinatore che ignora le capacità — che qui non si pone perché il registro le conosce per costruzione |
| **Comunicazione latente** (2606.05711) | Gli agenti si scambiano embedding / hidden state / KV-cache invece di testo | **Non applicabile**: richiede accesso agli interni del modello, impossibile con API commerciali. Da citare come direzione futura |
| **Survey protocolli** (2505.02279) | MCP, A2A, ACP, ANP: interoperabilità fra agenti di organizzazioni diverse | Non adottati: gli agenti sono tutti dello stesso sistema, nello stesso processo |
| **Agentic plan caching** (2506.14852) | Riuso dei piani fra task simili; la fase di pianificazione è la maggior parte del costo di calcolo | Rilevante perché nel sistema instradato **l'orchestratore diventa la voce di costo dominante**: qualunque leva sul planner domina le altre |

### 7.2 Tre rivendicazioni aggiuntive, emerse dalla rassegna

Tutte e tre sono misurabili con l'infrastruttura già costruita in M2a.

1. **Il routing ha due dimensioni.** Non solo *quale modello*, ma *attraverso quale
   percorso*. Verificato: la prompt cache non sopravvive al passaggio da un
   aggregatore, e lo **stesso modello** arriva a costare **2,25×**. La letteratura
   sul cost-routing assume accesso diretto alle API e non modella la seconda
   dimensione; i campi `api_provider` e `billing_provider` dello `UsageRecord`
   permettono di misurarla.
2. **Token e dollari non sono la stessa metrica.** Dove la cache è attiva i token
   ripetuti costano un decimo, quindi una riduzione del 17% dei token vale ~2,5%
   della spesa. Le due misure divergono di un ordine di grandezza **esattamente nel
   punto in cui la letteratura riporta i propri risultati**.
3. **CPT-τ — costo per task completato a qualità ≥ τ.** Ogni lavoro censito riporta
   costo *e* qualità come due numeri accostati; nessuno li riporta come uno solo
   vincolato. È la funzione obiettivo di §0 scritta nella forma in cui si misura, e
   assorbe quattro cose oggi relegate alle note: i tentativi economici falliti, il
   costo dell'escalation, l'overhead di coordinamento, i task che a τ non arrivano.

> ⚠️ Sono **candidate**, non risultati acquisiti. Prima di rivendicarle vanno letti
> per intero DeLM e FlyRoute, che sono i due lavori in grado di anticiparle.

---

**Gap difendibile:** cost-routing in uno **swarm di coding-agent** su **artefatto condiviso**, con
valutazione **execution-based + multimodale** del soggettivo, flywheel cascade→router, e isolamento/sicurezza.
A cui la rassegna 2026 aggiunge la misura del **percorso** oltre che del modello, e una
metrica congiunta di costo e qualità.

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
- **M2s IN CORSO — instradamento statico per ruolo** (2 task su 4):
  - *M2s.1* ✅ ruoli in `models.toml` (`planner` → modello frontier, `worker` →
    modello economico) con le capacita' che ogni mestiere richiede; il registro
    **verifica al caricamento** che il modello assegnato le possieda, quindi
    un'assegnazione sbagliata fallisce all'avvio e non a meta' di una run pagata.
  - *M2s.2* ✅ percorso **diretto** ai fornitori e secondo gateway. Il contratto
    fra gateway e agente, fino a qui implicito nella forma dell'SDK OpenAI, e'
    stato reso esplicito: `Agent` lavora su tipi del progetto e il secondo
    fornitore e' entrato **senza toccarlo**. E' la verifica sul campo della
    proprieta' che rende possibile lo swarm.
  - *M2s.3* ⬜ fabbrica di agenti · *M2s.4* ⬜ prima misura reale.
- **138 test verdi**, nessuno dei quali tocca la rete o consuma budget; CI su ogni
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
> può solo impedire di farne un'altra. **Lo sforamento massimo possibile è il costo di una
> singola chiamata**, ed è riportato nel report (`overrun_usd`). Non è un difetto
> dell'implementazione: è una proprietà del modello di fatturazione a consumo.

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
3. **Validità del soggettivo** → misurare l'accordo annotatori (kappa); rivendicare fino a quel soffitto.
4. **Dati di training** → RLAIF + DPO a scala di tesi (supporto università per il set umano di calibrazione?).
5. **Obsolescenza modelli** → il flywheel (ri-valutazione ripetibile) + transfer dei router (RouteLLM).
6. **Granularità di decomposizione** → ottimo a U; come la stima il Planner?
7. **Rappresentatività del benchmark** → pochi task non generalizzano; metodologia > scala.

---

## 11. Glossario rapido
- **Cost-routing**: instradare ogni (sotto-)task al modello più economico che soddisfa τ.
- **Cascade**: prova cheap → escala su qualità insufficiente (scopre, non predice).
- **Reward model**: rete che assegna un punteggio di qualità appreso da preferenze.
- **DPO**: preference tuning diretto sulle coppie (no reward model separato, no RL).
- **RLHF/PPO**: reward model + reinforcement learning; **RLAIF**: feedback da AI invece che da umani.
- **LLM-as-a-judge**: modello forte che valuta output (pairwise / single / G-Eval).
- **Blackboard**: spazio condiviso da cui gli agenti leggono/scrivono (anti-mesh).
- **Pareto costo/qualità**: a parità di qualità, scegli il più economico (e viceversa).
- **kappa (Cohen/Fleiss)**: misura dell'accordo tra annotatori → soffitto di validità del soggettivo.
- **Pilastro C**: resilienza/auto-correzione (errore → osservazione → riprova).
- **Ricomputabilità**: proprietà dei log che conservano le *quantità* e non solo i dollari → i
  costi si ricalcolano su dati storici quando cambia un listino, senza rieseguire nulla (§9.1).
- **`measurement_source`**: provenienza della misura di consumo — `reported` / `derived` /
  `missing`; distingue «zero» da «non lo so» ed evita che una chiamata senza usage entri nel
  dataset come gratuita (§9.4).
- **Ledger di run**: archivio append-only per singola esecuzione (`usage.jsonl` + `events.jsonl`
  + `summary.json`); è lo schema iniziale del dataset del flywheel (§9.5).
- **Sforamento residuo**: quanto una run può superare il tetto di budget — al massimo il costo di
  una singola chiamata, perché il costo si conosce solo a chiamata avvenuta (§9.6).
