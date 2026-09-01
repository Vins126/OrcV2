# ORC — Piano completo di progetto (v1, agosto 2026)

> **Cos'è questo documento.** Il piano teorico completo del progetto di tesi, redatto
> dopo il confronto sistematico tra il piano originale (TESI_master.md,
> M2_routing_design.md, slide 12) e lo stato dell'arte: OI-MAS, MasRouter, RouteLLM,
> FrugalGPT e i due lavori Sakana AI 2025 (Trinity, Conductor — la ricerca dietro il
> prodotto Fugu). Serve da input per la stesura della tabella di marcia.
>
> **Come usarlo.** Tutte le scelte non ancora ratificate sono marcate `[DECISIONE-n]`
> e raccolte nella sezione 10. Ogni decisione riporta le opzioni e una raccomandazione,
> ma **la scelta finale spetta a Vincenzo**: il progetto è suo, le logiche di
> controllo e comando le definisce lui. Nessuna `[DECISIONE-n]` va considerata presa
> finché non è esplicitamente accettata (o modificata) dall'autore.

---

## 1. La tesi (invariata, rafforzata dalla letteratura)

> *Un sistema multi-agente con cost-routing ottiene una riduzione di costo
> significativa a parità di qualità rispetto a una baseline mono-modello, su task di
> software engineering open-ended.*

Formulazione come ottimizzazione vincolata:

```
min  Σ costo(modello_i)      s.t.   qualità(output) ≥ τ
```

Il confronto con la letteratura **conferma questa formulazione**: OI-MAS ottimizza
esattamente `-reward + λ·Conf·Costo` (stessa struttura, vincolo reso penalità);
FrugalGPT e RouteLLM dimostrano che il risparmio a parità di qualità è ottenibile
(98% e >2× rispettivamente, su task semplici); Trinity/Conductor dimostrano che
l'orchestrazione può addirittura *superare* il miglior modello singolo.

I **tre pilastri co-centrali** restano: (1) routing, (2) valutazione della qualità,
(3) validazione sperimentale. Stanno o cadono insieme.

---

## 2. Stato dell'arte: cosa dice ciascun lavoro e cosa se ne prende

| Lavoro | Cosa fa | Cosa CONFERMA del piano | Cosa se ne PRENDE | Cosa NON si prende (e perché) |
|---|---|---|---|---|
| **OI-MAS** (2601.04861) | Router a 2 reti (ruoli ℱ_ϕ + scala modello 𝒢_ψ) addestrato via RL; confidence = media log-prob dei token, normalizzata; reward = correttezza − λ·Conf·Costo; ruoli Generator/Critique/Verifier/…/EarlyStop; max 4 turni; pool Qwen 3B-7B, Llama 8B-70B. +12.88% acc., −79.78% costo | La struttura "qualità vincolata al costo"; il routing per ruolo+scala | **Segnale di confidenza gratuito** (log-prob) come pre-filtro dell'escalation; ruolo **EarlyStop** (fermarsi è una decisione di risparmio); i loro 3 limiti dichiarati (memoria, scala, **safety**) come posizionamento | Il training RL delle due reti (costo di sviluppo alto, richiede molte esecuzioni); i task verificabili con ground-truth (il nostro dominio è open-ended) |
| **MasRouter** (2502.11133) | Definisce il problema **MASR** (routing per MAS ≠ single-agent); controller a cascata: modo di collaborazione → allocazione ruoli → routing LLM; −52% overhead. ⚠️ letto a livello abstract: **la lettura integrale del PDF resta da fare** | Che il routing multi-agente è problema aperto e recente (il gap esiste); che *anche la topologia/il numero di agenti è una decisione di routing* | Il nome del problema (MASR) per il capitolo related work; l'idea che **la granularità della decomposizione è parte della decisione di routing** (conferma la curva a U §2.3 del master) | La determinazione automatica del modo di collaborazione (la nostra topologia è fissata by-design: team-su-git) |
| **RouteLLM** (2406.18665) | Router binario forte/debole appreso da preferenze umane (+ augmentation); >2× risparmio; **transfer tra coppie di modelli** senza retrain | La via "preferenze → router"; lo scoring per coppia (prompt, modello) anti-obsolescenza | Il framework di valutazione a soglie di qualità; il risultato di transfer come argomento contro l'invecchiamento del router | La restrizione binaria forte/debole (il nostro pool è N modelli eterogenei) |
| **FrugalGPT** (2305.05176) | Tre leve: prompt adaptation, LLM approximation, **cascade** con stimatore di qualità; fino a 98% risparmio | La cascade come meccanismo che "scopre invece di predire" | La **terza leva dimenticata dal piano: l'economia del prompt/contesto** (il costo cresce super-linearmente con la storia della conversazione → gestirlo È cost-reduction) | L'approssimazione via cache/fine-tune di modelli propri (fuori scala per una tesi) |
| **Trinity** (Sakana, 2512.04695) | Coordinatore da 0.6B + testa lineare ~10K param (<20K totali apprendibili) su hidden state; ottimizzato con **sep-CMA-ES** (non RL: parametri debolmente accoppiati → gradienti a basso SNR); ruoli Thinker/Worker/Verifier; Verifier emette ACCEPT/REVISE; K=5 turni; SOTA LiveCodeBench 86.2% | Che un **router minuscolo è sufficiente** (il piano già prevedeva embedding+testa leggera, ELHSR-style); che il "giudice che decide se continuare" è il perno del loop | Il protocollo **Verifier→{ACCEPT, REVISE}** come forma minima del giudice di cascade; l'argomento **CMA-ES vs RL** come terza opzione di training documentabile; il loro limite dichiarato ("non può agire con i tool") come **nostro punto di forza** (M1 ha sandbox+tool) | L'uso degli hidden state (richiede accesso ai pesi: impossibile con API commerciali → il nostro analogo API-compatibile sono gli embedding) |
| **Conductor** (Sakana, 2512.04388) | Orchestratore 7B addestrato con GRPO (reward 0 / 0.5 / 1); emette il workflow come **tre liste**: `model_id`, `subtasks` (istruzioni in linguaggio naturale), `access_list` (visibilità dei contesti); fino a 5 step, topologie ad albero; ricorsione (sé stesso come worker) = test-time scaling; batte GPT-5 in media (77.27 vs 74.78); **analisi costi esplicita**: 735 token/campione vs 1413 del consenso 5×, performance/costo 103.5 vs 42.9 | La decomposizione con istruzioni mirate per worker; che l'orchestrazione batte il singolo modello **anche sul costo** | (a) La **rappresentazione del piano come struttura dati semplice** (liste: sotto-task, assegnazioni, visibilità) per l'output del Planner; (b) la metrica **cost-adjusted performance** per M7; (c) il training con **pool randomizzati** → robustezza al cambio di modelli; (d) `access_list` = controllo della visibilità del contesto → è anche una leva di costo | Il training RL end-to-end dell'orchestratore (fuori budget tesi); la ricorsione illimitata |
| **Fugu (prodotto)** | Orchestrazione commerciale multi-LLM; pool intercambiabile; benchmark alti MA: latenza fino a 30 min, un utente ha bruciato $20 di quota con un solo prompt | Che il trade-off costo/latenza/qualità è reale e va **dichiarato** | La lezione operativa: servono **guard-rail di budget** (tetto di spesa per task) e il pool deve essere **sostituibile a caldo** (loro hanno perso Fable 5 per export control) | — |

