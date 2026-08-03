# Presentazione proposta di tesi — contenuto slide (denso, autosufficiente)

> Uso: ogni slide è leggibile da sola (anche come materiale di studio). Sotto ogni slide,
> "💬 da dire a voce" = i passaggi/transizioni da raccontare a parole. Lingua: italiano.
> Da trasferire su Canva (vedi nota finale).

---

## Slide 1 — Titolo
**ORC — Orchestrazione e Cost-Routing di LLM per lo sviluppo software**
*Un sistema multi-agente che instrada ogni task al modello più economico capace di svolgerlo, a parità di qualità.*

- Vincenzo Mattioli — matricola 123014
- Relatore: Prof. Corradini
- Proposta di tesi di Laurea

💬 *"Vorrei proporle una tesi su come rendere economicamente sostenibili gli agenti di intelligenza artificiale per la programmazione."*

---

## Slide 2 — Contesto: cos'è un "agente LLM"
- Un **LLM** (es. GPT, Claude) di base **predice testo**: non agisce e non ha memoria.
- Un **agente** = LLM **+ strumenti (tool) + un ciclo**: *ragiona → agisce → osserva* (pattern **ReAct**).
- Con i tool (shell, lettura/scrittura file) l'agente **scrive ed esegue codice in autonomia**, correggendosi dagli errori.
- Esempi reali oggi: **Claude Code, Cursor, GitHub Copilot Agent**.

💬 *Spiega il loop con un esempio: "gli chiedo di creare un file, lui esegue un comando, vede il risultato, e decide la mossa successiva — come un programmatore."*

---

## Slide 3 — Il problema: potenza ⟷ costo
- Gli agenti più capaci usano i **modelli più costosi** (es. i modelli "frontiera").
- Ma usano il modello **top per OGNI passo**, anche per quelli **banali** (rinominare un file, scrivere CSS).
- Risultato: **spreco enorme**. Il costo è **la barriera** all'adozione reale.
- Intuizione: come in un'azienda **non mandi il senior architect a fare ogni micro-task**.

💬 *"Pagare il modello più potente per compiti banali è come pagare un ingegnere senior per spostare file. Il costo esplode senza motivo."*

---

## Slide 4 — L'idea della tesi (in una frase)
**Cost-routing:** instradare ogni (sotto-)task al **modello più economico capace di svolgerlo**.

Formulato come ottimizzazione:
> **minimizza il costo, a condizione che la qualità ≥ soglia τ**

- Obiettivo: **forte riduzione dei costi a PARITÀ di qualità** (riferimenti in letteratura: 5-10×, fino a ~80%).
- Nota cruciale: senza il vincolo "qualità ≥ τ", minimizzare il costo è banale (scegli sempre il più scadente).

💬 *"Il cuore non è 'spendere meno' — è 'spendere meno mantenendo la qualità'. Quella seconda metà è la parte difficile."*

---

## Slide 5 — Perché non è banale: i 3 pilastri
La tesi sta o cade su **tre parti inseparabili**:
1. **Routing** — *decide* quale modello (la parte intelligente).
2. **Valutazione della qualità** — *misura* la qualità → è il "a parità di qualità". **La più difficile.**
3. **Validazione sperimentale** — *dimostra* il risparmio vs una baseline → rende il lavoro **scienza**.

> Il routing fa una *affermazione*, la valutazione la *misura*, gli esperimenti la *provano*.

💬 *"Molti si fermano al routing. Ma se non so misurare la qualità, la mia affermazione non è dimostrabile. Per questo metto la valutazione al centro."*

---

## Slide 6 — Architettura: un "team su un repository"
- Un **Planner** (modello forte) **decompone** il task in sotto-task (alla granularità giusta).
- Un **Router** assegna a ogni sotto-task il **modello più adatto/economico**.
- **Worker specializzati** (ruoli: frontend, backend, test) lavorano in parallelo su un **workspace + blackboard condiviso**.
- Il progetto **cresce incrementalmente** (come un repo git), con **checkpoint di review/validazione** — **NON** si fondono output alla fine.
- Ispirazione: come lavora un **team umano** (e i sistemi MetaGPT / ChatDev).

💬 *"Non è 'spezza e poi incolla tutto'. È un team che contribuisce a un progetto condiviso che cresce, con momenti di revisione — esattamente come degli sviluppatori veri."*

---

## Slide 7 — Il meccanismo che apprende: cascade → flywheel → router
- **Cascade:** prova prima il modello **economico**; se la qualità non basta, **escala** a uno più forte. (Non *predice* la difficoltà: la *scopre*.)
- Mentre gira, **registra**: per ogni task, quale modello ha funzionato e a che costo/qualità → **dataset**.
- Su quei dati si **addestra un router leggero** che impara la **frontiera di Pareto** (miglior qualità/prezzo).
- È un **volano (flywheel)**: più gira → più dati → router migliore → costi più bassi. E **si auto-aggiorna** quando escono modelli nuovi.

💬 *"Il sistema migliora da solo col tempo, e non invecchia: quando esce un modello nuovo, lo prova e re-impara."*

---

