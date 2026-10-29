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
| **M7** | Campagna sperimentale | Set di task per categoria; esecuzione S0-S3 sugli stessi task; metriche §3.7 `[DECISIONE-8]`; calibrazione umana (kappa); analisi statistica di non-inferiorità della qualità | M2b (S2 e S3 — D13) | Tabella e Pareto costo-qualità a 3-4 stadi; test di non-inferiorità documentato |
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
| Dataset per S3 insufficiente | **Alta** | S3 è essenziale (D13), quindi il rischio non si aggira ma si gestisce: curva di apprendimento per fermarsi quando i dati bastano, apprendimento attivo per spendere solo dove il router è incerto (ROADMAP M2b.3); la testa supervisionata semplice (§3.9 opzione 1) richiede meno dati di DPO. Aggravante: le etichette soggettive costano ~2,6× quelle deterministiche e sono rumorose |
| Modelli che cambiano/spariscono | Media | Registro come configurazione; scoring per coppia; flywheel ripetibile (§3.8) |
| Scope troppo largo per una tesi | **Alta** | Tagli già decisi in questo piano (M5, M6); S0-S2 resta un'uscita di emergenza, ma come risultato di ingegneria e non di ricerca (D13) |
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
| **D13** | Il router appreso (S3) è essenziale, non opzionale | (a) S3 essenziale, S0-S2 apparato di misura; (b) S3 opzionale, S0-S2 minimo difendibile | **(a)** — senza S3 la tesi applica tecniche note (cascade, assegnazione statica per ruolo) a un dominio nuovo: un buon lavoro di ingegneria, non un contributo di ricerca. Il flywheel (§2.2 master) si chiude solo col router appreso, e i lavori con cui ci si confronta (MasRouter, RouteLLM, OI-MAS) sono tutti router appresi | ✅ accettata (a) — set 2026 — sostituita da D36 (18 ott 2026) |
| **D14** | Giudizio a due livelli: sezione durante il lavoro, pagina a fine lavoro | (a) due livelli; (b) solo pagina intera | **(a)** — il giudizio di sezione è l'etichetta del sotto-task che l'ha prodotta (risolve l'attribuzione del merito); il giudizio di pagina dimostra la tesi. Metriche diverse per addestramento e valutazione, quindi niente validazione circolare | ✅ accettata (a) — set 2026 |
| **D15** | Il planner produce anche il sistema di stile, in una sola chiamata | (a) un planner, due uscite (scomposizione + stile); (b) planner e art director come agenti separati | **(a)** — la coerenza fra sezioni diventa un vincolo di specifica; (b) costerebbe una chiamata al modello forte nel punto già più caro, con ruoli accoppiati che dovrebbero iterare. Nessun modello economico specializzato nel design è noto: (b) resta un esperimento misurabile | ✅ accettata (a) — set 2026 |
| **D16** | Dominio sperimentale: il sito web intero | (a) sito intero; (b) componenti isolati; (c) altri domini a giudizio istantaneo (grafici, SVG) | **(a)** — (b) e (c) semplificano la valutazione ma un componente si genera con una chiamata sola: senza nulla da scomporre lo swarm perde la ragione d'essere, e con esso la tesi | ✅ accettata (a) — set 2026 — confermata da D35 (18 ott 2026) |
| **D17** | Calibrazione di `f` in M2s sui 34 esercizi Python di polyglot (Exercism, MIT) | (a) esercizi polyglot scaricati da script; (b) task scritti da noi, 10-15; (c) misti | **(a)** — benchmark esterno e citabile, test gia' pronti, esercizi scelti perche' difficili; scaricati al commit `7e0611e` con verifica di un hash del contenuto, fuori da git. La verifica gira in una cartella pulita con i test originali ripristinati. Limiti: esercizi e soluzioni sono pubblici (rischio di contaminazione, e con accesso a internet l'agente potrebbe scaricare le soluzioni); non sono il dominio sperimentale (D16), servono solo a calibrare `f` del worker | ✅ accettata (a) — ott 2026 |
| **D18** | L'accesso a internet degli agenti e' una condizione sperimentale, con base senza rete | (a) condizione sperimentale con base senza rete; (b) rete libera sempre; (c) strumento web dedicato e controllato (rimandato a M7) | **(a)** — l'ipotesi da mostrare e' che un worker economico con internet possa avvicinarsi a uno costoso: senza la misura senza rete non si puo' dire quanto vale internet, e il confronto va fatto su entrambi i modelli con e senza. La rete e' un parametro dell'esecutore; sotto `bridge` un firewall nell'entrypoint chiude la macchina e la rete locale e l'utente finale non ha permessi. Provato con Docker, ramo IPv6 non provato | ✅ accettata (a) — ott 2026 |
| **D19** | Percorsi verso i modelli: LiteLLM esce dalla tesi | (a) Anthropic e Moonshot diretti, MiniMax via OpenRouter, Kimi su due strade per misurare la tassa; (b) tenere LiteLLM con account diretti; (c) spegnere la cache di LiteLLM | **(a)** — LiteLLM era un sistema personale fuori dal repository, con una cache locale che replicava le richieste identiche e falsava ripetizioni e costi; spegnerne la cache sarebbe stata una soluzione temporanea. Con credito gia' presente su OpenRouter non serve un account MiniMax. Conseguenze: il gateway nativo di Anthropic diventa provabile; la tassa dell'aggregatore si misura solo su un modello disponibile su entrambe le strade (Kimi); si toglie il codice del proxy | ✅ accettata (a) — ott 2026 |
| **D20** | Pool di modelli di M2s: `claude-opus-5.5`, `kimi-k3`, `minimax-m3`, senza selezione | (a) pool fissato senza misure di confronto; (b) selezione su 12 esercizi e poi su 34 fra 7 candidati (circa 9-45 dollari); (c) `claude-sonnet-5.5` come intermedio; (d) pool invariato (`opus-5`, `minimax-m2.7`) | **(a)** — per non spendere in questa fase. `claude-opus-5.5` costa circa il 20% in meno per token di `opus-5`; `minimax-m3` e' una scelta senza misura (unico indizio: siti aggregatori). La selezione fra famiglie, con il costo per esercizio risolto, si fa in M2b | ✅ accettata (a) — ott 2026 — sostituita da D38 (18 ott 2026) |
| **D21** | Una sola infrastruttura: OpenRouter | (a) tutti i modelli via OpenRouter con una chiave e il fornitore fissato per modello (`provider_order`, senza ripiego); (b) fornitori diretti (Anthropic, Moonshot, MiniMax) come in D19; (c) proxy locale | **(a)** — niente credito diretto su Anthropic e una sola infrastruttura da gestire, con chiavi e listini in un unico posto. Il fornitore fissato fa coincidere il costo riportato con quello calcolato sul listino (verificato su tre modelli). Conseguenze: la tassa dell'aggregatore di D19 non e' piu' misurabile e si sostituisce con il confronto costo riportato contro costo calcolato; il gateway nativo di Anthropic resta nel repository, scollegato (`docs/INFRASTRUTTURE_SCOLLEGATE.md`). Sostituisce D19 per fornitori e percorsi | ✅ accettata (a) — ott 2026 |
| **D22** | Parametri di richiesta per modello in configurazione | (a) campo facoltativo `extra_body` per modello in `models.toml`, validato dal registro e unito dalla fabbrica al vincolo del fornitore; (b) punti di cache espliciti sui messaggi, scritti nel gateway; (c) condizioni sul fornitore nel codice | **(a)** — un parametro nuovo si aggiunge con una riga di configurazione, senza condizioni sul fornitore nel codice (in linea con D9). Primo uso: `cache_control` per `opus-5-5`, misurato -37% di costo sulla stessa run. Chiavi riservate, che `extra_body` non puo' sovrascrivere: `provider`, `model`, `messages`, `tools`, `tool_choice`, `stream`; i valori devono essere serializzabili in JSON | ✅ accettata (a) — ott 2026 |
| **D23** | L'esito del turno attraversa il confine gateway-agente | (a) `AssistantTurn.outcome` (`COMPLETE`, `TOOL_REQUEST`, `TRUNCATED`, `REFUSED`, `ERROR`) tradotto dal gateway, stati di run in un'enumerazione; (b) solo controlli dentro il gateway; (c) (a) piu' un turno di recupero dopo una risposta vuota | **(a)** — «nessuna tool call» non significa «ho finito»: puo' essere un taglio per limite di token, un rifiuto, un errore o un silenzio. Una richiesta vera a `minimax-m3` con tetto di 8000 token li ha spesi tutti in ragionamento e si e' chiusa con `length`, senza testo. Una risposta vuota non si ritenta (la documentazione del fornitore lo sconsiglia) e diventa lo stato `empty_response`, cosi' la frequenza si misura. Un turno anomalo non entra nella storia e le sue tool call non si eseguono | ✅ accettata (a) — ott 2026 |
| **D24** | Registro dell'esito della run | (a) `summary.json` schema 4 con `last_finish_reason` e `final_message`; (b) lasciare il solo stato; (c) messaggio finale nel ledger di utilizzo | **(a)** — dopo una run fallita non si poteva leggere cosa avesse risposto l'agente, e le etichette di fallimento (`verification_failed`) mescolavano risposte vuote e soluzioni sbagliate. Serve anche al dataset di M2b.5 | ✅ accettata (a) — ott 2026 |
| **D25** | Costo degli stream interrotti e budget | (a) controllo a ogni tentativo e riconciliazione con `GET /generation`; prenotazione del caso peggiore rimandata a M3.4; (b) prenotazione subito; (c) niente riconciliazione | **(a)** — la prenotazione richiede un `max_tokens` per modello: senza, il caso peggiore e' il limite del modello (circa 0,61 dollari a chiamata) contro tetti di 0,15; con un tetto basso il ragionamento viene tagliato. Sonda del 14 ott: chiudere lo stream ferma la fatturazione e il costo si legge dopo circa 10 s (campione singolo, `minimax/fp8`) | ✅ accettata (a) — ott 2026 |
| **D26** | Assemblatore dei chunk dello streaming | (a) componente nostro, testato sui flussi veri della sonda; (b) accumulatore dell'SDK avvolto in controlli | **(a)** — l'accumulatore dell'SDK solleva `LengthFinishReasonError` su `length`, `AssertionError` su flusso vuoto e non segnala la troncatura (verificato); servono invece `length` come stato e la troncatura come errore | ✅ accettata (a) — ott 2026 |
| **D27** | Rilevamento degli stalli di uno stream su tre livelli | (a) timeout di lettura del client, misura dell'intervallo fra chunk, controllo su un thread che interrompe la connessione; (b) solo il timeout di lettura; (c) solo il controllo su un thread | **(a)** — i commenti keep-alive di OpenRouter azzerano il timeout di rete (compaiono ~0,4 s dopo l'ultimo chunk), quindi il solo timeout non scopre un modello che tace; il controllo sul contenuto serve, e la misura dell'intervallo permette di tararlo per modello (`stall_timeout_s`, default 120 s). L'interruzione si fa con `shutdown` del socket: `close()` da un altro thread non sblocca la lettura (prova locale, anche su TLS) | ✅ accettata (a) — ott 2026 |
| **D28** | Come si esegue in parallelo e come si governa il tetto di spesa | (a) modulo generico `parallel_runner.py` con partenze governate dal thread principale; (b) `ThreadPoolExecutor` direttamente in `run_campaign`; (c) API asincrona su `BuiltAgent`. Per il tetto: (i) solo la spesa registrata; (ii) spesa piu' tetto per run prenotato per le run in volo | **(a) e (ii)** — M4 riusa il modulo e l'isolamento si prova una volta sola; un agente ha una conversazione persistente, due incarichi insieme la corromperebbero (esclude (c)). Con 4 run in volo la sola spesa registrata lascerebbe sforare fino a 4 run: la prenotazione usa il tetto per run che c'e' gia' (non serve un `max_tokens` per modello). Il gruppo di thread ha gia' una coda: non se ne aggiunge un'altra; le partenze le decide il thread principale, cosi' spesa e lavori in volo si aggiornano senza lock. Resta uno sforamento limitato (una chiamata per run), da dichiarare in M3.4 | ✅ accettata (a), (ii) — ott 2026 |
| **D29** | Protocollo dell'esperimento anticipato di M2b.5 | (a) pacchetto `quality/` nel repository con test, protocollo in un file di dati, metriche in Python standard; (b) script sciolti fuori dal repository; (c) dentro `campaign.py`. Stimatore che vede istruzioni e codice (e non i test) | **(a)** — i numeri della tesi devono essere riproducibili da chi legge, e la sandbox, `parallel_runner` e il gateway esistente si riusano. Lo stimatore non vede i test perche' deve misurare la capacita' che avra' dove i test mancano. Regola di decisione scritta prima dei risultati (promettente: limite inferiore dell'AUROC >= 0,70 e a non piu' di 0,10 dal frontier; negativo: limite superiore <= 0,65) | ✅ accettata (a) — ott 2026 |
| **D30** | Limite ai container Docker contemporanei | (A) limitatore iniettato dalla fabbrica; (B) semaforo globale di modulo; (C) nessun limite oltre `workers`; (D) ibrido: parametro opzionale e istanza unica di modulo, posti come file bloccati con `fcntl.flock` | **(D)** — il limite riguarda una risorsa unica, la macchina: con (A) un limitatore dimenticato o duplicato aggira il limite in silenzio, (B) nasconde lo stato ai test, (C) non vale per lo swarm. I file valgono anche fra processi (piu' campagne insieme) e si liberano se il processo muore. Limite 6, `docker kill` con tempo massimo 10 s. Limiti dichiarati: container vivo con posto libero dopo crash o Ctrl+C, niente Windows | ✅ accettata (D) — ott 2026 |
| **D31** | Un solo punto di collegamento all'incarico in corso | (i) ripetitore di eventi per l'esecutore; (iii) `CurrentRun` dato una volta sola a contabile, gateway e strumenti; (iv) statistiche d'attesa nel limitatore | **(iii)** — (i) aggiungeva un ricollegamento da ricordare a ogni incarico (accoppiamento temporale), (iv) perdeva l'attribuzione all'agente. `CurrentRun` si stacca a fine incarico: un evento in ritardo e' un errore, non una riga in un ledger chiuso. `tools_builder` riceve `event_sink` (cambio d'interfaccia) | ✅ accettata (iii) — ott 2026 |
| **D32** | Contabile di squadra | (A) contabile vivo che somma i membri a ogni lettura; (B) riepilogo dai ledger a fine lavoro. Interfaccia: (C1) sottoclasse di `Accountant`; (C2) `SpendReader` separato; (C3) classe a se'. Conteggio: (C-a) tutta la vita dell'agente; (C-b) dall'ingresso in squadra | **(A), (C2), (C-b)** — il tetto di squadra (M4.2c) legge il totale mentre gli agenti lavorano; un `register` che sa solo fallire violerebbe sostituzione di Liskov e segregazione delle interfacce; la spesa di squadra non deve includere lavoro fatto altrove. Limite: un agente in una squadra alla volta (C-c rimandata a M4) | ✅ accettata (A), (C2), (C-b) — ott 2026 |
| **D33** | La prenotazione del tetto conta anche la run che parte (corregge D28) | (a) correggere il codice: `spent + (in_volo + 1) x riserva`; (b) correggere il testo della tesi | **(a)** — contando solo le run in volo lo sforamento poteva arrivare a un tetto intero per run (emerso dalla revisione indipendente) e §9.6 della tesi sarebbe stata falsa. Vale anche in serie; un tetto per run piu' alto del totale e' un errore all'avvio | ✅ accettata (a) — ott 2026 |
| **D34** | Strumenti dei file e workspace condiviso minimo | (B1) solo un test di carico su `Workspace`; (B2) `O_NOFOLLOW` in lettura e scrittura atomica; (B3) apertura un pezzo alla volta (`openat`) | **(B2)** — il rischio vero e' un link simbolico messo fra controllo e uso, non il carico su una funzione pura; la scrittura atomica rende definito l'esito di due scrittori (vince l'ultimo, mai un file a meta'). M3.3 ridotto a questo; cartella condivisa o copie con merge si decide in M4. Limite: cartella intermedia scambiata nello stesso istante | ✅ accettata (B2) — ott 2026 |
| **D35** | Terreno sperimentale della tesi | (a) siti web interi (conferma D16); (b) benchmark di modifica del codice (DeepSWE, Terminal-Bench); (c) entrambi | **(a)** — i dati per tentativo di DeepSWE v1.1 e Terminal-Bench 4.0, analizzati senza spesa, restano come indicazioni (modelli economici adatti, verificare l'esito rende piu' che prevederlo, sui task lunghi il risparmio scende); costano 10-20 volte una pagina e non sono il dominio della tesi | ✅ accettata (a) — 18 ott 2026 |
| **D36** | Contributo e pesi della tesi (sostituisce D13) | (a) router appreso come unico contributo; (b) il sistema e la scomposizione misurata del risparmio, router facoltativo | **(b)** — l'obiettivo e' il risparmio a qualita' uguale, qualunque leva lo produca. La struttura «planner forte, esecutori economici» e' gia' pubblicata (AgentCARD 2606.20629): la novita' difendibile e' il confronto equo sul dominio web e la misura di quale leva produce quanto risparmio (ablazioni). Valutazione co-centrale; ottimizzazione dell'harness come parte nuova; router appreso facoltativo (R7) o lavoro futuro | ✅ accettata (b) — 18 ott 2026 |
| **D37** | Condizione di convenienza dichiarata prima delle misure | (a) scriverla in tesi come ipotesi prima della campagna; (b) ricavarla dopo | **(a)** — lo sciame conviene se `m / r + q < 1` (m = token delle foglie rispetto al singolo forte, r = rapporto di prezzo pesato su input, cache e output reali, q = quota di planner ed escalation sul costo del singolo). Dichiarata prima, la misura puo' smentirla. Il risultato va presentato in funzione di r, perche' i prezzi cambiano | ✅ accettata (a) — 18 ott 2026 |
| **D38** | Rosa dei modelli (sostituisce D20) | (a) Opus 5.5 forte; DeepSeek V4 Pro e GLM 5.3 Flash economici; GPT-6.1 Sol intermedio; (b) rosa invariata | **(a)** — su DeepSWE v1 MiniMax M3 risolve il 20,4% a $5,57 per task; su v1.1 DeepSeek V4 Pro 62,8% a $0,24, GLM 5.3 Flash 63,4% a $0,48; su Terminal-Bench 4.0 GPT-6.1 Sol 58,6% a $1,94 contro Opus 5.5 65,2% a $14,30. Escono MiniMax M3 e Kimi K3. Versione e fornitore esatti da fissare in `models.toml` (il prezzo di DeepSeek varia di 3 volte fra versioni). DeepSeek V4 Pro non accetta immagini: il critico visivo deve essere un altro modello | ✅ accettata (a) — 18 ott 2026 — economico modificato da D47 (21 ott 2026): DeepSeek V4.1 Flash; intermedio modificato da D51 (24 ott 2026): Kimi K3.1 Pro |
| **D39** | Bracci sperimentali | A Opus 5.5 da solo; B Opus 5.5 con gli stessi strumenti e lo stesso ciclo di verifica di OrcV2; C OrcV2; D modello economico da solo con gli strumenti; E Opus con piu' tentativi a spesa uguale | **A, B, C, D** — C contro B isola l'orchestrazione (l'harness da solo sposta i risultati di vari punti a parita' di modello, 2605.23950); C contro A e' il numero di prodotto; D verifica che lo sciame serva. E resta un'opzione | ✅ accettata A-D — 18 ott 2026 — modificata da D45 (21 ott 2026): A tolto |
| **D40** | Compiti | (a) circa 10 WebGen-Bench (MIT) + circa 10 pagine ArtifactsBench + compiti nostri, circa 20, divisi fra sviluppo e test congelato; (b) solo compiti nostri | **(a)** — confrontabili con la letteratura, con casi di prova e checklist gia' pronti; la divisione di test non si guarda fino alla campagna finale | ✅ accettata (a) — 18 ott 2026 |
| **D41** | Valutazione della qualita' | (a) tre livelli: controlli automatici (Playwright, axe-core, 3 larghezze, script di interazione scritti prima), giudice a coppie in entrambi gli ordini di famiglie non in gara, voti umani alla cieca per verificare il giudice; (b) solo controlli automatici; (c) solo giudice | **(a)** — i modelli economici superano i controlli automatici ma perdono sul gusto; i giudici concordano con gli umani circa il 70% sulle pagine web (WebDevJudge 2510.18560) e preferiscono se stessi. Votanti: 4-6 persone (Vincenzo, familiari, amici, relatore), circa 50 coppie a testa. Giudice fra Gemini 4 Argon e Gemini 3.8 Flash, scelto in R1 per accordo con i voti umani | ✅ accettata (a) — 18 ott 2026 — giudice modificato da D52 (24 ott 2026): GPT-6.1 Sol via Codex CLI |
| **D42** | Regola delle ottimizzazioni dell'harness | (a) scelta in una fase dedicata (R4.0), una alla volta, misurata sui compiti di sviluppo, ogni strumento dato anche al braccio B; (b) integrare tutto subito | **(a)** — l'effetto di uno strumento dipende dal modello (2609.20804); senza misura e senza parita' con B il confronto non e' difendibile. Codice di harness aperti riusabile nel rispetto della licenza; niente reverse engineering di prodotti chiusi (termini commerciali) | ✅ accettata (a) — 18 ott 2026 |
| **D43** | Nuova ROADMAP e harness | (a) fasi R0-R7 sul nostro harness; (b) esperimenti dentro Harbor con mini-swe-agent; (c) ordine M4 -> M2b -> M7 invariato | **(a)** — R0 protocollo, R1 banco di prova, R2 baseline, R3 sciame per sezioni, R4.0 studio delle ottimizzazioni, R4 ottimizzazione manuale, R5 automatica, R6 campagna, R7 router facoltativo. Il nostro harness resta: (b) avrebbe sostituito il ciclo dell'agente per avere baseline pubblicate gratis, ma non sul dominio della tesi. M1, M2a, M3 restano come storia; M2s chiusa come superata (il dato su `f` lo da' il braccio D) | ✅ accettata (a) — 18 ott 2026 |
| **D44** | Budget sperimentale | (a) stima complessiva $60-130, preventivo prima di ogni fase (misurato per le campagne), tetto deciso fase per fase; (b) tetto unico fissato ora | **(a)** — le stime sono calcolate; il pilota di R2 le sostituisce con misure. Ogni esecuzione reale con `--budget-usd` | ✅ accettata (a) — 18 ott 2026 |
| **D45** | Bracci e dimensione della campagna (modifica D39 e la voce R6 di D43) | (a) A, B, C, D con 2-3 ripetizioni; (b) B, C, D, una esecuzione per compito, 20 compiti di test e 8 di sviluppo, scelti a sorte con seme e divisi a meta' fra siti di contenuto e applicazioni che girano nel browser | **(b)** — B contro C e' il confronto equo; A costa quanto B e aggiunge solo il numero «di prodotto»; D costa pochissimo e risponde a «basta il modello economico da solo?». A parita' di spesa piu' compiti informano piu' di piu' ripetizioni, perche' le ripetizioni dello stesso compito si somigliano. Costo calcolato della campagna circa $20, da sostituire con la misura del pilota di R2; precisione circa ±22 punti sulla quota di confronti vinti | ✅ accettata (b) — 21 ott 2026 |
| **D46** | Metrica principale e margini (dettaglia D41) | (a) un voto unico pesato fra funzionamento e giudizio; (b) due metriche affiancate: punteggio dei controlli automatici con credito parziale e voto graduato del giudice (−2..+2, entrambi gli ordini), non inferiorita' richiesta su entrambe | **(b)** — niente pesi arbitrari, e si vede dove C regge e dove no. τ_funziona = 10 punti su 100. Il voto graduato da' piu' informazione di una scelta secca: con 20 compiti l'intervallo di una quota di vittorie e' circa ±22 punti. τ_piace si fissa dopo il pilota di R2 e prima di ogni confronto C contro B | ✅ accettata (b) — 21 ott 2026 |
| **D47** | Modello economico (modifica D38) | (a) DeepSeek V4 Pro `-0813` sull'endpoint DeepSeek, 0,66 / 1,98 $/M, senza immagini; (b) DeepSeek V4.1 Flash `-1017` sull'endpoint DeepSeek, 0,15 / 0,60 $/M, con immagini | **(b)** — costa circa un quarto, vede le immagini (puo' fare anche il critico) e nella tabella del suo paper (arXiv 2609.19969) supera V4 Pro nei test agentici (DeepSWE v1.1 74,2 contro 62,7, cifre del produttore). Nessuno dei due e' provato sulla generazione di siti: lo misura il pilota di R2. Nei giorni feriali, 01-04 e 06-10 UTC, il prezzo raddoppia: le run si lanciano fuori da quelle fasce. Usato dai worker di OrcV2 e dal braccio D | ✅ accettata (b) — 21 ott 2026 |
| **D48** | Meccanismo centrale: verifica eseguibile invece della previsione (modifica D36 e il pilastro «routing» di `TESI_master.md` §0-§3; toglie R7 da D43) | (a) il sistema decide quando passare al modello forte **verificando il sito eseguito** con controlli gratuiti e visibili all'agente (avvio, errori, test propri), e la tesi misura questa verifica come leva; il router predittivo esce dal piano e diventa lavoro futuro; (b) invariato: router predittivo facoltativo in R7 | **(a)** — prove convergenti, tutte verificate su fonte fissata il 22-23 ott 2026: l'analisi di R0 (prevedere quale modello basta perde 8-14 punti fuori campione); NadirClaw (v0.25.1, `MODEL_CARD.md`) separa i casi da passare al forte con AUROC ≈ 0,62 leggendo solo la richiesta, e il suo verificatore testuale ha AUROC 0,65 sul codice, tanto che le regole del prodotto lo scavalcano appena compare `def ` (`cascade_rules/profiles/default.yaml`); il giudice di Switchyard ospitato su OpenRouter presume che il modello economico fallisca sui lavori di codice sostanziali; la verifica del candidato prima di servirlo (VGR di Switchyard) esiste solo come modalita' sperimentale e non misurata. Nessuno dei router esaminati esegue il sito prodotto: il renderer di R1 lo fa. Vincoli: il cancello non vede mai script, domande o riferimenti della valutazione; copre «funziona», non «piace». Originalita' da verificare contro la letteratura sulla generazione web con verifica (WebGen-Agent e simili) prima di dichiararla | ✅ accettata (a) — 23 ott 2026 |
| **D49** | Scala di politiche (modifica D39 e D45) | (a) bracci B, C, D invariati; (b) oltre a B, C, D, due politiche semplici con gli stessi strumenti: **V**, cascata D→B (si tiene il sito di D se supera il cancello di D48, altrimenti il sito di B fatto da zero) e **H**, Plan/Execute (Opus fino alla prima scrittura di un file, poi il modello economico con tutta la storia); tutte riportate sul piano costo-qualita' | **(b)** — sono le obiezioni piu' prevedibili a C. Su DeepSWE v1.1 il Plan/Execute di Switchyard (GPT-5.6 Sol → Luna) risolve il 60,8% a $180,51 per suite contro il 62,8% a $720,95 di Sol da solo (3 esecuzioni, profilo `deepswe-v11-plan-execute-luna-sol.toml` al commit `7558a1d`): −75% di costo a −2 punti. Su SWE-Atlas (40 compiti) il modello economico da solo risolve quanto il forte e quanto il router (15/40) e costa meno di entrambi. La prova principale resta C contro B (`PROTOCOLLO.md` §10); D, V e H si riportano con intervallo, senza dichiarazioni di significativita'. **V non costa generazione ne' giudizio in piu':** B parte da zero e non dipende da D, quindi V si compone dalle esecuzioni di B e D gia' previste piu' il cancello, che e' gratuito; il suo sito coincide con quello di D (coppia D-B gia' giudicata) o con quello di B (voto 0). H costa un'esecuzione per compito e le coppie H-B | ✅ accettata (b) — 23 ott 2026 |
| **D50** | Pilota di R2 (dettaglia R2.4) | (a) B e D sui 3 compiti pilota; (b) anche H, e V composta da B e D | **(b)** — da' i primi valori delle due quantita' che decidono quanto pesano V e H: la quota `a` di compiti in cui il sito di D supera il cancello e la quota di spesa di Opus in H. Spesa aggiuntiva: solo le esecuzioni di H; nel pilota H e V si misurano con «funziona» e costo, senza giudice. Sostituisce l'idea di H come sola ablazione di R6.4 | ✅ accettata (b) — 23 ott 2026 |
| **D51** | Modello intermedio (modifica D38) | (a) GPT-6.1 Sol; (b) Kimi K3.1 Pro, anche nel ruolo `worker` | **(b)** — aggiornamento della rosa scelto prima delle misure della campagna. Identificativo `moonshotai/kimi-k3.1-pro`, endpoint standard `moonshotai/mxfp4`; listino OpenRouter verificato il 24 ott 2026: input 2, output 10, lettura cache 0,20 dollari per milione di token, immagini e strumenti supportati. Nessun prezzo di scrittura cache pubblicato da quell'endpoint. GPT-6.1 Sol e Kimi K3 conservati senza ruolo per i dati storici. Non implica una superiorita' misurata di K3.1 Pro; D47 e la scelta finale dei worker di C in R2.3 restano distinte | ✅ accettata (b) — 24 ott 2026 |
| **D52** | Giudice a coppie (modifica D41 e R1.9) | (a) Gemini 4 Argon o 3.8 Flash via API, scelto per accordo con i voti umani; (b) GPT-6.1 Sol via Codex CLI con l'abbonamento dell'autore; (c) GPT-6.1 Sol via API | **(b)** — scelta dell'autore per non spendere sul giudice. Famiglia non in gara dopo D51 (nessun braccio usa modelli OpenAI); Kimi K3.1 escluso perche' e' il `worker`. Codex CLI 0.164.0 accetta immagini (`-i`), modello fissato (`-m`) e uscita vincolata (`--output-schema`). Limiti da dichiarare: istruzioni di sistema dello strumento non controllabili, temperatura non fissabile, limiti di messaggi dell'abbonamento, costo non misurato (il giudice non entra nel costo dei bracci). La calibrazione con i voti umani (R1.10) resta identica e decide se il giudice si usa; il confronto fra i due Gemini cade | ✅ accettata (b) — 24 ott 2026 |
| **D55** | Riduzione del piano per la scadenza della tesi (modifica D36, D45, D49 e le fasi R2-R6) | (A) piano MVP: sciame minimo senza critico, cancello di avvio ed errori, campagna B, D, C sui 5 compiti di sviluppo con V composta, H facoltativo, R4-R5 e ablazioni lavoro futuro; (B) niente sciame: V e H contro B; (C) piano invariato | **(A)** — tesi triennale da chiudere entro l'8 novembre 2026; il piano R2-R6 non ci stava. (B) toglieva lo sciame, oggetto della tesi. Conseguenze dichiarate: risultato come stima su 5 compiti, nessun compito di test separato, scomposizione del risparmio ridotta a V e C. Dettagli in `ROADMAP.md`, «Piano MVP», e `PROTOCOLLO.md` §0 | ✅ accettata (A) — 29 ott 2026 |

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