**Sintesi del posizionamento (invariato ma più forte):** tutti i lavori vicini operano
su task *verificabili* a risposta singola, senza esecuzione reale con tool, senza
safety, senza artefatto condiviso. Il gap della tesi — cost-routing in uno swarm di
coding agent su artefatto condiviso, con valutazione execution-based e sandbox — resta
libero, e ora due lavori (OI-MAS e Trinity) **dichiarano come propri limiti** esattamente
ciò che questo progetto ha già costruito in M1.

**Ampliamento del gap (§3.11):** nessuno dei lavori citati instrada su un pool
**eterogeneo per capacità** né su **unità di fatturazione miste** — OI-MAS, MasRouter,
RouteLLM, Trinity e Conductor scelgono tutti fra LLM testuali con lo stesso modello di
costo (token). Il contributo rivendicabile diventa quindi: *cost-routing su pool
eterogeneo per capacità, con unità di fatturazione miste, in uno swarm di coding agent
su artefatto condiviso, con valutazione execution-based e isolamento.* È un
posizionamento più ampio e più difendibile, non una complicazione.

---

## 3. Migliorie al piano derivate dal confronto

Ogni miglioria indica: fonte, cosa cambia, perché. Quelle marcate `[DECISIONE-n]`
richiedono ratifica.

### 3.1 Misura prima dell'intelligenza `[DECISIONE-1]`
**Fonte:** tutti i paper riportano costi misurati; il claim della tesi è una misura.
**Cambia:** M2 si spezza in **M2a (infrastruttura di misura)** — contabilità costi,
registro modelli/prezzi, logging strutturato — da fare *subito*, e **M2b (intelligenza
di routing)** — valutazione, cascade, router appreso — da fare *dopo* lo swarm.
**Perché:** (a) senza misura non esiste né baseline né esperimento; (b) addestrare il
router su dati mono-agente riprodurrebbe il limite che MasRouter denuncia (il routing
single-agent non trasferisce ai MAS); (c) la valutazione "di stato" (§2.4 master)
non è definibile prima che esista il workspace condiviso.

