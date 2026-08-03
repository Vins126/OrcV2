# ORC — M2: Cost-Routing & Valutazione (documento di lavoro per il colloquio)

> Stato: M1 completo (agente singolo robusto, sandbox Docker, resilienza, test).
> Questo documento raccoglie il ragionamento di design su **M2 (cost-routing)** e sul
> **problema della valutazione della qualità**, con architettura attuale e futura.

---

## 1. Il problema e l'obiettivo della tesi

Oggi ogni task va su **un modello fisso** = **baseline mono-modello** (il termine di paragone).
La tesi sostiene: **5-10x di riduzione dei costi a parità di qualità** instradando ogni
(sotto-)task al **modello più economico capace di farlo**.

Frase chiave: **"più economico A PARITÀ DI QUALITÀ"**. Spendere meno è banale (un modello
debole costa poco ma fallisce). Il contributo è cost-routing **senza** perdita di qualità.
Quindi M2 ha due metà inseparabili:
1. **Router** — *decide* quale modello.
2. **Contabilità costi + valutazione qualità** — *misura* e *dimostra* il risparmio.

---

## 2. Strategie di routing (mappa ragionata)

| Strategia | Idea | Pro | Contro |
|---|---|---|---|
| Keyword/euristica | regole ("css"→cheap) | gratis, deterministica | fragile, ingenua |
| LLM-classifier | un modello classifica il task | flessibile | costo/latenza, coarse |
| **Cascade/escalation** | prova cheap → escala se la qualità non basta | non *predice*, *scopre*; paghi il forte solo se serve | serve un **giudice** di qualità |
| **Router appreso (reward model)** | mini-modello addestrato a predire la scelta migliore | economico a runtime, preciso | **serve dataset**, invecchia coi modelli |
| Capability-aware | filtra per capacità richieste (vision/contesto/tool) | multidimensionale (vero) | va combinato con un criterio di costo |
| Role-based | meta=forte, worker=economici | semplice ed efficace | grossolano da solo |

**Perché NON i "tier":** comprimono la scelta su un asse (facile↔difficile), ma la realtà è
**multidimensionale** (es. "facile ma serve vision", "serve contesto lungo"). Vista corretta:
**capacità richieste (filtro hard)** + **frontiera di Pareto costo/qualità**. I tier al massimo
restano un *prior morbido*, non il meccanismo.

---

## 3. Il fattore swarm (cambia il problema)

Quando diventa uno swarm di agenti:
- **La difficoltà di un sotto-task la DETERMINA la decomposizione.** Decomporre bene → foglie
  semplici → modelli economici. Quindi conta routare **ogni sotto-task quando nasce** (routing
  dinamico per-foglia), non classificare il task originale a monte.
- **Routing per ruolo:** meta-agente (pianifica/decompone/valida) → modello forte; worker → economici.
- **Topologia:** NO mesh (comunicazione O(N²) = caos, conflitti, chiacchiericcio). SÌ
  **gerarchico + Blackboard** (spazio condiviso) per coordinare senza N² messaggi.

---

## 4. Architettura PROPOSTA (idea iniziale) e sue criticità

**Idea:** modello forte decompone in tanti sotto-task → un mini-LLM addestrato assegna il
modello migliore a ciascuno → l'agente iniziale spawna lo swarm (mesh).

**Criticità individuate:**
1. **"Più sotto-task possibile" è sbagliato** → costo/latenza esplodono, overhead di
   coordinamento super-lineare, frammentazione del contesto, meno parallelismo. Obiettivo
   corretto: **granularità ottimale** (pezzi grandi quanto basta perché un cheap li chiuda).
2. **La decomposizione è il collo di bottiglia fragile** → va **validata**, con ri-decomposizione
   sugli errori. Non è one-shot.
3. **Router addestrato:** ottimo l'istinto di un modello **piccolo/dedicato/veloce**, ma:
   - **i dati di training** (task → modello migliore + costo + qualità) sono costosi da generare;
   - **predire** a priori è più difficile che **scoprire** (cascade);
   - i modelli **cambiano di continuo** → il router invecchia → serve ri-training ripetibile.