## Slide 8 — Il nodo difficile: valutare la qualità
- Per il software **open-ended** non esiste "una risposta giusta" → metriche testuali classiche (BLEU/ROUGE) **falliscono**.
- I modelli moderni sbagliano poco: il discriminante è la **qualità**, spesso **soggettiva** (es. il "gusto" estetico di un frontend).
- **Metodo proposto:**
  - **Oggettivo (gratis):** build ok? test passano (pass@k)? lint, **Lighthouse/axe** (perf/accessibilità), costo, latenza.
  - **Soggettivo → preferenze:** **LLM-as-a-judge** con **confronti a coppie** (più affidabili dei voti assoluti), mitigando i bias (posizione, lunghezza, auto-preferenza).
  - **Validità:** misurare l'**accordo tra valutatori** (kappa) → si rivendica qualità fino a quel "soffitto".

💬 *"La parte rischiosa è proprio questa, e voglio affrontarla con rigore: dove esistono metriche oggettive le uso; per il soggettivo lo trasformo in preferenze e ne misuro l'affidabilità."*

---

## Slide 9 — Come si "impara" la qualità (e il router)
- La soggettività si quantifica come **preferenza** (A è meglio di B) — è così che i modelli di frontiera hanno imparato il "gusto" (**RLHF / DPO / RLAIF**).
- Stessa tecnica per me: i giudizi (anche generati da un modello forte = **RLAIF**) → un **reward model** addestrato via **DPO** (economico, fattibile a scala di tesi).
- I giudizi paralleli si uniscono con: **gate hard** (safety/capacità = ON/OFF, non mediabili) + **sintesi** dei criteri soft (Bradley-Terry, non media di voti assoluti).
- Il **Router** finale è **leggero** (embedding + testa di classificazione), con scoring **per coppia (prompt, modello)** → robusto ai modelli nuovi.

💬 *"Non rifaccio l'addestramento miliardario dei grandi laboratori: uso feedback AI + DPO, sostenibili per una tesi."*

---

## Slide 10 — Stato dell'arte e il mio contributo
- **Esiste già** ricerca vicina (2024-2026): **OI-MAS**, **MasRouter** (routing multi-agente), **RouteLLM**, **FrugalGPT** (cascade), **MetaGPT/ChatDev** (team simulati).
- Ma operano in un **regime diverso:** task a **risposta verificabile** (matematica/quiz), topologia sequenziale, modelli open; **senza** sicurezza né artefatto condiviso.
- **Il mio gap (poco esplorato):** cost-routing in uno **swarm di coding open-ended**, su **artefatto condiviso**, con valutazione **execution-based + multimodale** e **isolamento/sicurezza** — affrontando due limiti che quei lavori **dichiarano** (safety e memoria a lungo orizzonte).

💬 *"Non parto dal nulla né reinvento la ruota: mi colloco nello spazio più difficile e meno coperto."*

---

## Slide 11 — Cosa ho già costruito (non è solo teoria)
Ho già implementato e **testato** un **agente singolo robusto** (la base su cui costruire lo swarm):
- ciclo **ReAct**, **auto-correzione** dagli errori, rilevamento dei loop;
- **sandbox di sicurezza Docker** (niente rete, niente privilegi root, filesystem isolato);
- strumenti confinati (anti path-traversal), configurazione centralizzata, logging professionale;
- **7 test automatici** verdi.

💬 *"Ho già un 'atomo' funzionante e sicuro. La tesi lo moltiplica in uno swarm con il cost-routing."*

---

## Slide 12 — Piano e metodologia sperimentale
- **Milestone:** M2 cost-routing → M3 parallelo → M4 swarm → M5 RAG/contesto → M6 macchina a stati → M7 misurazione.
- **Esperimento:** **baseline** mono-modello (tutto sul modello top) **vs ORC** con routing, sugli **stessi task**.
- **Metriche:** **costo** per task, **qualità** (oggettiva + giudizio calibrato), **tasso di completamento autonomo**, latenza.
- **Tesi dimostrata** se: costo ↓↓ con qualità statisticamente **non inferiore** alla baseline.

💬 *"Il disegno sperimentale è classico: stesso set di task, due condizioni, variabili controllate."*

---

## Slide 13 — Rischi e domande aperte (per discussione)
- **Valutazione open-ended** = il capitolo più difficile (è ciò che i lavori esistenti evitano).
- **Bias del giudice** (auto-preferenza) → mitigazioni: giudici terzi, panel, pairwise.
- **Dati di training** per il router → feedback AI (RLAIF) + DPO; *l'università può supportare un piccolo set umano di calibrazione?*
- **Obsolescenza dei modelli** → il flywheel + transfer dei router.
- **Rappresentatività** del benchmark → metodologia rigorosa più che numeri grandi.

💬 *Chiudi invitando: "Su questi punti, in particolare la valutazione, gradirei molto il suo parere."*

---

## Nota build (Canva)
- **Stile:** slide dense ma pulite; 1 colore d'accento, font leggibile, niente muri indistinti — usa i bullet così come sono.
- **Diagrammi da inserire** (li abbiamo già in `M2_routing_design.md` / `TESI_master.md`): slide 6 (architettura team-su-git), slide 7 (flywheel), slide 12 (timeline milestone). Vanno ridisegnati puliti in Canva.
- Opzioni: (a) genero io il deck via il connettore Canva; (b) lo monti tu in Canva con questo testo. Da decidere.