### 3.2 Routing statico role-based come stadio sperimentale `[DECISIONE-2]`
**Fonte:** OI-MAS (routing per ruolo), pratica MetaGPT/ChatDev.
**Cambia:** tra M2a e lo swarm si introduce un routing **statico per ruolo** (Planner
= modello forte, Worker = economici, da tabella fissa). Non è una pezza: è uno
**stadio misurato** della narrazione sperimentale, che diventa a 4 stadi:
`S0 baseline mono-modello → S1 role-based statico → S2 cascade → S3 router appreso`.
**Perché:** ogni stadio produce un numero; la distanza S1→S3 quantifica il valore
dell'*intelligenza* del router rispetto a una regola banale — un risultato in più,
non un compromesso.

### 3.3 Guard-rail di budget (cost circuit-breaker) `[DECISIONE-3]`
**Fonte:** lezione Fugu ($20/prompt, 30 min di latenza); coerente col RilevatoreLoop
già esistente (stessa filosofia: fermare lo spreco).
**Cambia:** ogni esecuzione ha un **tetto di spesa** (per task e, nello swarm, per
agente). Superata la soglia: stop pulito + log. Analogo dell'enum Alerts ma sul costo:
OK / AVVISA (soglia morbida) / FERMA (tetto).
**Perché:** un sistema autonomo che spende senza limite non è deployabile né
sperimentabile in sicurezza; ed è un dettaglio che in sede di discussione dimostra
maturità ingegneristica.