4. **Mesh** → sostituire con **gerarchico + Blackboard**.
5. **Ruoli confusi** → separare: **Planner/Decompositore · Router · Orchestratore · Worker ·
   Integratore**. Flusso **iterativo** (worker → valida → ri-delega), non lineare.

---

## 5. L'idea unificante (proposta forte per la tesi)

Cascade e router appreso **non sono alternative, si alimentano**:

1. **Cascade** (cheap-first, escala se la qualità non regge) → funziona subito, batte la baseline,
   e **mentre gira logga**: per ogni sotto-task quale modello ce l'ha fatta e a che costo/qualità.
2. Quei log **sono il dataset etichettato** → si **addestra il router** (reward/preference model).
3. Il router fa il primo tiro intelligente; la cascade resta come **rete di sicurezza**.

Narrazione di tesi a stadi misurabili:
**baseline mono-modello → cascade → router appreso**, con il miglioramento misurato a ogni stadio.

> Nota tecnica: il "mini-LLM addestrato con uno score" = **reward modeling / preference learning**
> (famiglia RLHF). Si apprende meglio da **confronti a coppie** che da punteggi assoluti.

---

## 6. Il nodo VALUTAZIONE (il vero problema di ricerca)

Per modelli ormai capaci, "errore/non errore" è un segnale piatto: il discriminante è la
**qualità**, multidimensionale e in parte **soggettiva** (es. "gusto" estetico del frontend).
Quindi il giudice della cascade è un **valutatore di qualità**, non un rilevatore di errori.

**La qualità è un VETTORE, per-categoria** (non un numero unico):

| Tipo task | Metriche oggettive (auto, gratis) | Metriche soggettive (giudice) |
|---|---|---|
| Frontend | build, **Lighthouse** (perf/a11y), **axe-core**, bundle size | gerarchia visiva, spaziatura, colori, coerenza |
| Backend/logica | test pass@k, type-check, lint, complessità, performance | leggibilità, idiomaticità |
| Refactor | test ancora verdi, complessità ↓, dimensione diff | "pulizia" percepita |
| Trasversali | **costo** (token×prezzo), latenza, completamento autonomo | — |

Anche il "gusto" ha **proxy oggettivi** (Lighthouse/axe) → catturane una fetta gratis prima di
ricorrere al soggettivo.

**Come valutare il soggettivo:**
- **LLM-as-a-judge** su rubrica (1-5). Attenzione ai **bias** (position, verbosity, **self-preference**).
- **Giudice multimodale su screenshot** (per il frontend → operazionalizza il "gusto"; usa i tool vision/browser).
- **Confronto a coppie (pairwise)**: più affidabile dei voti assoluti, e dà **ranking** (ciò che serve al router).
- **Umani**: gold standard del soggettivo, usati per **calibrare** il giudice automatico su un piccolo campione (qui può aiutare l'università).

**Punto che salva il piano:** la valutazione costosa avviene **OFFLINE** (creazione dataset),
il router a runtime è economico (niente giudice in produzione).

**Benchmark-harness (metodologia):** stesso set di task (per categoria) eseguito su più modelli;
si salvano **tutte** le metriche (oggettive + giudizio pairwise + costo + latenza) → dataset
comparativo → si addestra il reward/router → si calibra il giudice contro umani.

**Rischi da dichiarare:** definire la **rubrica/metriche** È il contributo (e la parte dura);
**bias del giudice** (specie self-preference) contamina valutazione e training; **rappresentatività/
overfitting** (pochi task non generalizzano); **modelli che cambiano** → pipeline di ri-valutazione ripetibile.

---

## 7. Architettura ATTUALE (M1, implementata e testata)

```
                ┌──────────────────────────────┐
                │        LLM (proxy LiteLLM)    │  1 modello fisso = BASELINE
                └───────────────┬──────────────┘
            (3) osservazione    │   ▲ (1) decide (ReAct)
                    ▼           │   │
                ┌──────────────────────────────┐
                │   Agent (classe, DI)          │
                │   - loop ReAct + max iter      │
                │   - retry + backoff (resilienza)│
                │   - loop detection (escalation) │
                │   - errori → osservazioni       │
                └───────────────┬──────────────┘
                   (2) esegui    │   ▲ risultato
                                 ▼   │
                ┌──────────────────────────────┐
                │   Tools (ABC/Strategy)         │
                │   • bash → DockerExecutor       │ sandbox: --network none,
                │   • read/write → Workspace      │ non-root, read-only, effimero
                │                                 │ + guardia path-traversal
                └──────────────────────────────┘

   Config centralizzata · logging professionale · test pytest · requirements pinnati
```

## 8. Architettura FUTURA (ipotesi M2→M4)

```
                         TASK utente
                            │
                            ▼
                  ┌────────────────────┐
                  │ PLANNER / DECOMPOS. │  modello FORTE
                  │ granularità ottimale│  (decomposizione VALIDATA)
                  └─────────┬──────────┘
                            │ sotto-task + DAG di dipendenze
                            ▼
   ┌────────────────────┐   consulta   ┌──────────────────────────────┐
   │      ROUTER         │◄────────────│ REWARD/ROUTER model           │
   │ (per sotto-task)    │             │ addestrato OFFLINE su dataset │
   │ capacità → Pareto   │             │ comparativo (benchmark)       │
   └─────────┬──────────┘             └──────────────────────────────┘
             │ modello scelto per ogni sotto-task
             ▼
   ┌────────────────────┐
   │   ORCHESTRATORE     │  assegna i sotto-task (per ruolo), governa il DAG (wave),
   │   (tech-lead)       │  indìce i checkpoint di review
   └─────────┬──────────┘
       ┌──────┼───────┐
       ▼      ▼       ▼
   ┌──────┐┌──────┐┌──────┐
   │Worker││Worker││Worker│   ogni worker = Agent (M1) + modello (dal ROUTER) + sandbox
   │ (FE) ││ (BE) ││(test)│   specializzati per ruolo
   └───┬──┘└───┬──┘└───┬──┘
       │ scrivono/leggono INCREMENTALMENTE │
       └───────────┼───────────────────────┘
                   ▼
   ┌───────────────────────────────────────────┐
   │  WORKSPACE CONDIVISO ("il repo") +          │  il progetto cresce QUI, in modo
   │  BLACKBOARD (interfacce, convenzioni,       │  incrementale. NIENTE fan-in/merge
   │  contratti → evitano collisioni)            │  finale dei risultati.
   └───────────────────────────────────────────┘
                   ▲
                   │ a checkpoint
   ┌────────────────────┐
   │ REVIEW / VALIDAZIONE │  "direzione giusta? builda? test verdi?" → ri-delega se serve
   │  (sync + DevOps gate)│  NON fonde gli output: VALIDA l'insieme
   └────────────────────┘

   ▸ Topologia: artefatto condiviso che cresce + checkpoint di review (come un team su git),
     NON Map-Reduce con merge finale. Ispirazione: MetaGPT / ChatDev (team-azienda simulati).
   ▸ Conflitti su file condivisi → risoluzione incrementale (stile git), non merge monolitico.
   ▸ CASCADE come rete di sicurezza: worker sotto-soglia di qualità → escala modello.
   ▸ CONTABILITÀ COSTI: token×prezzo per ogni chiamata → confronto vs baseline.
```

## 9. Pipeline di valutazione/addestramento (offline)

```
  TASK SET (per categoria)
        │  esegui ogni task su PIÙ modelli/config
        ▼
  RACCOLTA METRICHE
    • oggettive: build, test pass@k, lint, Lighthouse/axe, COSTO, latenza
    • soggettive: LLM-judge / giudice multimodale su screenshot / PAIRWISE
    • calibrazione su piccolo set UMANO
        ▼
  DATASET COMPARATIVO  (feature task → qualità & costo per modello)
        ▼
  ADDESTRA REWARD/ROUTER  (preference learning)
        ▼
  ROUTER A RUNTIME  (economico, nessun giudice in produzione)
```

---

## 10. Domande aperte da discutere col professore
1. Definizione rigorosa delle **metriche di qualità per categoria** (specie il soggettivo).
2. Validità del **giudice automatico** e mitigazione dei bias (calibrazione umana, pairwise).
3. **Generazione del dataset** (compute/annotatori — supporto università?).
4. Strategia contro l'**obsolescenza** dei modelli (pipeline ri-valutazione).
5. Scelta tra cascade-only, router-only, o l'ibrido a stadi (qui proposto).

## 11. Riferimenti da approfondire (related work)
FrugalGPT (cascade) · RouteLLM (router appreso) · AutoMix · Hybrid LLM · LLM-as-a-judge
(Zheng et al. 2023) · G-Eval · MT-Bench / Chatbot Arena (Elo, pairwise) · reward modeling (RLHF)
· SWE-bench / pass@k · WebArena · Lighthouse / axe-core · Mixture-of-Agents · Blackboard pattern
· **MetaGPT** (azienda software simulata, SOP + documenti condivisi) · **ChatDev** (team di ruoli a fasi)
· **OI-MAS** (arxiv 2601.04861) · **MasRouter** (arxiv 2502.11133).

---

## 12. Stato dell'arte aggiornato (ricerca 2024-2026)

### 12.1 Routing & cascade (mono-agente)
- **RouteLLM** (Ong et al., 2024) — addestra un router da **dati di preferenza** per scegliere tra
  modello forte/debole (decisione binaria). Risultato chiave: **i router generalizzano tra coppie
  di modelli senza ri-addestramento** (es. trained su GPT-4/Mixtral → funziona su Claude/Llama).
  → risponde in parte alla tua paura "i modelli cambiano di continuo". arxiv 2406.18665
- **FrugalGPT** (Chen et al.) — router + stimatore di qualità a soglia + stop judge; **cascade**;
  fino a **98% di riduzione costi**. È esattamente il tuo "cheap-first, escala". 
- **Survey: Dynamic Model Routing and Cascading for Efficient LLM Inference** — rassegna completa
  (perfetta per related work). arxiv 2603.04445
- **UCCI** — cascade routing con **incertezza calibrata** (come decidere quando escalare). arxiv 2605.18796
- Distinzione netta: **cascade** = più query, escala; **routing** = una query, scelta a monte.

### 12.2 Routing MULTI-AGENTE (il TUO scenario — il più rilevante)
- **MasRouter: Learning to Route LLMs for Multi-Agent Systems** — osserva che i metodi di routing
  esistenti sono **single-agent e NON pronti per i MAS**. È il tuo prior work più vicino: da leggere
  per definire il tuo *delta*. arxiv 2502.11133
- **OI-MAS — Confidence-Aware Routing across Multi-Scale Models** — routing *state-dependent* di
  ruoli-agente e scala-modello, con meccanismo confidence-aware: **+12.88% accuratezza, -79.78% costo**.
  ⚠️ Numeri quasi sovrapponibili alla tua tesi → da conoscere assolutamente (baseline da battere
  e/o validazione della direzione). arxiv 2601.04861
- **Towards Generalized Routing: Model and Agent Orchestration** — routing congiunto modello+agente
  per un **pool di modelli eterogeneo e in crescita** (di nuovo: il problema "nuovi modelli"). arxiv 2509.07571
- **Difficulty-Aware Agent Orchestration** — orchestrazione in base alla difficoltà. arxiv 2509.11079

### 12.3 Valutazione / LLM-as-a-judge
- Survey (Gu et al. 2025): giudici tipo GPT-4 allineati agli umani **>80%**, ma con bias
  (position, verbosity, **self-enhancement**, variabilità stocastica) → servono mitigazioni.
- **An Empirical Study of LLM-as-a-Judge: How Design Choices Impact Reliability** — arxiv 2506.13639
- **EvalGen** — raffina i prompt di valutazione con **human-in-the-loop**, affronta il *criteria drift*.
- Studi su scoring/shortcut bias e "curse of knowledge" → da citare per la validità del giudice.

### 12.4 Reward modeling & valutazione del codice
- **Beyond Scalar Reward Model: Learning Generative Judge from Preference Data** — arxiv 2410.03742
- **Rethinking Rubric Generation for LLM Judge & Reward Modeling (open-ended)** — affronta proprio
  il TUO problema "come definire le rubriche/metriche del soggettivo".
- **BigCodeArena / BigCodeReward** — preferenze umane affidabili sul codice **via ESECUZIONE**
  (← conferma: per il codice le metriche oggettive/esecuzione battono il giudizio testuale). arxiv 2510.08697
- **ELHSR** — reward head **lineare e leggero** su LLM congelato → reward model economico
  (supporta il tuo istinto "modello router piccolo/dedicato").
- **Multimodal judge bias mitigation** (perceptual perturbation + reward modeling) — rilevante per il
  tuo **giudice multimodale su screenshot** del frontend. arxiv 2606.02578

### 12.5 Posizionamento della tesi (gap)
La gran parte del routing è **single-agent**; il routing **multi-agente** (MasRouter, OI-MAS) è
recentissimo e ancora aperto. Angolo difendibile per la tua tesi:
**cost-routing in uno swarm di CODING agents**, con (a) pipeline *cascade → genera dataset → router
appreso*, (b) valutazione **execution-based + multimodale** specifica per il dominio coding/frontend,
(c) misura a stadi (baseline → cascade → router). Leggere MasRouter e OI-MAS per definire il delta esatto.

---

## 13. Confronto diretto con OI-MAS (arxiv 2601.04861) — il "vicino di casa"

**Cosa fa OI-MAS:** router **a due stadi appreso via RL** — una rete sceglie *quali ruoli*
(Generator/Refiner/Verifier…), un'altra *quale scala di modello* (Qwen 3B/7B, Llama 8B/70B).
"Confidence-aware" = usa la **log-probability** dei token come segnale di complessità (confidenza
bassa → escala). Reward = **correttezza (1/0) + costo pesato**. Topologia **sequenziale** (ruoli in
fila per ~4 turni, contesto via stato; nessun blackboard). Domini: math/QA/medical + coding
**a funzione singola** (MBPP/HumanEval). Risultati: **+fino a 12.88% accuratezza, −17÷78% costo**.

### Similitudini (da dichiarare onestamente)
- Stessa tesi: routare per complessità → risparmio a parità di qualità.
- **Router appreso con uno score** (loro RL: correttezza+costo ≈ il mio reward/preference model).
- **Escalation per confidenza** ≈ la mia **cascade** (loro: logprob; io: giudizio di qualità).
- Ruoli + decomposizione; pool multi-scala; routing per sotto-task; misura costo+accuratezza+latenza.

### Differenze (il mio delta)
| Aspetto | OI-MAS | Questa tesi |
|---|---|---|
| Dominio/task | risposta **verificabile** (math/QA, funzioni singole con unit test) | **software open-ended** multi-file, frontend con estetica |
| Reward/eval | **correttezza binaria** (ground-truth) | qualità **non binaria/soggettiva** → judge/multimodale/execution, calibrato su umani |
| Topologia | **sequenziale**, contesto via stato, no artefatto condiviso | **swarm su artefatto condiviso** che cresce (modello team-su-git) + checkpoint |
| Pool modelli | open piccoli (3B-70B) self-hosted | **commerciali eterogenei** via proxy (+ tema "nuovi modelli") |
| Sicurezza | **limite dichiarato** (no safety, unsafe tool use) | **sandbox Docker + guardie** già implementate |
| Orizzonte lungo | **limite dichiarato** (no memory mgmt) | **workspace condiviso persistente** = memoria del progetto |

### Posizionamento (messaggio per il colloquio)
OI-MAS **valida la direzione** ma in un **regime diverso** (task verificabili, sequenziale, modelli
open, no safety/artefatto condiviso). Questa tesi occupa lo spazio **più difficile e meno esplorato**:
SE open-ended, swarm su artefatto condiviso, modelli commerciali eterogenei, valutazione
**execution-based + multimodale** (incluso il soggettivo), con isolamento/sicurezza — affrontando
**due limiti che gli autori stessi dichiarano** (safety e memoria a lungo orizzonte).

⚠️ **Punto critico:** la **valutazione open-ended** è dove la difesa sarà più dura — è esattamente
ciò che OI-MAS evita usando task verificabili. È il capitolo più rischioso e più importante.