### 3.4 Valutazione a due livelli: segnali gratuiti prima, giudice poi `[DECISIONE-4]`
**Fonte:** OI-MAS (confidence da log-prob = segnale gratuito); BigCodeArena (per il
codice l'esecuzione batte il giudizio testuale); FrugalGPT (stimatore a soglia).
**Cambia:** il gate di qualità della cascade diventa **a due livelli**:
- **Livello 1 (gratis, sempre):** exit code, test verdi/rossi, build ok, lint,
  e — dove il provider li espone — log-prob medi come confidenza. Verifica per
  provider: OpenAI li espone, altri no → trattare come segnale *opzionale*.
- **Livello 2 (costoso, solo ai checkpoint):** LLM-as-a-judge pairwise, secondo il
  piano già definito (§5 master: gate hard + Bradley-Terry, bias mitigati, kappa).
**Perché:** il giudice a ogni passo mangerebbe il risparmio che si vuole dimostrare.
I segnali gratuiti filtrano la maggioranza dei casi; il giudice interviene dove serve.

### 3.5 Output del Planner come struttura dati semplice `[DECISIONE-5]`
**Fonte:** Conductor (workflow = tre liste: `model_id`, `subtasks`, `access_list`).
**Cambia:** il Planner emette il piano in un formato strutturato e validabile:
```
sotto_task   : [descrizione in linguaggio naturale, per ciascuna foglia]
dipendenze   : [DAG: quali foglie attendono quali]
ruolo        : [frontend / backend / test / refactor, per foglia]
visibilità   : [quali output/file precedenti ogni foglia può vedere]
```
La `visibilità` è la novità: controlla il contesto passato a ogni worker → è
insieme il meccanismo anti-collisione del blackboard **e una leva di costo**
(contesto più piccolo = inferenza più economica).
**Perché:** un formato semplice è validabile programmaticamente (il piano si può
rifiutare/rigenerare), loggabile nel dataset, e citabile in tesi con un precedente
pubblicato a ICLR.

### 3.6 Economia del contesto come leva di costo dichiarata `[DECISIONE-7, parte]`
**Fonte:** FrugalGPT (prompt adaptation è una delle tre leve); natura autoregressiva
dell'inferenza (il costo per iterazione cresce con la storia).
**Cambia:** M5 "RAG/contesto" si ridimensiona da milestone autonomo a **principio
trasversale**: visibilità minima necessaria per ogni worker (§3.5), troncamento/
riassunto della storia nei task lunghi, misurazione dei token di contesto nel log.
**Perché:** nel regime multi-agente il contesto è una voce di costo primaria; un RAG
completo è probabilmente fuori scope, la *disciplina del contesto* no.

### 3.7 Metrica principale: cost-adjusted performance + frontiera di Pareto `[DECISIONE-8]`
**Fonte:** Conductor (103.49 vs 42.94); RouteLLM (qualità a % di costo).
**Cambia:** M7 riporta per ogni stadio S0-S3: costo/task, qualità (vettore), latenza,
tasso di completamento autonomo, **qualità÷costo** come indice sintetico, e il
**grafico di Pareto costo-qualità** con i 4 stadi come punti.
**Perché:** è la forma in cui la letteratura 2024-26 presenta questo tipo di
risultato; rende il confronto immediato e difendibile.

### 3.8 Robustezza al cambio del pool `[DECISIONE-9]`
**Fonte:** Conductor (training con pool randomizzati); RouteLLM (transfer); lezione
Fugu (modelli che spariscono per cause esterne).
**Cambia:** (a) il registro modelli di M2a è **configurazione, non codice** (aggiungere
/togliere un modello = editare una tabella); (b) se si arriva al router appreso (S3),
addestrarlo con **subset casuali del pool** e con scoring per coppia (prompt, modello),
mai come classificatore a N vie fisso.
**Perché:** è la difesa concreta contro l'obsolescenza — la domanda che il relatore
farà di sicuro ("e quando esce un modello nuovo?").

### 3.9 Metodo di training del router: tre opzioni documentate `[DECISIONE-6]`
**Fonte:** RouteLLM (supervised da preferenze), piano originale (DPO), Trinity
(CMA-ES con argomento tecnico: parametri debolmente accoppiati → gradienti RL a basso
SNR → i metodi evolutivi diagonali vincono).
**Cambia:** la scelta non si prende ora. Si documentano tre vie in ordine di costo
di implementazione:
1. **Testa supervisionata su embedding** (regressione logistica / MLP piccolo sul
   dataset dei log): la più semplice, probabilmente sufficiente a scala di tesi.
2. **DPO** sul giudice (come da piano §5.3 master) se si vuole il reward model.
3. **CMA-ES** come alternativa se i gradienti si rivelassero rumorosi (citare Trinity).
**Perché:** decidere ora sarebbe prematuro: la scelta giusta dipende da quanti dati
produrrà davvero il flywheel (S2). La tesi guadagna a *discutere* le tre opzioni.

### 3.10 M6 (macchina a stati) assorbito nell'orchestratore `[DECISIONE-7, parte]`
**Fonte:** analisi delle dipendenze; OI-MAS e Conductor gestiscono il flusso con
strutture minime (soglie di turno, liste), non con macchine a stati esplicite.
**Cambia:** M6 cessa di essere un milestone autonomo: il ciclo
`pianifica → esegui wave → checkpoint → (ri-delega | avanza | fermati)` È la macchina
a stati, e vive dentro l'orchestratore di M4.
**Perché:** riduce lo scope senza perdere nulla: lo stato del sistema è già
rappresentato da DAG + esiti dei checkpoint.

### 3.11 Tassonomia delle capacità e unità di fatturazione multiple `[DECISIONE-10]` `[DECISIONE-11]`
**Fonte:** analisi condotta partendo dal task reale ("costruisci il sito di una
pizzeria") invece che dalla lista dei modelli disponibili; il `capability-aware
routing` era già previsto in `TESI_master.md` §3 ma non era stato reso operativo.

**Il problema individuato:** un sistema che consegna un sito con
`<img src="placeholder.jpg">` non ha completato il task. Le capacità non testuali
(immagini, video, 3D, voce) fanno parte del prodotto software, quindi del dominio
della tesi. Ma **non si fatturano a token**, e un contabile `token × prezzo` non
le regge.

**Le capacità del sistema:**

| # | Capacità | Unità di fatturazione |
|---|---|---|
| C1 | Ragionamento / pianificazione | token |
| C2 | Generazione di codice | token |
| C3 | Scrittura di contenuti | token |
| C4 | Comprensione visiva (input: mockup, screenshot) | token |
| C5 | Immagini raster | **per immagine** |
| C6 | Grafica vettoriale (logo, icone) | **token** (l'SVG è codice) |
| C7 | Video | **per secondo** |
| C8 | Modelli 3D | **per credito/job** |
| C9 | Sintesi vocale (TTS) | **per carattere** |
| C10 | Trascrizione (STT) | **per minuto** |
| C11 | Embedding (RAG **e il router stesso**) | token |
| C12 | Reranking | per query |
| C13 | Asset da libreria/stock | **spesso gratis** |
| C14 | Elaborazione deterministica (compressione, ottimizzazione) | **gratis (tool)** |

**Tre osservazioni non ovvie:**
1. **C6 — logo e icone sono codice, non immagini.** L'SVG è testo: un LLM lo scrive
   direttamente, fatturato a token. Vettoriale, scalabile, modificabile, e a una
   frazione del costo di un'immagine generata. Nessun modello aggiuntivo: la copre C2.
2. **C13/C14 — non ogni capacità richiede un modello generativo.** Foto stock o
   librerie di icone possono essere migliori *e gratuite*; l'ottimizzazione immagini è
   un tool deterministico. Ne segue che **"quale capacità impiegare" è a sua volta una
   decisione di routing**, e l'opzione più economica a volte non è un modello.
3. **C11 non è opzionale:** gli embedding sono l'infrastruttura del router previsto in
   `TESI_master.md` §5.7 (embedding + testa leggera).

**`[DECISIONE-10]` — Contabilità generalizzata a quantità + unità.** Il record di
consumo porta **quantità e unità**; il registro mappa `(modello, unità) → prezzo`:
```
costo = Σ  quantità × prezzo_unitario
```
I token restano il caso comune, ma tutto converge in **$**: i totali restano
sommabili e confrontabili fra capacità diverse. È una generalizzazione della
struttura dati, non un cambio di architettura.

**`[DECISIONE-11]` — Sistema generale, campagna focalizzata.** L'architettura
supporta *tutte* le capacità (costa poco: registro + filtro per capacità, entrambi
già previsti) e lo si dimostra con una **demo end-to-end** multi-capacità. La
**campagna quantitativa di M7 resta su codice + frontend**, con il perimetro
dichiarato esplicitamente. Motivo: valutare la qualità di un'immagine, di un video o
di un asset 3D è un problema di ricerca autonomo, che moltiplicherebbe metriche,
giudici e calibrazione umana. Sistema generale + valutazione circoscritta e onesta è
la prassi corretta.

**Conseguenza sul filtro di routing:** il capability-aware diventa operativo e
**precede** il criterio di costo. Esempio concreto: nel video, un modello con audio
nativo e uno senza non sono confrontabili sul prezzo al secondo, perché il secondo
richiede uno step audio aggiuntivo (costo + latenza). Prima si filtra per capacità
richieste, poi si sceglie sulla frontiera di Pareto.

### 3.12 Costo marginale vs costo fisso, e criterio di selezione dei fornitori `[DECISIONE-12]`
**Fonte:** analisi dei listini reali per la capacità C8 (3D). Meshy espone l'API solo
ai piani in abbonamento ($20-100/mese); Tripo offre anche pacchetti **pay-as-you-go**
(~$10 per 1.000 crediti, ~$0.01/credito).

**Il problema individuato.** L'abbonamento è un **terzo modello di fatturazione**,
accanto al per-token e al per-unità, e rompe un'assunzione implicita del contabile:
1. esiste un **costo fisso** che non dipende dall'uso e che il contabile marginale non
   registrerebbe da nessuna parte;
2. il **costo per credito dipende dal piano** ($0.020 su Pro contro $0.010 su Ultra:
   lo stesso asset costa il doppio) — il prezzo non è una proprietà del modello ma
   della configurazione commerciale;
3. **sunk cost**: su un piano da $20 con 1.000 crediti, generare 10 asset invece di 50
   porta il costo effettivo per asset da $0.40 a $2.00. Il costo unitario dipende dal
   tasso di utilizzo mensile, quindi **non è riproducibile né confrontabile**.

**Regola adottata:**
> Nel contabile si registra il **costo marginale** (quantità × prezzo unitario del
> piano dichiarato). Il **costo fisso** si dichiara separatamente, in una tabella
> "costi di accesso" del capitolo sperimentale.

Motivazione: il costo marginale è riproducibile e confrontabile fra esecuzioni; il
costo fisso è **affondato** e non varia in funzione delle decisioni del router, quindi
farlo pesare su una scelta che non lo modifica sarebbe metodologicamente scorretto —
ma ometterlo del tutto sottostimerebbe il costo del sistema.

**`[DECISIONE-12]` — Criterio di selezione dei fornitori.**
> A parità di capacità si preferisce il fornitore con **fatturazione marginale e
> trasparente**. I modelli ad abbonamento rendono il costo unitario dipendente dal
> tasso di utilizzo, quindi non riproducibile, e introducono un asterisco che si
> trascinerebbe per tutta la campagna sperimentale.

Applicazione a C8: **si adotta Tripo in pay-as-you-go** (~$0.01/credito, ~$0.20-0.30
per modello completo da 20-30 crediti, 300 crediti gratuiti per la misurazione
iniziale). Meshy è scartato dal pool: l'API richiede un abbonamento ricorrente, non ha
alcun tier gratuito per l'API e a parità di tariffa migliore ($0.010/credito) impone
$100/mese. Resta citabile in tesi come termine di paragone sulla qualità delle mesh.

**Nota:** il criterio è generale e nessuno dei lavori confrontati lo affronta — tutti
assumono implicitamente il pay-per-token. In un lavoro il cui oggetto *è* la misura
del costo, la struttura di fatturazione del fornitore è essa stessa una variabile
metodologica.

**Conseguenza sul budget guard (D3):** con un pool che va da $0.003 per immagine a
$0.20-0.30 per asset 3D — due ordini di grandezza — una singola chiamata costosa può
dominare il budget di un intero task. Il tetto di spesa smette di essere una
precauzione e diventa un requisito.

---

## 4. Architettura di riferimento (aggiornata)

Invariata nell'impianto (team-su-git, gerarchico + blackboard, NO mesh, NO merge
finale), con le integrazioni §3 evidenziate da (*).

```
                              TASK utente
                                  │
                                  ▼
                      ┌───────────────────────┐
                      │  PLANNER (modello forte)│
                      │  emette piano strutturato│ (*) §3.5: sotto_task, DAG,
                      │  validato/rigenerabile   │      ruolo, visibilità
                      └───────────┬────────────┘
                                  ▼
                      ┌───────────────────────┐
                      │  ROUTER per sotto-task │  S1: tabella statica per ruolo
                      │  (stadi S1→S2→S3)      │  S2: + cascade   S3: + appreso
                      └───────────┬────────────┘
                                  ▼
                      ┌───────────────────────┐
                      │  ORCHESTRATORE         │  governa il DAG a ondate (wave),
                      │  (tech-lead)           │  indice i checkpoint,
                      │  + BUDGET GUARD (*)    │  ferma chi sfora il tetto §3.3
                      └───────────┬────────────┘
                       ┌──────────┼──────────┐
                       ▼          ▼          ▼
                   ┌───────┐  ┌───────┐  ┌───────┐
                   │Worker │  │Worker │  │Worker │   ogni worker = Agent M1
                   │ (FE)  │  │ (BE)  │  │(test) │   + modello dal router
                   └───┬───┘  └───┬───┘  └───┬───┘   + sandbox Docker
                       │  contesto = solo la │
                       │  vista dichiarata (*)│ §3.5/§3.6
                       └──────────┼──────────┘
                                  ▼
              ┌────────────────────────────────────────┐
              │  WORKSPACE CONDIVISO + BLACKBOARD       │  il progetto cresce qui,
              │  (interfacce, convenzioni, contratti)   │  incrementalmente
              └────────────────────┬───────────────────┘
                                   ▼  ai checkpoint
              ┌────────────────────────────────────────┐
              │  GATE DI QUALITÀ A DUE LIVELLI (*) §3.4 │
              │  L1 gratis: build, test, exit code,     │
              │             (log-prob se disponibile)   │
              │  L2 costoso: LLM-judge pairwise          │
              │  esito: ACCEPT / REVISE (ri-delega)      │ (protocollo Trinity)
              └────────────────────────────────────────┘

   TRASVERSALE (M2a): contabilità costi su OGNI chiamata (usage → token × prezzo),
   registro modelli/prezzi come configurazione, log strutturato per esecuzione:
   (task, sotto-task, modello, ruolo, token in/out, costo, esito L1/L2, latenza)
   → questo log È il dataset del flywheel.
```

**Punti di comando dell'autore** (dove le regole le fissa Vincenzo, non il sistema):
la tabella ruolo→modello di S1; le soglie τ dei gate; i tetti di budget; la decisione
ACCEPT/REVISE ai checkpoint può essere resa semi-automatica solo dopo che i gate sono
calibrati; la composizione del pool di modelli.

---

## 5. Valutazione della qualità (il pilastro difficile — impianto confermato)

Confermato l'impianto del master §5, con la gerarchia resa operativa dal gate a
due livelli (§3.4):

1. **Qualità = vettore per categoria** (frontend / backend / refactor / trasversali),
   mai un numero unico.
2. **Oggettivo prima di tutto** (gratis, esecuzione): build, pass@k, lint, type-check,
   Lighthouse/axe per il frontend, dimensione diff per i refactor. Conferma esterna:
   BigCodeArena — per il codice l'esecuzione batte il giudizio testuale.
3. **Soggettivo come preferenze**: pairwise (A vs B anonimi, ordine scambiato),
   gate hard non mediabili, aggregazione Bradley-Terry, penalità di verbosità,
   giudice terzo (mai un modello che valuta sé stesso).
4. **Validità dichiarata**: piccolo set umano, accordo inter-annotatore (kappa) come
   soffitto rivendicabile.
5. **Nel runtime** entra solo la forma economica del giudizio (L1 + ACCEPT/REVISE ai
   checkpoint); la valutazione ricca vive **offline** nel benchmark-harness di M7.

---

## 6. Piano milestone rivisto

Legenda stato: ✅ fatto · 🔜 prossimo · ⏳ dipendente · ✂️ ridotto/assorbito

| # | Milestone | Contenuto | Dipende da | Criterio di completamento (definition of done) |
|---|---|---|---|---|
| **M1** ✅ | Agente singolo | ReAct, resilienza, loop-detect, sandbox Docker, workspace, test, CI | — | *(fatto: 7 test verdi in CI, repo versionato)* |
| **M2a** 🔜 | Infrastruttura di misura `[DECISIONE-1]` | Cattura `usage` per chiamata; registro modelli+prezzi (configurazione); log strutturato per esecuzione; budget guard `[DECISIONE-3]`; report di costo a fine task | M1 | Un task d'esempio stampa e salva: token in/out, costo €, per iterazione e totale; sforare il tetto ferma il task; i prezzi si cambiano senza toccare codice |
| **M2s** | Routing statico role-based `[DECISIONE-2]` | Tabella ruolo→modello; istanziazione di Agent con modelli diversi; misura S1 su task campione | M2a | Due agenti con modelli diversi completano task loggando costi confrontabili |
| **M3** | Parallelismo | Esecuzione concorrente di N agenti su workspace separati; poi su workspace condiviso con file-lock/convenzioni | M2a | N agenti in parallelo senza corruzione del workspace, costi aggregati correttamente |
| **M4** | Swarm (cuore) | Planner con output strutturato `[DECISIONE-5]`; orchestratore a ondate sul DAG; blackboard; checkpoint con gate L1 `[DECISIONE-4]`; ri-delega su REVISE | M3, M2s | Un task multi-file (es. mini web-app) completato end-to-end dallo swarm con log completo di costi e esiti |
| **M2b** ⏳ | Intelligenza di routing | Gate L2 (judge pairwise); cascade con escalation (S2); raccolta dataset dai log; router appreso (S3) `[DECISIONE-6]` con pool randomizzato `[DECISIONE-9]` | M4 | S2: escalation osservabile nei log con delta di costo; S3: router che batte S1 sul set di validazione |
| **M7** | Campagna sperimentale | Set di task per categoria; esecuzione S0-S3 sugli stessi task; metriche §3.7 `[DECISIONE-8]`; calibrazione umana (kappa); analisi statistica di non-inferiorità della qualità | M2b (S2 basta; S3 se il tempo regge) | Tabella e Pareto costo-qualità a 3-4 stadi; test di non-inferiorità documentato |
| ~~M5~~ ✂️ | RAG/contesto → **principio trasversale** §3.6 `[DECISIONE-7]` | Visibilità minima, disciplina del contesto, misura dei token di contesto | dentro M4 | — |
| ~~M6~~ ✂️ | Macchina a stati → **assorbito nell'orchestratore** §3.10 `[DECISIONE-7]` | Ciclo pianifica→esegui→checkpoint→decidi | dentro M4 | — |

**Percorso critico:** M2a → M2s → M3 → M4 → M2b(S2) → M7.
**Uscita di sicurezza:** se il tempo stringe, la tesi è difendibile già con
S0-S1-S2 misurati (baseline, statico, cascade); S3 (router appreso) è il massimo
risultato, non il minimo indispensabile. La valutazione L2 completa (judge calibrato
con umani) può ridursi al solo L1 + campione ridotto di giudizi, dichiarandolo.

---

## 7. Metodologia sperimentale (M7, disegnata ora per costruire nel modo giusto)

- **Set di task:** 3 categorie (frontend, backend/logica, refactor), pochi task ma
  curati e ripetibili; ogni task con criteri L1 automatici definiti *a priori*.
- **Condizioni:** S0 baseline mono-modello (tutto sul modello top — è M1);
  S1 role-based statico; S2 cascade; S3 router appreso. Stessi task, stessa sandbox,
  stessi criteri: cambia solo la politica di routing.
- **Metriche per condizione:** costo/task (€ e token), qualità (vettore: L1 + giudizio
  calibrato), latenza, tasso di completamento autonomo, qualità÷costo.
- **Esito che dimostra la tesi:** costo S≥1 significativamente < S0 con qualità
  **statisticamente non inferiore** (test di non-inferiorità, non di superiorità).
- **Ripetibilità:** ambiente fissato (immagine Docker pinnata, requirements pinnati,
  seed dove possibile), log completi versionati; il flywheel (ri-esecuzione su
  modelli nuovi) è la risposta all'obsolescenza.

---

## 8. Rischi e mitigazioni (aggiornati)

| Rischio | Gravità | Mitigazione |
|---|---|---|
| Valutazione open-ended non regge la difesa | **Alta** — è il capitolo che OI-MAS evita | Gerarchia L1-prima (esecuzione, oggettivo); soggettivo solo come preferenze con kappa dichiarato; iniziare a raccogliere L1 fin da M2a per testare presto l'impianto |
| Costi di sviluppo/esperimenti fuori controllo | Media | Budget guard (§3.3) dal giorno uno; modelli economici in sviluppo; il modello forte solo dove il ruolo lo richiede |
| Latenza dello swarm (lezione Fugu: 30 min) | Media | Parallelismo reale sulle ondate del DAG; visibilità minima (meno token = meno tempo); dichiarare il trade-off in tesi |
| Dataset per S3 insufficiente | Media | S3 dichiarato opzionale (§6); in alternativa la testa supervisionata semplice (§3.9 opzione 1) richiede meno dati di DPO |
| Modelli che cambiano/spariscono | Media | Registro come configurazione; scoring per coppia; flywheel ripetibile (§3.8) |
| Scope troppo largo per una tesi | **Alta** | Tagli già decisi in questo piano (M5, M6); uscita di sicurezza S0-S2; il piano distingue "minimo difendibile" da "massimo risultato" |
| Conflitti sul workspace condiviso in M3/M4 | Media | Prima workspace separati, poi condiviso con convenzioni dal blackboard; risoluzione incrementale stile git (mai merge monolitico) |
| MasRouter letto solo a livello abstract | Bassa | **TODO esplicito:** lettura integrale del PDF prima di scrivere il related work |

---

## 9. Cosa NON si fa (non-goal dichiarati)

- **Training RL end-to-end** dell'orchestratore (Conductor) o del router (OI-MAS):
  fuori budget computazionale e temporale di una tesi; si documenta il perché.
- **Uso di hidden state** dei modelli (Trinity): impossibile via API commerciali;
  l'analogo API-compatibile sono gli embedding.
- **Topologia mesh** e negoziazione libera tra agenti: O(N²), esclusa by-design.
- **RAG completo** su codebase esterne: ridotto a disciplina del contesto (§3.6).
- **Fine-tuning di modelli generativi**: al più DPO su un giudice/reward piccolo, o
  testa leggera su embedding.

---

## 10. Registro delle decisioni aperte (da ratificare una per una)

> Nessuna di queste è operativa finché Vincenzo non la accetta, modifica o respinge.
> Le raccomandazioni sono motivate nelle sezioni indicate.

| ID | Decisione | Opzioni | Raccomandazione | Stato |
|---|---|---|---|---|
| **D1** | Spezzare M2 in M2a (misura, subito) + M2b (intelligenza, dopo M4) | (a) sì; (b) M2 completo ora; (c) M2 tutto dopo | **(a)** — §3.1 | ✅ accettata (a) — ago 2026 |
| **D2** | Routing statico role-based come stadio sperimentale S1 | (a) sì, misurato; (b) no, si salta a cascade | **(a)** — §3.2 | ✅ accettata (a) — ago 2026 |
| **D3** | Budget guard per task/agente (OK/AVVISA/FERMA sul costo) | (a) sì da M2a; (b) più avanti | **(a)** — §3.3 | ✅ accettata (a) — ago 2026 |
| **D4** | Gate di qualità a due livelli (L1 gratis sempre, L2 judge ai checkpoint) | (a) sì; (b) judge ovunque; (c) solo L1 | **(a)** — §3.4 | ✅ accettata (a) — ago 2026 |
| **D5** | Planner emette piano strutturato (sotto_task, DAG, ruolo, visibilità) | (a) sì; (b) piano libero in prosa | **(a)** — §3.5 | ✅ accettata (a) — ago 2026 |
| **D6** | Metodo training router S3 | (a) testa supervisionata su embedding; (b) DPO; (c) CMA-ES | **rimandare a M2b**, default (a) — §3.9 | ⏸ rimandata a M2b (by design) |
| **D7** | Tagli di scope: M5→principio trasversale, M6→assorbito | (a) entrambi i tagli; (b) tenerne uno; (c) tenerli entrambi | **(a)** — §3.6, §3.10 | ✅ accettata (a) — ago 2026 |
| **D8** | Metrica principale M7: cost-adjusted performance + Pareto a stadi | (a) sì; (b) solo costo e qualità separate | **(a)** — §3.7 | ✅ accettata (a) — ago 2026 |
| **D9** | Robustezza pool: registro come config + (per S3) training con subset randomizzati | (a) sì; (b) solo registro | **(a)**, con (b) accettabile — §3.8 | ✅ accettata (a) — ago 2026 |
| **D10** | Contabilità generalizzata a quantità + unità (token, immagine, secondo, credito, carattere, minuto) | (a) sì; (b) solo token, capacità non testuali escluse | **(a)** — §3.11 | ✅ accettata (a) — ago 2026 |
| **D11** | Sistema generale su tutte le capacità, campagna sperimentale M7 focalizzata su codice+frontend | (a) sì; (b) campagna su tutte le categorie; (c) sistema solo testuale | **(a)** — §3.11 | ✅ accettata (a) — ago 2026 |
| **D12** | Costo marginale nel contabile + costo fisso dichiarato a parte; preferenza per fornitori a fatturazione marginale (per C8: solo Tripo PAYG) | (a) sì; (b) amortizzare l'abbonamento sugli asset; (c) ignorare i costi fissi | **(a)** — §3.12 | ✅ accettata (a) — ago 2026 |

---

## 11. Riferimenti

- OI-MAS — *Confidence-Aware Routing across Multi-Scale Models*, arXiv:2601.04861
- MasRouter — *Learning to Route LLMs for Multi-Agent Systems*, arXiv:2502.11133 ⚠️ da leggere integralmente
- RouteLLM — Ong et al., arXiv:2406.18665
- FrugalGPT — Chen et al., arXiv:2305.05176
- Trinity — *An Evolved LLM Coordinator*, Sakana AI, arXiv:2512.04695 (ICLR 2026)
- Conductor — *Learning to Orchestrate Agents in Natural Language*, Sakana AI, arXiv:2512.04388 (ICLR 2026)
- MetaGPT, ChatDev — topologia team simulato (già nel master)
- LLM-as-a-judge: Zheng et al. 2023; survey Gu et al. 2025; BigCodeArena arXiv:2510.08697
- ELHSR (reward head lineare), RLHF/DPO/RLAIF — già nel master §5
- Documenti interni: `TESI_master.md`, `M2_routing_design.md`, `TESI_presentazione.md`
