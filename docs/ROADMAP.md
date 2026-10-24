# ORC — Roadmap

> **Cos'e'.** Il piano vigente del progetto: cosa fare, in che ordine, con quali scelte ancora da fare e quando
> una fase e' finita. Le fasi M1-M7 scritte fino al 18 ottobre 2026 sono in `ROADMAP_storico.md`: M1, M2a e M3
> sono completate e restano la base del codice; M2s e' chiusa come superata; M4, M2b e M7 sono sostituite dalle
> fasi R0-R7 (D43); R7 e' stata tolta il 23 ottobre 2026 (D48). Molte analisi di quelle fasi valgono ancora e sono
> riprese qui, con il rimando alla riga.
>
> **Come si usa.** Si apre la fase corrente e si prende il primo task non chiuso nell'ordine indicato. Ogni task
> ha la stessa forma: **Obiettivo**, **Gia' deciso**, **Scelte aperte** (`[SCELTA]`, con alternative e una
> raccomandazione: le decide l'autore, una alla volta, prima di scrivere il codice che ne dipende), **Passi**,
> **⚠️ Trappole**, **Test**, **Costo** (calcolato o misurato, sempre detto quale) e **Fatto quando**. Una fase si
> chiude quando la sua *Definition of Done* e' tutta spuntata e verificata; a fine fase si aggiorna la tabella qui
> sotto e si abbozza la sezione di tesi.
>
> **Cosa non e' questo file.** Non e' un diario: misure ed esiti vanno nella tesi o nel registro della fase. Le
> regole dell'esperimento stanno in `PROTOCOLLO.md`, le decisioni con la loro motivazione nel registro di
> `PIANO_completo.md`. Se questo file e il protocollo divergono, vale il protocollo e questo file si corregge.

## Stato generale

| Fase | Nome | Stato |
|---|---|---|
| M1, M2a, M3 | Agente singolo, infrastruttura di misura, parallelismo | ✅ completate (base del codice) |
| M2s | Routing statico per ruolo | ✅ chiusa come superata (D43) |
| M4, M2b, M7 | Swarm, routing, campagna | ↪️ sostituite da R0-R7 (D43); testo in `ROADMAP_storico.md` |
| R0 | Decisioni e protocollo | ✅ 21 ott 2026 (D35-D47); rivista il 21 ott durante R1 e il 23 ott (D48-D50, vedi sotto) |
| **R1** | **Banco di prova: compiti, esecuzione dei siti, controlli, giudice, voti umani** | 🟡 **in corso**: R1.1 fatto (da committare) |
| R2 | Strumenti comuni, baseline e politiche semplici (cancello, H, pilota, preventivo misurato) | ⬜ |
| R3 | OrcV2 minimo: sciame per sezioni | ⬜ |
| R4.0 / R4 | Studio delle ottimizzazioni / ottimizzazione manuale | ⬜ |
| R5 | Ottimizzazione automatica (facoltativa) | ⬜ |
| R6 | Campagna finale, scala di politiche e ablazioni | ⬜ |
| R7 | Router grossolano | ❌ tolta il 23 ott 2026 (D48): lavoro futuro |

**Percorso e dipendenze.** R0 → R1 → R2 → R3 → R4.0 → R4 → (R5) → R6.
- R1 fornisce **come si misura** (esecuzione, controlli, giudice validato). Senza R1 nessun numero di R2-R6 vale.
- R2 fornisce **gli strumenti comuni**, la **parita' fra bracci** (tetti, ragionamento, ciclo di verifica), il
  **cancello eseguibile** (D48) e il braccio **H** (D49). B, C, D e H devono avere gli stessi strumenti (D39, D42):
  per questo nascono in R2 e non dentro lo sciame. Il pilota misura per primo le due quantita' che dicono quanto
  pesano le politiche semplici: `a` per V e la quota di Opus in H (D50).
- R3 costruisce C sopra gli strumenti e il cancello di R2; R4 li migliora dandoli anche a B, D e H.
- R6 usa tutto congelato: protocollo, compiti di test, checklist, giudice, versioni dei modelli.

**Dove sta il contributo (D36, D48, D49).** Il sistema e la scomposizione misurata del risparmio: quale leva
(strumenti, sezioni, verifica, ottimizzazione, modelli economici sul server) produce quanto risparmio a qualita' non
inferiore. Il meccanismo che decide quando passare al forte e' la **verifica eseguibile** del sito, non una
previsione (D48). Lo sciame si confronta con il forte da solo (prova principale) e con politiche piu' semplici sugli
stessi modelli, la cascata V e Plan/Execute H (D49), cosi' il risultato dice quale leva basta, qualunque sia. La
valutazione e' co-centrale; il router appreso e' lavoro futuro.

## Le quattro questioni che decidono la riuscita (da chiudere prima del congelamento)

1. **Potenza della prova (R6.1).** Con 20 compiti, deviazione standard ipotizzata di 25 punti e τ_funziona = 10,
   l'intervallo al 95% della differenza media ha semi-ampiezza ≈ 11 punti: anche se C e B fossero davvero uguali,
   la non inferiorita' si dimostrerebbe solo circa 4 volte su 10, e su due metriche insieme ancora meno. Per una
   potenza dell'80% a differenza vera nulla servono ≈ (1,96 + 0,84)² · 25² / 10² ≈ 49 compiti. Le leve sono il
   numero di compiti, τ, la variabilita' reale (da misurare in R2-R4) o il modo di presentare il risultato. Oggi
   nessuna scelta e' fatta: e' la decisione piu' importante non ancora presa.
2. **Equita' fra bracci (R2.5, R4).** «Stessi strumenti e stesso ciclo di verifica» (D39) va tradotto in regole:
   tetti per braccio, sforzo di ragionamento, cosa sostituisce per B il critico di C, messa a punto dei prompt
   anche per B. Senza, il confronto C contro B si puo' contestare.
3. **Validita' del giudice (R1.9).** Anche fra persone l'accordo sull'estetica di pagine web e' modesto (Fleiss κ
   0,26-0,46, Design2Code 2403.03163). La soglia di accettazione del giudice e il piano B vanno scritti prima di
   vedere i voti.
4. **Il rivale semplice (D49, R2.4).** Se la cascata V o Plan/Execute H costano quanto C a qualita' pari, lo sciame
   non aggiunge nulla su questi compiti. Le condizioni sono scritte prima delle misure (`TESI_master.md` §0.2): V
   conviene su B se `a > c_D`; C batte V sul costo, in prima approssimazione, se la quota di Opus `q` resta sotto
   `1 − a`. Il pilota da' i primi valori di `a` e della quota di Opus in H: se V o H arrivano vicini a B gia' li',
   la sezione di tesi sui risultati va impostata su «quale leva basta» prima di R3, non dopo R6.

**Calendario dei prezzi.** Gemini 4 Argon costa 2/10 $/M fino al 30 nov 2026 e 4/20 $/M dal 1 dic; Gemini 3.8
Flash su Google 0,75/3,75 $/M fino al 31 dic, poi 1,50/7,50 (ai.google.dev/gemini-api/docs/pricing, letta il 21
ott 2026). Su OpenRouter 3.8 Flash risulta 0,825/4,125, ma `models.toml:220-225` lo prezza 0,75/3,75: il listino
del progetto potrebbe sottostimare del 10% (da verificare con una chiamata in R1.8). La calibrazione del giudice
(R1) cade nel periodo scontato, la campagna (R6) probabilmente no: il preventivo di R6 va fatto sul listino pieno.

---

## Fasi R0-R7 (riprogettazione del 18 ottobre 2026)

**Perche'.** Prima di aprire M4 e' stata fatta un'analisi della letteratura recente (STORM, CAID, AgentRoom,
Kim et al. 2512.08296, AgentRouter, AgentCARD) e dei dati per tentativo di DeepSWE v1.1 e Terminal-Bench 4.0,
senza spesa. Esiti: a parita' di modello un sistema multi-agente costa 1,5-4,4 volte l'agente singolo; il
risparmio viene dai modelli economici, ma solo se il risultato viene **verificato** (prevedere in anticipo quale
modello basta perde 8-14 punti fuori campione); il risparmio dipende dal tipo di compito; l'harness pesa quanto il
modello.

**Cosa resta uguale.** La frase della tesi (`min costo s.t. qualita' >= τ`), il dominio dei siti web (D16, D35),
l'architettura (planner, worker, verifica), il codice di M1-M3.

**Cosa cambia.** Contributo = sistema e scomposizione del risparmio (D36); modelli (D38, D47); confronto equo con
Opus dotato degli stessi strumenti (D39, D45); valutazione a tre livelli verificata con voti umani (D41, D46); fase
di ottimizzazione dell'harness (D42); ordine dei lavori (D43).

**Revisione del 21 ottobre 2026 (durante R1).** Tre scelte di R0 sono state riviste prima di qualunque misura
(`PROTOCOLLO.md` §2): (1) le applicazioni possono avere un **server** e usare framework con compilazione; (2) per
ogni applicazione si scrive prima un **contratto delle rotte** e i test colpiscono anche il server; (3) per ora
**5 compiti di sviluppo** completi, numero dei compiti di test da decidere prima di R6. Motivo: compiti piu' vicini
a quelli reali; il server e' una parte del lavoro dove il risparmio con modelli economici e' plausibile. Il
registro e' indietro: D40 e D45 dicono ancora circa 20 compiti, 8 di sviluppo, applicazioni solo nel browser. Va
scritta e approvata una voce D di revisione.

**Revisione del 23 ottobre 2026 (D48-D50, durante R1).** Un'analisi dei router gia' pronti (Switchyard, NadirClaw,
Conduit, RouteLLM, Not Diamond, Arch-Router, RouteFM, router di OpenRouter; sintesi e fonti in `TESI_master.md`
§7.3) ha cambiato il disegno, non il codice gia' scritto:
1. **Verifica invece di previsione (D48).** Sul codice prevedere quale modello basta separa male i casi (AUROC ≈
   0,62 per un classificatore che legge solo la richiesta; 0,65 per un verificatore testuale), mentre verificare il
   risultato rende. Il renderer di R1 diventa anche il **cancello** del sistema: controlli gratuiti sul sito, visibili
   all'agente, mai gli script o le domande della valutazione. R7 (router che prevede) esce dal piano.
2. **Scala di politiche (D49).** Oltre a B, C, D: **V**, cascata D→B (sito di D se passa il cancello, altrimenti
   quello di B) e **H**, Plan/Execute (Opus fino alla prima scrittura di un file, poi l'economico). Su DeepSWE v1.1
   Plan/Execute costa il 75% in meno del forte a −2 punti: e' l'obiezione piu' prevedibile a C. V non costa nulla in
   piu' (si compone da B e D); H costa un'esecuzione per compito.
3. **Pilota esteso (D50).** H e V entrano gia' nel pilota di R2.4, misurati con «funziona» e costo.
Restano invariati: la prova principale (C contro B, non inferiorita' su due metriche), i compiti, la valutazione.
Miglioramenti minori ricavati dalla stessa analisi: innesco dell'escalation (R3.4), costo del lavoro scartato
(R3.6), consigliere (R4), compressione del contesto (R4), replay (R6.4).

---

### R0 — Decisioni e protocollo ✅

- [x] Decisioni D35-D47 nel registro di `PIANO_completo.md`.
- [x] Protocollo in `docs/PROTOCOLLO.md`, deciso una voce alla volta:
      R0-1 fissaggio con un commit pubblicato prima di R6 · R0-2 tipo di compito (rivisto in R1) · R0-3 bracci B, C,
      D e dimensione (D45, rivista in R1) · R0-4 controlli come punteggio con credito parziale · R0-5 due metriche,
      «funziona» e «piace» (D46) · R0-6 voto graduato −2..+2, τ_funziona = 10, τ_piace dopo il pilota · R0-7 sei
      domande fisse + 2-4 per compito · R0-8 bootstrap sui compiti al 2,5% con test t di controllo · R0-9 «funziona»
      = quota di passi superati dello script d'interazione · R0-10 seme 20261021 e DeepSeek V4.1 Flash (D47).
- [x] `models.toml` con la rosa D38/D47, fornitori fissati, visione verificata; Opus con `cache_control` in
      `extra_body` (`models.toml:154`; cache verificata il 12 ott su una prova isolata).
- [x] Condizione di convenienza D37 in tesi prima delle misure (`TESI_master.md` §0.1).

---

### R1 — Banco di prova 🟡

**Obiettivo.** Uno strumento di misura di cui ci si possa fidare: dato un sito generato da un braccio qualunque,
produrre in modo ripetibile il punteggio «funziona» (0-100), le metriche secondarie (server, sbordo,
accessibilita', errori), gli screenshot e il voto «piace» di un giudice di cui si e' misurato l'accordo con persone
vere. **Prerequisiti:** R0. **Sezione di tesi:** metodo sperimentale (compiti, metriche, validazione del giudice).
**Non fa:** non genera siti con i bracci (R2-R3).

**Gia' deciso (21 ott 2026, `PROTOCOLLO.md` §2 e §6).**
- Filtro lungo l'ordine estratto (P3-D1): pre-filtro per etichetta, mescolamento con il seme, lettura in ordine
  con un verdetto scritto per ogni compito letto.
- Applicazioni web complete ammesse, con server e framework compilati; esclusi API a pagamento o con chiave, AI,
  invio di email, mini-program, programmi desktop (P11-D1). Giochi esclusi (P6-D1). Pre-filtro di ArtifactsBench
  sulle famiglie web (P9-D1). Copie dei dati fissate a un commit con sha256 (P7-D1).
- Contratto delle rotte per ogni applicazione, test diretti sul server, avvio entro 60 s (P12-D1).
- 5 compiti di sviluppo: `000098` noleggio auto, `000040` consulenza con vendita di servizi, `000058` coaching,
  `842` cruscotto «Security Center», `684` gestione di file con etichette (sostituisce `1594`, scartato il 22 ott
  per contenuto non verificabile). Completezza = almeno 3 funzioni verificabili nel testo.
- Giudice Gemini (famiglia non in gara), fra Gemini 4 Argon e 3.8 Flash per accordo con i voti umani (D41);
  entrambi gia' nel registro con la visione (`models.toml:213-225`).

**Ordine dei task (rispetta le dipendenze).**
R1.1 ✅ → **R1.2** (scelte sulle convenzioni) → **R1.3** (contratti e domande: servono al prompt e agli script) →
**R1.4** (esecuzione e rendering) → **R1.5** (risultato strutturato) → **R1.6** (controlli automatici) → **R1.7**
(script d'interazione) → **R1.8** (fonte delle coppie e strumento di voto) → **R1.9** (giudice) → **R1.10** (voti e
scelta del giudice). R1.11 (manutenzione) quando capita, prima di R2. Al termine di R1.3 si chiudono i prompt.

#### R1.1 — Compiti: scaricamento, filtro e sorteggio ✅ (da committare)
- **Fatto:** `webtasks.py` (lettura dei due formati, pre-filtro, ordine col seme, scelta lungo l'ordine che
  rifiuta compiti saltati o giudicati fuori turno, scaricamento con sha256), `campaigns/r1_compiti.toml`
  (verdetti), comando `python campaign.py fetch-webtasks`, `tests/test_webtasks.py` (23 test + 1 prova reale).
- **Verificato il 21 ott:** suite 832 passati, pyright 0 errori; prova reale con `ORC_INTEGRATION=1` passata.
- **Resta:** rilettura dell'autore con le domande di verifica; revisione indipendente (modello a scelta).
- **⚠️ Trappola:** il file di ArtifactsBench si chiama `.json` ma e' JSONL: si salva come `.jsonl`, l'hash resta
  quello dei byte originali.

#### R1.2 — Il compito come lo vedono i bracci: convenzioni
- **Obiettivo:** un unico modo, uguale per B, C, D e H, di trasformare un compito in istruzioni e di dire dove e come
  consegnare. Tutto cio' che e' qui entra nel prompt e quindi nel confronto.
- **Gia' deciso:** contratto delle rotte nel prompt (P12-D1); un solo comando di avvio su una porta fissa (§2).
- **Scelte aperte:**
  - ✅ **Marcatori per lo script d'interazione (22 ott):** `data-testid` obbligatori nel prompt, fino a 12 per compito
    (scartate la ricerca per testo, fragile, e l'agente con un modello come WebGen-Bench, a pagamento e non
    deterministico).
  - ✅ **Preambolo di ArtifactsBench (22 ott):** «You are a code expert…» (in 1822 compiti su 1825) si tiene com'e':
    arriva identico a tutti i bracci, quindi non tocca il confronto, ed e' fedele alla fonte. Si rivede solo se nel
    pilota di R2 i modelli rispondono con un blocco di codice invece di scrivere i file.
  - ✅ **Consegna (22 ott):** `start.sh` nella radice del workspace avvia il sito in primo piano sulla porta 8080,
    per qualunque tecnologia (sito statico, Node, Python). `start.sh` mancante o rotto vale come sito che non parte.
  - ✅ **Compilazione e dipendenze (22 ott):** le fa l'agente durante la generazione, nel workspace (`node_modules`,
    build, venv per Python), con lockfile obbligatorio; `start.sh` avvia soltanto e i 60 s valgono per l'avvio; la
    valutazione non scarica nulla. Il workspace si archivia in `runs/` senza `node_modules` (ricostruibile dal
    lockfile), dichiarandolo.
  - ✅ **Immagini dei contenuti (22 ott):** si generano. Strumento «genera immagine» identico per B, C e D (D42),
    con un modello d'immagini via OpenRouter (stessa chiave, gateway e ledger; la spesa entra nel costo per pagina).
    Il modello si sceglie con una prova su 5-10 immagini a costo misurato (preventivo prima); candidato indicato
    dall'autore: `openai/gpt-image-2.5-sunburst` (OpenAI, dal 9 set 2026, listino OpenRouter 8/8 $/M e
    `image_output` 0,00003 con unita' da misurare). ⚠️ L'elenco `/api/v1/models` di OpenRouter non mostra i modelli
    che producono solo immagini: i candidati vanno cercati sul sito o con `/models/<id>/endpoints`. Un modello
    Google farebbe immagini della stessa casa del giudice: non sposta il confronto fra bracci, ma un modello OpenAI
    evita il dubbio. Lo strumento nasce in R2 con gli altri strumenti comuni.
  - ✅ **Contenuti non verificabili, `1594` scartato (22 ott, revisione):** regola nuova, valida anche per i compiti
    di test: si scartano i compiti il cui contenuto principale e' in una lingua o in un dominio che giudice e votanti
    non sanno verificare. `1594` (poesie di Su Shi con pinyin) esce; il sostituto e' il successivo valido
    nell'ordine di ArtifactsBench, scelto dopo la regola delle quote qui sotto.
  - ✅ **Nessuna quota per tipo nello sviluppo (22 ott):** i compiti di sviluppo sono 5 siti web presi nell'ordine
    estratto con le regole di validita', senza distinguere siti di contenuto e applicazioni. Il sostituto di `1594` e'
    `684` (gestione di file con etichette e filtri), primo valido dopo di lui. Il criterio sito/applicazione e le quote
    si riprendono solo per i compiti di test, prima di R6.
  - ✅ **Rete durante la generazione e soluzioni pubbliche (22 ott): rischio accettato, nessuna contromisura.** Le
    risposte di 20 modelli sui compiti di ArtifactsBench sono pubbliche (`dataset/release_data_20250725/`) e
    WebGen-Bench pubblica un `outputs.zip`; il firewall non blocca GitHub ne' Hugging Face. Si dichiara come limite in
    tesi. Contromisure possibili, se servissero: controllo a posteriori dei comandi nel ledger, blocco dei domini.
- **⚠️ Trappole:** script di valutazione, domande del giudice e siti di riferimento non entrano mai nel workspace ne'
  nel prompt di nessun braccio (stessa regola della soluzione di riferimento in Polyglot, `polyglot.py:8-17`). I
  colori richiesti dai compiti di WebGen-Bench («papaya whip», «dark orange») restano: sono verificabili.
- **Passi:** dopo R1.3, funzione che da un `WebTask` produce il prompt (cornice comune + testo + contratto +
  marcatori + convenzione di consegna) e il passaggio `WebTask → Task` della campagna (oggi `WebTask` non ha
  `prompt` ne' `verify`, `webtasks.py:106`). Se R2.6 sceglie il cancello con test propri, la convenzione `test.sh`
  entra nella cornice comune, uguale per tutti i bracci (D48).
- **Test:** il prompt contiene contratto, marcatori e convenzione e non contiene script ne' domande; la frase fissa
  sparisce da tutte le varianti presenti nel file vero.
- **Fatto quando:** scelte registrate in `PROTOCOLLO.md`; dopo R1.3, 5 prompt riletti dall'autore.

#### R1.3 — Contratti delle rotte e domande per compito (materia della tesi) ✅ (23 ott: `campaigns/r1_valutazione/*.md`, approvati)
- **Obiettivo:** prima di qualunque generazione, il contratto delle rotte di ogni applicazione e le 2-4 domande del
  giudice per ogni compito (`PROTOCOLLO.md` §6), piu' l'elenco dei marcatori se R1.2 sceglie (a).
- ✅ **Quali compiti hanno un contratto (22 ott):** i 4 il cui testo chiede funzioni sui dati dell'utente (`000098`,
  `000040`, `000058`, `684`); `842` (cruscotto con dati di monitoraggio simulati) no: per lui contano script
  d'interfaccia e giudice. Regola per i compiti di test: contratto se il testo chiede di salvare, elaborare o
  condividere dati dell'utente.
- **Chi scrive:** sono definizioni scientifiche della valutazione: si prepara una bozza, l'autore la
  corregge e l'approva.
- `[SCELTA]` **Formato del contratto.** (a) Tabella in testo (metodo, percorso, corpo, risposta, codici di
  errore); (b) OpenAPI. Raccomandazione: (a). Il contratto dice anche dove persistono i dati (file JSON o SQLite
  nel workspace), altrimenti il test «dopo riavvio» e' ingiusto, e quanto vincola: nomi dei campi e codici HTTP
  si', struttura interna del server no.
- **Fatto quando:** contratti, domande e marcatori nel repository, datati, prima della prima generazione.

#### R1.4 — Esecuzione del sito e rendering ✅ (22 ott, da committare)
- **Obiettivo:** avviare il sito consegnato, aspettare che risponda, aprirlo con un browser vero a 375, 768 e
  1440 px e raccogliere screenshot, errori e metriche, sempre nello stesso modo.
- **Stato del codice:** l'immagine sandbox (Debian bookworm, Python 3.14, Node 24, `docker/sandbox.Dockerfile:9-24`)
  esegue ogni comando in un container nuovo e usa e getta (`executors/docker.py:367-381`), senza porte esposte;
  Playwright, Chromium e axe-core non sono nel progetto.
- **Scelte aperte:**
  - ✅ (22 ott: (a)) **Dove gira il browser.** (a) Immagine «renderer» costruita `FROM` l'immagine sandbox piu' Chromium
    (installato con `playwright install --with-deps chromium` a versione bloccata): stesso Python, stesso Node,
    stesse librerie di sistema in cui il sito e' stato compilato; server e browser nello stesso container, il server
    si raggiunge su `localhost`; (b) l'immagine ufficiale `mcr.microsoft.com/playwright/python:v1.64.0-noble` (circa
    1 GB compresso; Ubuntu, non Debian: i moduli nativi compilati nella sandbox, come esbuild o better-sqlite3,
    possono non girarci); (c) Playwright sull'host: non funziona col firewall, che blocca 172.16.0.0/12 in uscita e
    quindi anche le risposte verso un altro container. Raccomandazione: (a). Dipendenza nuova (pacchetto
    `playwright` e browser): scelta dell'autore.
  - ✅ (22 ott: (a)) **Rete durante la valutazione.** (a) Nessuna rete: ripetibile; coerente con «dipendenze nel
    workspace» di R1.2; un sito che carica librerie da CDN si vede rotto, e la regola va scritta nel prompt; (b)
    `bridge`: il sito si vede come lo vedrebbe un utente, ma il risultato dipende da terzi. Oggi la verifica gira
    sempre senza rete (`campaign.py:142-150`). Raccomandazione: (a).
  - ✅ (22 ott) **Screenshot.** Pagina intera tagliata a un'altezza massima (es. 4000 px) e un solo stato: per i
    siti la pagina iniziale, per le applicazioni la pagina dopo lo script (con dati). Un secondo stato raddoppia le
    immagini del giudice (12 invece di 6 per coppia) e si aggiunge solo se la calibrazione mostra che serve.
- **Gia' noto dalle fonti (repository letti il 21 ott):** WebGen-Bench avvia con `npm install` in tre tentativi
  (normale, `--force`, `--legacy-peer-deps`) e `npm run dev` sotto pm2, scoprendo la porta dai log entro 60 s;
  ArtifactsBench apre la pagina come `file://`, aspetta `networkidle` e fa 3 screenshot a 1 s di distanza. Si
  riprende l'idea, non il codice (WebGen-Bench contiene una chiave API in chiaro in
  `src/ui_test_bolt/ui_eval_with_answer.py`).
- **Passi:** immagine renderer con versione bloccata; esecuzione «lunga» in un solo container (server in
  background, attesa della porta con tempo massimo, browser, arresto); limiti propri (memoria ≥ 2 GB, `--ipc=host`
  o `--shm-size`, `--init`, pids piu' alti: Chromium conta anche i thread); utente non privilegiato e profilo
  seccomp di Playwright; congelamento di animazioni e orologio prima degli screenshot.
- **⚠️ Trappole:** i limiti attuali (512 MB, 256 pid, `config.py:167-168`) uccidono Chromium; il timeout di 60 s
  per comando (`config.py:174`) non basta per avvio + 3 larghezze + axe; `ContainerLimiter` a 6 posti
  (`config.py:172`) conta anche i renderer; un server che scrive fuori dal workspace perde la persistenza fra due
  avvii (`executors/docker.py:372-373`).
- **Test:** un sito statico e una mini applicazione Node scritti nei test producono le stesse metriche e gli stessi
  screenshot (differenza sotto soglia) in due esecuzioni; un sito che non parte entro 60 s produce «avvio fallito»,
  non un'eccezione; un tentativo di uscire in rete fallisce in modo pulito. Prove Docker con `ORC_INTEGRATION=1`.
- **Costo:** zero.
- **Fatto (22 ott):** `renderer.py` (copia del workspace, comando del container, lettura del risultato, guasti),
  `docker/render_site.py` (avvio di `start.sh`, attesa della porta, Chromium a tre larghezze, errori, sbordo,
  screenshot), `docker/renderer.Dockerfile` (sandbox + Playwright 1.64.0 + Chromium 156; immagine `orc-renderer:r1`,
  2,1 GB), `tests/test_renderer.py` (12 test + 4 prove reali, passate). Due esecuzioni sullo stesso sito danno
  screenshot identici byte per byte. **Resta:** la prova con Ctrl+C a meta' (R1.11) e l'uso di `ContainerLimiter`
  per i renderer.

#### R1.5 — Risultato strutturato al posto dell'exit code
- **Obiettivo:** oggi la verifica e' un comando con exit code 0/1 (`task_model.py:25`, `campaign.py:202-208`) e il
  report calcola `f` su un booleano (`campaign.py:392`). Serve un risultato con credito parziale e metriche.
- ✅ **Deciso il 22 ott:** la valutazione scrive un JSON (avvio riuscito, passi superati e totali, test delle
  rotte superati e totali, errori, sbordo per larghezza, violazioni axe per gravita', percorsi degli screenshot,
  versioni di immagine e browser), letto da Python; la riga del manifesto si estende; `f` resta calcolabile.
- **⚠️ Trappola:** «guasto dell'infrastruttura» e «sito che vale 0» sono due esiti diversi (regola in R6.2).
- **⚠️ Trappola (D48):** lo stesso renderer fara' anche da cancello del sistema (R2.6). Nel JSON i campi che il
  cancello puo' leggere (avvio, errori, sbordo, accessibilita') vanno tenuti separati da quelli riservati alla
  valutazione (passi dello script, test delle rotte): il cancello non deve mai ricevere i secondi.
- **Test:** il JSON di un sito d'esempio ha tutti i campi; un JSON malformato e' un guasto, non uno 0; i vecchi test
  di campagna restano verdi.

#### R1.6 — Controlli automatici (livello 1) ✅ (22 ott, da committare)
- **Obiettivo:** una definizione operativa, scritta prima delle misure, di ogni controllo di §6.
- ✅ **Decise il 22 ott (in `PROTOCOLLO.md` §6):**
  - Errori: eccezioni non gestite (`pageerror`) e `console.error`, al caricamento e durante lo script; le risorse
    mancanti come la favicon non contano.
  - Sbordo: `scrollWidth > clientWidth` del documento, tolleranza 1 px, dopo il caricamento e l'attesa dei font,
    a ciascuna larghezza.
  - Accessibilita': violazioni axe di impatto `critical` e `serious`. Scelto (a): `axe.min.js` (axe-core 4.14.0,
    MPL-2.0) nel repository con la sua licenza, iniettato con `add_script_tag`; (b) `axe-playwright-python` 0.1.8
    (MIT, un solo manutentore). Raccomandazione: (a).
- **Test:** pagine costruite apposta (un errore JavaScript; uno sbordo a 375 px; un'immagine senza `alt` e un
  contrasto insufficiente): ciascuna fa scattare solo il suo controllo.
- **Fatto (22 ott):** errori e sbordo in `docker/render_site.py`; axe-core 4.14.0 (`docker/axe.min.js`, sha512 del
  pacchetto npm verificato, licenza in `docker/axe-core.LICENSE`) eseguito a ogni larghezza, solo impatti `critical`
  e `serious`. Prove reali i2 e i5 passate.

#### R1.7 — Script d'interazione e test delle rotte ✅ (23 ott, da committare: interprete e 5 script approvati)
- **Obiettivo:** per ogni compito, una sequenza di passi scritta prima di generare qualunque sito per quel compito.
- **Gia' deciso:** «funziona» = quota di passi superati dello **script d'interazione**, 0 se la pagina non si apre
  (R0-9); per le applicazioni ci sono anche test diretti sul server (P12-D1).
- **Scelte aperte:**
  - ✅ (22 ott: (b)) **Dove vanno i test delle rotte.** (a) Dentro «funziona», a peso uguale con i passi d'interfaccia:
    il server conta nella prova principale, ma «funziona» misura cose diverse su siti (solo interfaccia) e su
    applicazioni (in buona parte server, compresa l'aderenza ai codici HTTP), ed e' un cambio di R0-9; (b) metrica
    secondaria «funziona-server», riportata per C contro B con il suo intervallo sulle sole applicazioni, senza
    dichiarazione di non inferiorita'. Raccomandazione: (b): tiene la metrica principale omogenea e lascia il server
    misurato e visibile. Se si sceglie (a), va scritto come revisione di R0-9.
  - ✅ (22 ott: (a)) **Passi dipendenti:** se un passo fallisce, quelli che ne dipendono contano come falliti (a) o si
    tolgono dal denominatore (b). Raccomandazione: (a), passi indipendenti quando possibile.
  - ✅ (22 ott: (a), dopo aver letto le bozze) **Formato:** (a) Python con Playwright, un file per compito; (b) formato dichiarativo (azione,
    marcatore, atteso) eseguito da un interprete unico. Raccomandazione: (b): si rilegge senza programmare e
    l'interprete si testa una volta.
- **Passi:** tradurre i casi di prova di WebGen-Bench (`ui_instruct`, 5-8 per compito) tenendo accanto a ogni passo
  il caso originale, cosi' chi rilegge vede se la traduzione e' fedele; per ArtifactsBench, che non ha casi di
  prova, partire dalle voci funzionali della checklist; per le applicazioni, i test del contratto (crea, leggi,
  modifica, cancella, input sbagliato rifiutato, dato presente dopo riavvio).
- **⚠️ Trappola:** uno script che passa su un sito vuoto e' sbagliato. Ogni script deve dare 0 su un sito vuoto; uno
  script per un sito e uno per un'applicazione si provano anche contro un riferimento scritto a mano (deve dare
  100), come in Polyglot scheletro e soluzione.
- **Fatto (22 ott):** libreria `valutazione/libreria.py` (passi, dipendenze, «non valutabile», punteggi),
  contesto con il browser `valutazione/browser.py`, esecuzione nel renderer `valutazione/contenitore.py` (sito
  ripristinato a ogni passo, `node_modules` e venv collegati), lato host `renderer.evaluate_site`. Test: 14 + 8
  unitari, 2 prove reali con una mini applicazione d'esempio (`tests/fixtures/valutazione/`): 100 sul sito giusto, 0
  sul sito vuoto con i passi preparati «non valutabili». Il rendering ora gira anch'esso in `/workspace`.
- **684 (23 ott):** materiali in `campaigns/r1_valutazione/684.md` e script `684.py` (13 passi + 8 rotte); sito di
  riferimento scritto a mano in `tests/fixtures/valutazione/rif_684/`: 100 e 100; sito vuoto: 0 e 0 (prova i8).
- **Altri 4 script (23 ott):** `000098`, `000040`, `000058`, `842` (`.md` + `.py` in `campaigns/r1_valutazione/`, siti di
  riferimento in `tests/fixtures/valutazione/rif_*`), scritti da 4 sottoagenti in parallelo e riverificati: la prova
  i8 da' 100 sul riferimento (funziona-server 100, `842` senza rotte) e 0 sul sito vuoto per tutti e 5 (6 min 52 s).
- **Vetrina (23 ott):** `render_site(..., script=...)` esegue `vetrina(c)` dello script prima degli screenshot; esito
  nel risultato (`ok`, `assente`, `errore: ...`); un errore non ferma il rendering. Test r13-r15 e prova reale i9.
- **Fatto quando:** 5 script approvati dall'autore, tutti «vuoto = 0», due «riferimento = 100».

#### R1.8 — Fonte delle coppie e strumento di voto
- **Il problema:** per misurare l'accordo giudice-umani servono circa 100-200 coppie di siti, e in R1 non esistono
  siti dei bracci.
- `[SCELTA]` **Fonte.** (a) Le risposte pubblicate da ArtifactsBench (`dataset/release_data_20250725/`: 20 modelli,
  stessi compiti, gia' giudicati da Gemini 2.5 Pro), scegliendo **coppie di qualita' vicina** (fra i modelli
  migliori), perche' l'accordo e' piu' alto fra siti molto diversi e misurarlo li' lo gonfierebbe proprio dove
  conta (C e B si somiglieranno); limite: pagine singole senza server; la licenza di quella cartella va verificata
  ed e' **bloccante**; (b) siti generati da B e D nel pilota di R2; (c) entrambe. Raccomandazione: (c): (a) per il
  grosso della calibrazione in R1, e una quota **obbligatoria** di coppie da R2 (almeno 20) per controllare che
  l'accordo regga sui siti con server.
- `[SCELTA]` **Compiti della calibrazione senza toccare i compiti di test.** I compiti di test si prenderanno
  proseguendo l'ordine estratto (§2): toglierne alcuni per la calibrazione cambierebbe l'insieme. Proposta: la
  calibrazione usa solo compiti oltre una posizione fissata ora nell'ordine di ArtifactsBench (es. dalla 300ª in
  poi, ben oltre quanto servira' ai test), scritta nel protocollo prima di usarla.
- **Strumento di voto:** pagina locale servita dal portatile; vede il testo del compito e gli stessi screenshot del
  giudice; voto da −2 a +2; ordine sinistra/destra casuale e registrato; nessun indizio del braccio; pausa ogni 20
  coppie; 5 coppie ripetute per misurare la coerenza del votante; voti salvati con identificativo anonimo, fuori dal
  repository pubblico.
- **⚠️ Trappola:** l'autore conosce lo stile di C: sulle coppie con C il suo voto non e' cieco. Si esclude dalle
  coppie con C o si dichiara.
- **Fatto quando:** coppie scelte e salvate; l'autore ha votato 10 coppie di prova e il file dei voti si legge.

#### R1.9 — Giudice a coppie («piace»)
- **Obiettivo:** dato un compito e due siti, un voto da −2 a +2 in entrambi gli ordini, piu' le risposte si'/no
  della checklist, con costo misurato.
- **Gia' deciso:** voto graduato, entrambi gli ordini, media dei due voti col segno dalla parte di C (D46); sei
  domande fisse + 2-4 per compito, fuori dalla metrica (R0-7); famiglia non in gara (D41).
- **Base nel codice:** `quality/estimators.py:176-249` (`FrontierJudge`: gateway, tetto, 402, costo per giudizio).
  Il gateway lascia passare i messaggi costruiti come dizionari (`llm_gateway.py:555-565`), quindi anche le
  immagini, ma **nessun test lo prova: non verificato**. Manca il ruolo `judge` (`models.toml:265`).
- **Scelte aperte:**
  - `[SCELTA]` **Cosa vede:** testo del compito e screenshot dei due siti alle tre larghezze (6 immagini). Non
    l'esito dello script: il funzionamento lo misura «funziona», e tenerli separati evita di contarlo due volte.
  - `[SCELTA]` **Checklist nella stessa chiamata del voto** (a, costa meta' e orienta il voto, scopo dichiarato in
    §6) o in chiamate separate (b). Raccomandazione: (a).
  - Risoluzione delle immagini fissata a 1120 token (valore predefinito di Gemini); formato d'uscita JSON; risposta
    malformata o rifiuto: un nuovo tentativo, poi «non valutabile», contato a parte e mai trasformato in pareggio;
    temperatura e sforzo di ragionamento fissati e scritti.
- **⚠️ Trappole:** bias di posizione, piu' forte quando i due siti si somigliano (Shi et al. 2406.07791); bias di
  quantita' (vince il sito con piu' contenuto), da controllare sulla calibrazione; nome del modello o del braccio
  mai visibili; lezione di M2b.5 (storica righe 1394-1429): il giudice e' costato 3 volte la stima, quindi
  **preventivo misurato su 15-20 chiamate** prima di ogni lotto; un 402 ferma l'esecuzione.
- **Costo (calcolato, da misurare):** per ordine circa 9k token d'ingresso (6 immagini da 1120 + testo) e 2-4k
  d'uscita compreso il ragionamento. Argon al prezzo scontato ≈ $0,04-0,06 per ordine, ≈ $0,08-0,12 per coppia;
  3.8 Flash ≈ $0,02 per ordine, ≈ $0,04 per coppia. Calibrazione di 120 coppie con entrambi i giudici ≈ $15-20.
- **Test (nessuna chiamata a pagamento):** con un gateway finto, l'inversione dell'ordine ribalta il segno; due
  voti opposti fanno pareggio; malformata → nuovo tentativo → «non valutabile»; costo sommato per coppia; un 402
  ferma il lotto; un messaggio con immagini arriva al client nel formato giusto.
- **Fatto quando:** il giudice gira su 5 coppie vere con costo misurato e prezzo di 3.8 Flash verificato.

#### R1.10 — Voti umani e scelta del giudice
- **Procedura (da M2b.1, storica righe 1225-1229):** prima l'accordo fra umani, poi giudice contro umani; il
  giudice si usa solo se si avvicina all'accordo fra umani.
- `[SCELTA]` **Quanti voti.** Con 50 coppie l'accordo percentuale ha un'incertezza di ±12 punti, con 100 di ±8, con
  200 di ±6 (intervallo di Wilson al 95%, accordo 75%: calcolo del 21 ott, non da letteratura). Ogni coppia va
  votata da almeno 2 persone per conoscere il tetto di accordo fra umani. Proposta: 120 coppie × 2 persone su 4-6
  (≈ 50-60 voti a testa, come previsto in D41).
- `[SCELTA]` **Metrica e soglia, scritte prima di vedere i voti.** Proposta: accordo sul segno (chi vince; pareggio
  a parte) con Scott's π, consigliato da Thakur et al. 2406.12624 perche' l'accordo percentuale distingue male i
  giudici, e Spearman sui voti graduati; il giudice e' accettato se il suo accordo con gli umani non e' inferiore di
  oltre X all'accordo fra umani. **Piano B** se nessuno dei due Gemini passa: «piace» diventa metrica secondaria e la
  prova si regge su «funziona».
- **Revisione delle domande fisse (rimandabile):** una domanda a cui il giudice risponde «si'» a oltre il 90% dei
  siti non distingue e si toglie. Si congelano prima di R6.
- **Fatto quando:** accordi calcolati con intervallo; giudice scelto o piano B attivato; scritto in `PROTOCOLLO.md`.

#### R1.11 — Manutenzione dell'infrastruttura (da «Da decidere a inizio M4», storica righe 999-1020)
- Pulizia dei container orfani `orc-sandbox-*` (e dei renderer) all'avvio di ogni campagna.
- Tempo massimo di attesa per un posto nella sandbox (oggi senza limite).
- Client `openai.OpenAI` chiuso a fine agente (oggi mai chiuso: pesa nelle campagne lunghe).
- Prove con Docker vero mai fatte: Ctrl+C durante `docker run`, tempo scaduto prima dell'avvio, container orfano.

**Definition of Done — R1**
- [x] 5 compiti di sviluppo estratti e riproducibili dal codice.
- [ ] Convenzioni, contratti, domande, marcatori e script scritti e approvati prima di ogni generazione.
- [ ] Un sito statico e uno con server d'esempio danno due volte lo stesso risultato; ogni script da' 0 sul sito
      vuoto; due script danno 100 sul riferimento.
- [ ] Giudice con costo misurato; accordi umani-umani e giudice-umani con intervallo; giudice scelto o piano B.
- [ ] Nessuna chiamata a pagamento nei test; suite e pyright verdi.
- [ ] Sezione di tesi «metodo di valutazione» abbozzata.

---

### R2 — Strumenti comuni, baseline e politiche semplici ⬜

**Obiettivo.** Dare a un agente singolo gli strumenti che avranno tutti i bracci, fissare le regole di parita',
costruire il cancello eseguibile (D48) e il braccio H (D49), far lavorare Opus 5.5 (B), DeepSeek V4.1 Flash (D) e H
sui compiti pilota, comporre V, sostituire il preventivo calcolato con uno misurato. **Prerequisiti:** R1.
**Sezione di tesi:** baseline, politiche semplici e costo del forte da solo.

**Ordine dei task.** R2.1 e R2.1b (strumenti) → R2.2 (correzioni) → R2.3 (parita') → **R2.6** (cancello) →
**R2.7** (H) → R2.4 (pilota) → R2.5 (τ_piace e preventivo). Il cancello viene prima di H e del pilota perche' serve
a comporre V gia' nel pilota.

**Stato del codice.** L'agente ha `bash`, `read_file`, `write_file` (`tools/__init__.py:47`); l'esito di uno
strumento torna come stringa JSON (`agent.py:386-390`), quindi oggi un agente non puo' ricevere immagini; prompt
di sistema generico (`agent.py:27-32`); 30 iterazioni (`config.py:124`); nessun `max_tokens` sul percorso
OpenRouter (`llm_gateway.py:398-409`); uscite di `bash` non troncate (`tools/bash.py:62-74`); `main.py` usa di
default il ruolo `worker` (GPT-6.1 Sol).

#### R2.1 — Strumento «guarda il sito»
- L'agente avvia il proprio sito e riceve screenshot ed errori dallo stesso renderer di R1.4, senza vedere gli
  script di valutazione.
- `[SCELTA]` (a) Lo strumento restituisce immagini (cambia il contratto di `Tool` e il messaggio di esito); (b)
  solo metriche testuali. Raccomandazione: (a): il critico visivo di C e' il cuore della sua verifica e per D39 B
  deve poter fare lo stesso.
- **⚠️ Trappola:** ogni chiamata aggiunge immagini alla storia, rimandata a ogni turno. Politica minima: le
  immagini vecchie si tolgono dalla storia e resta una riga di testo.

#### R2.1b — Strumento «genera immagine» (deciso il 22 ott: immagini generate via OpenRouter)
- **Obiettivo:** uno strumento identico per B, C, D e H che produce un'immagine nel workspace e ne registra il costo.
  Dettagli della ricerca del 22 ott in `docs/STUDIO.md` (escluso da git).
- **Fatti che condizionano il disegno:** su OpenRouter le immagini passano da `POST /api/v1/images`, non dalla
  chat; la risposta da' `usage.cost` ma **nessun id di generazione**, quindi la rilettura del costo di
  `generation_lookup.py` non si applica cosi' com'e' (da verificare con una chiamata); niente seed (immagini non
  riproducibili); latenza fino a 1-2 minuti; nessuna maschera via OpenRouter (modifica = prompt + fino a 16
  riferimenti); richieste bloccate dalla moderazione.
- `[SCELTA]` **Modello:** Sunburst (precisione) o Flare (veloce), stesso listino; oppure un'alternativa a prezzo
  fisso (Seedream 5.0 flash $0,018, Flux 3 klein $0,009). Si sceglie con una prova su 5-10 immagini, costo e tempo
  misurati, preventivo prima. Il prezzo per immagine della serie 2.5 non e' pubblicato.
- `[SCELTA]` **Parametri fissi** (qualita', dimensioni ammesse, formato) e **tetto di immagini per sito**: senza
  tetto un braccio puo' spendere in immagini piu' che in testo.
- **⚠️ Trappole:** timeout dello strumento sopra i 2 minuti; un blocco di moderazione e' un esito restituito
  all'agente, non un guasto; il costo delle immagini entra nel costo per pagina del braccio; le immagini non sono
  riproducibili, quindi si archiviano in `runs/` insieme al sito.
- **Test:** con un client finto, salvataggio del file dal base64, costo registrato, timeout, moderazione, tetto di
  immagini.
- **Candidati per R4:** immagine di riferimento di stile passata a tutte le generazioni dello stesso sito
  (coerenza); bozze a qualita' `low` poi una sola versione finale; icone e loghi in SVG con un modello vettoriale;
  modifica di un'immagine invece di rigenerarla.

#### R2.2 — Correzioni dell'harness comuni a tutti
- Troncamento delle uscite di `bash`; `max_tokens` esplicito su OpenRouter; prompt di sistema per i siti con le
  convenzioni di R1.2. Test con modelli finti.

#### R2.3 — Parita' fra bracci
- `[SCELTA]` **Ruoli.** B = `planner` (Opus 5.5); D = `worker_cheap` (DeepSeek V4.1 Flash, D47). Per i worker di
  C, D47 dice DeepSeek, mentre `models.toml:272-274` assegna `worker` a GPT-6.1 Sol (scelta mai confermata
  dall'autore): va deciso quale modello fanno i worker di C, e D usa lo stesso.
- `[SCELTA]` **Tetti per braccio.** Proposta: stesso tetto in dollari **per compito** per B, C, D e H (per C e' il
  tetto di squadra, R3.5; per H vale per tutta la run, prima e dopo il passaggio); tetto di iterazioni per agente
  misurato nel pilota (30 bastano per un sito statico, probabilmente non per un'applicazione) e uguale per tutti gli
  agenti; tempo massimo per compito uguale. V non ha un tetto proprio: eredita quelli di D e di B.
- `[SCELTA]` **Ragionamento e temperatura** fissati per ogni modello e scritti nel protocollo.
- `[SCELTA]` **Ciclo di verifica di B.** C avra' critico ed escalation (R3.4). (a) B riceve gli stessi strumenti di
  verifica (guarda il sito, propri test del contratto) e un passo di autocritica con lo stesso prompt del critico,
  eseguito da Opus stesso; (b) solo gli strumenti, e la differenza si dichiara come parte di cio' che C aggiunge.
  Raccomandazione: (a): e' la lettura letterale di D39 e toglie l'obiezione piu' facile.

#### R2.4 — Pilota
- **Compiti:** `[SCELTA]` 3 dei 5 di sviluppo, almeno un sito e un'applicazione con server; proposta `000040`
  (sito), `000098` e `842` (app).
- **Bracci (D50):** B, D e H, una esecuzione ciascuno; V composta da B e D con il cancello di R2.6 (nessuna
  esecuzione in piu'); una seconda esecuzione di B se R2.5 sceglie (b). Per H e V nel pilota niente giudice: si
  misurano «funziona» e costo.
- **Regole di spesa:** preventivo spiegato prima; `--budget-usd` per run e `--max-total-usd` per il lotto; DeepSeek
  fuori dalle fasce a prezzo doppio (giorni feriali 01-04 e 06-10 UTC, `PROTOCOLLO.md` §4), con il confronto fra
  costo calcolato e riportato nel report a segnalare gli errori d'orario.
- **⚠️ Trappola:** verificare che Opus via OpenRouter legga davvero dalla cache (`cached_tokens` > 0 dal secondo
  turno): senza, B costa di piu' per una scelta d'infrastruttura.
- **Misure:** token per tipo (input, cache letta e scritta, output, ragionamento), costo calcolato e riportato,
  iterazioni, durata, «funziona», motivo di arresto. Le coppie B-D entrano nella quota di calibrazione di R1.8.
- **Misure delle politiche semplici (D50):** verdetto del cancello sul sito di D e sul sito di B (un cancello che
  rifiuta B segnala un cancello troppo severo); `a` sui 3 compiti; costo e «funziona» di V; per H il turno del
  passaggio, la quota di spesa di Opus (`q_H`) e «funziona». Con 3 compiti sono indicazioni, non stime: servono a
  capire se V e H vanno curati come rivali seri (`TESI_master.md` §0.2) e a fare il preventivo di R6.

#### R2.5 — τ_piace e preventivo misurato
- **Il problema:** R0-6 dice «τ_piace dopo il pilota, quando si conosce la variabilita' dei voti», ma nel pilota
  non c'e' C, e un margine di non inferiorita' dovrebbe dire quale differenza conta, non quanto rumore c'e' (il
  rumore pesa sulla potenza, non sul margine). In R0 «τ dal rumore» era gia' stato giudicato eccessivo.
  `[SCELTA]` (a) τ_piace fissato a priori con una motivazione sulla scala (es. 0,5 = «in media meta' strada fra
  pari e leggermente meglio»), dopo aver visto nel pilota come il giudice usa la scala; (b) stimato dalla
  variabilita' di due esecuzioni di B sullo stesso compito. Raccomandazione: (a); la variabilita' misurata serve
  invece al calcolo della potenza di R6.1.
- **Preventivo della campagna:** generazione (B, C, D, H; V non costa) + giudice (coppie C-B, D-B, H-B e ablazioni,
  entrambi gli ordini, listino di dicembre; V riusa D-B) + voti umani sul campione. La voce da controllare e' il giudizio, non la generazione
  (storica righe 1554-1566).

#### R2.6 — Cancello eseguibile (D48)
- **Obiettivo:** una funzione deterministica e gratuita che, dato il workspace consegnato, dice «accettato» o
  «rifiutato» con il motivo, usando solo cio' che l'agente stesso puo' vedere. Serve a V (sito di D tenuto o no) e a
  C (prima del critico e come innesco dell'escalation, R3.4): una sola implementazione per entrambi.
- **Gia' deciso:** nessuna chiamata a un modello; mai script d'interazione, test delle rotte, domande del giudice o
  siti di riferimento (regola permanente «Valutazione invisibile ai bracci»); verdetto e motivo registrati nel
  manifesto della run.
- `[SCELTA]` **Cosa controlla.** (a) Il sito si avvia con `start.sh` entro 60 s e nessun errore JavaScript al
  caricamento; (b) (a) piu' i test scritti dall'agente, eseguiti con un comando convenzionale (es. `test.sh`) chiesto
  nel prompt a **tutti** i bracci, che devono passare; (c) (b) piu' sbordo e accessibilita' gravi. Raccomandazione:
  (b): l'avvio da solo accetta troppo, mentre i test propri sono gia' previsti per C (R3.3) e sono la verifica che un
  router testuale non puo' fare. Sbordo e accessibilita' restano metriche riportate, non motivi di rifiuto.
- `[SCELTA]` **Test propri mancanti.** Un workspace senza `test.sh`: (a) rifiutato; (b) giudicato solo su avvio ed
  errori. Raccomandazione: (b) per i siti di contenuto, (a) per i compiti con contratto, scritto nel prompt.
- **⚠️ Trappole:** un `test.sh` vuoto o che stampa «ok» passa sempre: il cancello conta i test eseguiti e rifiuta
  zero test sui compiti con contratto; i test dell'agente girano nel renderer senza rete come la valutazione; il
  cancello non e' «funziona»: un sito accettato puo' valere poco su «funziona» e su «piace» (lo si misura).
- **Test (nessuna chiamata a pagamento):** sito che non parte → rifiutato con motivo; errore JavaScript → rifiutato;
  `test.sh` che fallisce → rifiutato; `test.sh` vuoto su un compito con contratto → rifiutato; il cancello non legge
  mai i file di `valutazione/` ne' i campi riservati del JSON di R1.5 (test dedicato).
- **Costo:** zero (Docker locale).

#### R2.7 — Braccio H: Plan/Execute (D49)
- **Obiettivo:** un agente singolo con gli stessi strumenti di B e D che usa Opus 5.5 fino alla prima scrittura di
  un file, poi DeepSeek V4.1 Flash con tutta la storia, fino alla fine.
- **Riferimento:** politica Plan/Execute di Switchyard (`crates/libsy/src/algorithms/plan_execute.rs:87-119` al
  commit `7558a1d`): si reimplementa l'idea nel nostro harness, senza dipendenze nuove, e in tesi la si chiama
  «adattamento», non riproduzione.
- `[SCELTA]` **Dove vive il cambio di modello.** (a) Un gateway che delega a due gateway, quello di Opus e quello di
  DeepSeek, e passa al secondo quando una risposta contiene una chiamata a `write_file`: l'agente (`agent.py:129`
  riceve un solo `ChatGateway`) non cambia, e ogni gateway registra nel ledger il proprio modello
  (`llm_gateway.py:196-197`), quindi il costo resta attribuito giusto; (b) l'agente riceve due gateway e decide lui.
  Raccomandazione: (a).
- `[SCELTA]` **Cosa conta come prima scrittura.** (a) La prima chiamata a `write_file`, anche se fallisce (come
  Switchyard); (b) anche un comando `bash` che scrive file (`>`, `npm init`, ...): piu' fedele, ma un riconoscimento
  testuale fragile. Raccomandazione: (a), dichiarando che un agente che scrive solo via `bash` non passa mai.
- `[SCELTA]` **Istruzione di pianificare.** (a) Al prompt di H si aggiunge una frase: «prima di scrivere file,
  esplora e scrivi il piano» (Switchyard fa lo stesso); (b) nessuna frase, prompt identico a B. Raccomandazione:
  (a), perche' senza la frase il passaggio arriva al primo turno e H diventa D; la frase si dichiara.
- **⚠️ Trappole:** i blocchi di ragionamento di Opus non si passano a DeepSeek (formati diversi): si tolgono al
  passaggio e lo si dichiara; al passaggio DeepSeek legge tutta la storia senza cache, una volta (costo piccolo, ma
  misurato); gli identificativi delle chiamate agli strumenti devono restare coerenti; il tetto di spesa e' unico
  per tutta la run.
- **Test (modelli finti):** passaggio esattamente dopo la prima `write_file` e mai prima; storia completa al secondo
  modello senza blocchi di ragionamento; nel ledger le chiamate risultano dei due modelli giusti; tetto unico; una run
  senza scritture resta tutta su Opus.
- **Costo:** solo nel pilota e in R6, una esecuzione per compito.

**Definition of Done — R2**
- [ ] Strumenti comuni e regole di parita' scritti, testati con modelli finti, identici per B, C, D e H.
- [ ] Cancello eseguibile (R2.6) e braccio H (R2.7) scritti e testati con modelli finti; il cancello non legge mai
      la valutazione (test dedicato).
- [ ] Pilota su 3 compiti con costo misurato, cache di Opus verificata, motivi di arresto analizzati; `a`, costo
      di V, quota di Opus in H riportati; sezione di tesi §0.2 confrontata con i primi dati.
- [ ] τ_piace in `PROTOCOLLO.md` con la motivazione, prima di qualunque confronto C contro B.
- [ ] Deviazione standard di «funziona» stimata e potenza di R6 ricalcolata; preventivo di R3, R4 e R6.

---

### R3 — OrcV2 minimo: sciame per sezioni ⬜

**Obiettivo.** Il braccio C su tutti i compiti di sviluppo: un planner forte divide il lavoro, worker economici lo
eseguono in parallelo, il cancello e un critico controllano, un integratore ricompone, il forte interviene solo
quando il controllo lo chiede. **Prerequisiti:** R2. **Sezione di tesi:** architettura del sistema.

**Cosa deve battere (D49, `TESI_master.md` §0.2).** Non solo B: sul costo C deve tenere la quota di Opus `q` sotto
la quota di compiti in cui D da solo non passa il cancello (`1 − a`, dal pilota); sulla qualita' deve fare meglio di
V proprio dove V tiene il sito di D. Ogni scelta di R3 (piano, critico, escalation) si legge anche cosi'.

**A cosa serve lo sciame (storica righe 978-997, ancora valido).** A rendere possibile il modello economico: la
scomposizione abbassa la difficolta' di ogni pezzo fino a dove il modello economico ce la fa. **Il costo e' una U
nel numero di pezzi K**: pochi pezzi = pezzi troppo difficili ed escalation; troppi = coordinamento. I sotto-agenti
dei prodotti commerciali costano 1,5-2,9 volte l'agente singolo a parita' di accuratezza (DeLM v3, 2606.10662,
Tab. 2). «Decomponi il piu' possibile» e' sbagliato quanto «non decomporre».

#### R3.1 — Il piano
- Il planner (Opus) produce un piano JSON validato: sistema di stile (variabili CSS e regole), pezzi con file,
  dipendenze e cosa vede ogni worker.
- `[SCELTA]` **Cos'e' un pezzo in un'applicazione** (con il server, «un file per sezione» non basta). (a) Scheletro
  comune per primo (`package.json`, server con le rotte vuote del contratto, layout, stile), poi in parallelo una
  sezione d'interfaccia per file e un modulo di server per risorsa del contratto; (b) due pezzi, interfaccia e
  server; (c) un pezzo per funzione, da cima a fondo. Raccomandazione: (a): il contratto e' il confine naturale.
- **Validazione (M4.1, storica righe 1031-1047):** grafo senza cicli, file che non si sovrappongono, ogni rotta del
  contratto assegnata; piano invalido → al massimo 2 rigenerazioni, poi errore registrato.
- **Test:** piani finti validi e invalidi (ciclo, file condiviso, rotta mancante).

#### R3.2 — Esecuzione in ondate
- Ondate dal grafo; un pezzo fallito blocca solo chi ne dipende. Workspace comune alla squadra (oggi ogni agente ha
  il suo, `agent_factory.py:414`): la fabbrica deve accettare un workspace imposto.
- **Contesto isolato (M4.3, storica righe 1106-1126):** il worker riceve stile, contratto, la descrizione del suo
  pezzo e le interfacce dei vicini, non la storia del planner.
- **⚠️ Trappola (M4.2b, storica righe 1054-1087):** la cache dura circa 5 minuti; un worker fermo in attesa la
  perde e riscrive la storia a 1,25 volte il prezzo. L'inattivita' e' una voce di costo.

#### R3.3 — Integrazione
- Siti statici: integratore deterministico (modello di pagina che include le sezioni). Applicazioni: build e avvio
  con `start.sh`, poi i controlli che C puo' vedere: i propri test del contratto (il contratto e' nel prompt, quindi
  ogni braccio puo' scriverseli) e lo strumento «guarda il sito». Mai gli script di valutazione.

#### R3.4 — Critico ed escalation
- Critico per pezzo (modello economico con visione) che guarda il pezzo dentro la pagina; al massimo 2 giri; si
  tiene la versione migliore secondo il critico. Prima il **cancello eseguibile di R2.6** (M2b.0, storica righe
  1196-1205; D48), lo stesso usato da V: se il cancello rifiuta, il critico non si chiama.
- `[SCELTA]` **Criteri del critico:** propri e generici (stile rispettato, niente di tagliato, testo leggibile),
  uguali per tutti i compiti, mai le domande del giudice (si insegnerebbe per il test). Lo stesso prompt serve
  all'autocritica di B (R2.3).
- `[SCELTA]` **Escalation (M2b.2, storica righe 1237-1245):** innesco, granularita' (pezzo), contesto passato a
  Opus, tetto di escalation per compito. Per l'innesco: (a) il cancello o il critico rifiutano ancora dopo 2 giri;
  (b) due rifiuti consecutivi con **evidenza nuova sullo stesso tipo di errore** (default della politica Escalation
  di Switchyard, `docs/routing_algorithms/escalation_router_routing.md`): evita di salire per un errore isolato
  gia' visto. Raccomandazione: (a), con il criterio «evidenza nuova» di (b) per non contare due volte lo stesso
  rifiuto. Il costo comprende la riscrittura della cache sul modello nuovo: nella documentazione di Switchyard ci sono
  casi in cui il cambio di modello ha fatto **salire** il costo.

#### R3.5 — Tetto di squadra
- Guardiano sopra `TeamAccountant` (`accounting/team.py:45`, oggi usato solo nei test), iniettato al posto del
  `BudgetGuard` per agente (`agent_factory.py:313`); innesco sulla **proiezione** della spesa (pezzi fatti / pezzi
  del piano), non sulla spesa gia' fatta (M4.2c, storica righe 1088-1105).
- `[SCELTA]` **Cosa fa al tetto** (problema B4, storica riga 179; B5, nessuna risposta = fermarsi e riportare, e'
  gia' deciso): (a) consegna il lavoro fatto; (b) modelli piu' economici per i pezzi rimasti; (c) ferma tutto.
  Raccomandazione: (a); si sceglie insieme alla regola dei guasti di R6.2, che vale per tutti i bracci.

#### R3.6 — Cosa registrare
- Per ogni chiamata ruolo e pezzo, per calcolare m e q della condizione D37.
- **Lavoro scartato** come voce separata: giri del critico non tenuti, escalation che rifanno un pezzo, tentativi
  ripetuti. E' la parte di `q` che non produce il sito e spiega dove la previsione di D37 viene smentita.
- Verdetto del cancello (accettato/rifiutato e motivo) per ogni pezzo e per il sito finale, per confrontarlo con V.

**Definition of Done — R3**
- [ ] C completa i 5 compiti di sviluppo con «funziona» misurato e costo per ruolo.
- [ ] Piano, ondate, integrazione, cancello, critico, escalation e tetto coperti da test con modelli finti.
- [ ] Sui 5 compiti di sviluppo C confrontato con V e H (costo e «funziona»), come prima lettura di §0.2.
- [ ] Nessun braccio vede script o domande di valutazione (test dedicato).
- [ ] Sezione di tesi «architettura» abbozzata.

---

### R4.0 — Studio delle ottimizzazioni ⬜
- Sessione senza codice: skill (es. `frontend-design`), server MCP (es. Playwright), harness aperti (SWE-agent,
  OpenHands, mini-swe-agent, Aider, Codex CLI) con licenza, prove pubblicate e costo. L'autore sceglie cosa provare.
- `[SCELTA]` Le skill scritte per un formato preciso si danno uguali ai modelli di altre case? Per D42 ogni
  strumento va a B, C, D e H allo stesso modo.
- **Letteratura da controllare (D48):** generazione web con verifica a ciclo chiuso (WebGen-Agent e simili), per
  stabilire se il cancello eseguibile come criterio per passare al forte e' gia' pubblicato, prima di rivendicarlo
  in tesi (`TESI_master.md` §7.3, rischio 16).
- Da M7.1b (storica righe 1571-1583, AgentCARD): «planner forte + esecutore economico» vince con una coppia di
  modelli e perde con un'altra della stessa forma; un revisore economico sopra un planner forte non rende.

### R4 — Ottimizzazione manuale ⬜
- Una ottimizzazione alla volta, sui compiti di sviluppo, data anche a B e D (D42).
- `[SCELTA]` **Parita' nella messa a punto.** Ogni modifica di prompt o di harness si prova anche su B (a), oppure il
  vantaggio di messa a punto di C si dichiara come limite (b). Raccomandazione: (a) per le modifiche comuni; quelle
  che esistono solo nello sciame (piano, critico) non hanno un equivalente in B.
- `[SCELTA]` **Regola di accettazione.** 5 compiti con una esecuzione non distinguono un effetto dal rumore. (a) 3
  esecuzioni per compito solo in R4; (b) si accetta solo un cambio che riduce il costo senza abbassare «funziona» su
  nessun compito; (c) entrambe. Raccomandazione: (c), dichiarando il rischio di adattarsi ai compiti di sviluppo.
- Candidati: prompt stabili per la cache; compattazione del contesto; arresti che consegnano il lavoro fatto;
  strumento di piano per i modelli economici; Opus come consigliere; HTML + Tailwind compilato nel workspace; skill
  di design; best-of-N (M4.7, storica righe 1165-1174).
- **Opus come consigliere (Advisor di Switchyard):** il forte legge la trascrizione del worker a un punto di
  controllo e propone una correzione, invece di rifare il pezzo. Su DeepSWE v1.1: Advisor 57,5% a $208, Plan/Execute
  60,8% a $180,51 (esecuzioni diverse, non confrontabili alla lettera). Il profilo misurato usa 3 revisioni, 32.768
  token per il consigliere e nessun ripiego in caso di errore: i valori predefiniti della libreria (1 revisione,
  2.048 token) non riproducono quel risultato.
- **⚠️ Trappola sulla compattazione:** la modalita' «safe» di NadirClaw taglia la storia oltre 40 turni e comprime
  gli spazi anche dentro le stringhe del codice (`"A  B"` diventa `"A B"`): un compressore che cambia il codice non
  e' senza perdita. Si misura spento/acceso a modello fisso, con costo, cache e qualita' del sito finale; prima si
  guarda quali messaggi pesano sulla spesa.
- Revisione di checklist e domande con i dati di sviluppo; versione finale congelata prima di R6.
- **Costo:** preventivo misurato prima di ogni lotto.

### R5 — Ottimizzazione automatica (facoltativa) ⬜
- GEPA e adattamento dell'harness per modello sui compiti di sviluppo. `[SCELTA]` metrica da ottimizzare:
  «funziona» e costo, con il giudice solo come controllo finale (ottimizzare sul giudice insegna a ingannarlo).

---

### R6 — Campagna finale ⬜

**Obiettivo.** La prova della tesi: C contro B sui compiti di test, con la scala di politiche D, V, H (D49) e le
ablazioni come contorno.
**Prerequisiti:** R1-R4 chiusi, protocollo completo.

#### R6.1 — Prima di congelare
- `[SCELTA]` **Numero di compiti e potenza** (vedi «Le tre questioni»). Opzioni: (a) circa 50 compiti di test
  (costo di generazione e giudice circa 2,5 volte quello con 20); (b) τ_funziona piu' largo: con τ = 15 bastano
  circa 22 compiti per l'80% (stesse ipotesi), ma il margine va motivato come differenza irrilevante; (c) 20 compiti
  e risultato presentato come stima con intervallo, dichiarando in anticipo la bassa potenza; (d) misurare in R2-R4
  la deviazione standard vera e ricalcolare: se e' molto sotto 25, 20-25 compiti possono bastare. Raccomandazione:
  (d) subito, poi una fra (a) e (b) prima del congelamento. Le cifre usano σ = 25 ipotizzato, non misurato.
- `[SCELTA]` **Quote sito/applicazione** dei compiti di test, con la regola di R1.2.
- Scrittura di prompt, contratti, domande e script dei compiti di test, senza aver mai generato siti su di loro.
- Commit pubblicato del protocollo (R0-1): da quel momento ogni modifica va dichiarata e la campagna rifatta.

#### R6.2 — Esecuzione
- Bracci B, C, D, H, una esecuzione per compito (D45, D49); V composta da B e D con il cancello congelato; lo stesso
  compito su tutti i bracci nello stesso giorno, contro la deriva dei fornitori; DeepSeek fuori dalle fasce a prezzo
  doppio.
- `[SCELTA]` **Guasti.** Proposta coerente con R1.5 e con «un 402 ferma l'esecuzione»: un guasto
  dell'infrastruttura (fornitore, 402, sandbox, renderer) non e' un risultato del braccio: la run si ripete fino a 2
  volte e, se fallisce ancora, il compito esce dal confronto per tutti i bracci e si riporta. Un braccio che finisce
  regolarmente (anche per tetto) ma consegna un sito che non parte vale 0 in «funziona» e perde il confronto
  «piace» (−2 dalla sua parte). Se nessuno dei due consegna, «piace» = 0 e «funziona» = 0 per entrambi.

#### R6.3 — Giudizio e analisi
- Giudice congelato su tutte le coppie C-B, D-B, H-B e delle ablazioni, entrambi gli ordini; V non richiede
  coppie nuove (`PROTOCOLLO.md` §10). I «non valutabile» si
  riportano per braccio e si escludono dal bootstrap, con un'analisi di sensibilita' che li conta come pareggi.
- Analisi di `PROTOCOLLO.md` §10, con `cluster_bootstrap_ci` (`quality/metrics.py:130`) come base; voti umani anche
  su un campione della campagna (M7.5, storica righe 1620-1621).
- Rimandabili (si decidono dopo R4): costo per pagina accettata (CPT-τ, storica righe 1599-1619, introduce una
  terza soglia), riduzione del costo del giudice con endpoint a prezzo ridotto (`models.toml:209-210` ha escluso gli
  endpoint `flex`: va verificato cosa offre OpenRouter).

#### R6.4 — Ablazioni e curve
- `[SCELTA]` quali leve togliere una alla volta (critico, escalation, strumenti di R4, numero di pezzi K) e se anche
  su B; ognuna moltiplica il costo del giudice.
- Curva costo-qualita' e risultato in funzione del rapporto di prezzo r (D37), ricalcolando sulle quantita' grezze
  del ledger con listini ipotetici, valori di r scelti prima.
- **Scala di politiche (D49):** B, D, V, H, C sullo stesso piano costo-«funziona» e costo-«piace», con `a`, `q`,
  `q_H` misurati e la verifica delle condizioni di `TESI_master.md` §0.2.
- **⚠️ Trappola (replay):** ricalcolare il costo di una traccia con un altro listino e' lecito; dire da una traccia
  di Opus che «l'economico ce l'avrebbe fatta» no, perche' un altro modello avrebbe fatto altre scelte. Ogni
  politica si esegue davvero; V e' l'eccezione solo perche' B parte da zero e non dipende da D.

**Definition of Done — R6**
- [ ] Protocollo congelato con commit pubblicato prima della prima run.
- [ ] Tutte le run, i guasti e le coppie giudicate, con costo misurato.
- [ ] Risultato principale (non inferiorita' su entrambe le metriche, costo C/B) con intervalli; D, V, H e
      ablazioni riportati sul piano costo-qualita' senza dichiarazioni di significativita'.
- [ ] Capitolo dei risultati abbozzato.

### R7 — Router grossolano ❌ tolta il 23 ott 2026 (D48)
- Un router che **prevede** il modello o la strategia sufficiente prima di vedere il risultato non entra nel piano:
  sul codice la previsione separa male i casi, con 5 compiti di sviluppo non c'e' niente da imparare, e i router con
  pesi pronti (RouteLLM, Arch-Router, RouteFM) andrebbero comunque riprovati sul dominio. Il suo posto lo prende la
  verifica eseguibile (R2.6, R3.4) e la scala di politiche (R6).
- **Lavoro futuro (capitolo finale della tesi):** router per tipo di pagina addestrato sui dati di R6; trasferimento
  di router preaddestrati alla rosa del 2026; controllo «stessa quota di chiamate al forte, scelte a caso» per
  capire se un router sceglie *quali* turni, oltre a quanti; esiti per sotto-compito invece che per sito.

---

## Dove finiscono le voci precedenti

M4.1 planner → R3.1. M4.2 orchestratore → R3.2. M4.2b vita degli agenti → R3.2 (cache) e R4 (compattazione).
M4.2c tetto globale → R3.5. M4.3 stato condiviso → R3.2. M4.4 gate → R3.4. M4.6 immagini → R1.2. M4.7 best-of-N →
R4. M4.8 ottimo di scomposizione → R6.4 (K). «Da decidere a inizio M4» → R1.11. M2b.0 gate → R3.4. M2b.1 giudice
→ R1.9-R1.10. M2b.2 cascata → R3.4. M2b.3 registrazione delle scelte → R3.6. M2b.4 router → lavoro futuro (D48). M2b.5 e `quality/`
→ R1.9 (schema di `FrontierJudge`) e R6.3 (`cluster_bootstrap_ci`). M7 → R6. B1-B6 controllo del costo → R3.5 e R4.

## Problemi aperti ancora validi

| Problema | Dove si risolve |
|---|---|
| Potenza della prova con pochi compiti di test | R2 (deviazione misurata), R6.1 |
| Equita' fra bracci: tetti, ragionamento, ciclo di verifica di B, messa a punto | R2.3, R4 |
| Il giudice sa giudicare l'aspetto di un sito? | R1.8-R1.10 (soglia e piano B scritti prima) |
| Cio' che uno screenshot non mostra: interazione, server | R1.7 («funziona» e «funziona-server») |
| Soluzioni pubbliche raggiungibili dalla rete della generazione | R1.2 (controllo a posteriori) |
| Ambiente di valutazione uguale a quello di generazione | R1.4 (renderer costruito sulla sandbox) |
| Cos'e' un pezzo in un'applicazione con server | R3.1 |
| Tetto di spesa che consegna il lavoro invece di troncarlo (B1-B6) | R3.5, R4 |
| Prezzi che cambiano (Argon dal 1 dic, 3.8 Flash dal 1 gen, DeepSeek a fasce) | preventivi di R2 e R6; risultato in funzione di r |
| Varianza fra esecuzioni dello stesso modello | D45 (piu' compiti, non ripetizioni); R2 |
| Una politica semplice (V o H) raggiunge C | R2.4 (prima lettura), R3 (confronto sui compiti di sviluppo), R6 |
| Il cancello accetta siti che funzionano ma non piacciono | R2.6 (cosa controlla), R6.3 (coppie D-B dei compiti accettati) |
| Il cancello eseguibile e' gia' pubblicato? | R4.0 (letteratura), prima del capitolo sullo stato dell'arte |

## Regole operative permanenti

- **Ogni feature nasce col suo test.** Se non si sa come testarla, il design va rivisto prima di scriverla.
- **I test non possono spendere.** Nessuna chiamata a pagamento nei test; le prove reali (Docker, rete, file veri)
  girano solo con `ORC_INTEGRATION=1`.
- **CI sempre verde.** Push solo con `pytest` e `pyright` verdi in locale.
- **Il log e' sacro.** Ogni esecuzione produce un log strutturato in `runs/`: non si cancella. Un errore di
  configurazione non deve lasciare cartelle orfane (prima si valida, poi si crea).
- **Ogni esecuzione con un tetto di spesa** e un preventivo spiegato prima. Il preventivo di una campagna si misura
  su 15-20 chiamate vere; costo calcolato e misurato si distinguono sempre.
- **Un 402 (credito finito) ferma l'esecuzione** ed e' un guasto, non un fallimento del modello.
- **Fornitore fissato** per ogni modello in `models.toml`.
- **Dollari, non token.** In tesi si riportano dollari; i token solo come dato ausiliario.
- **Valutazione invisibile ai bracci e al cancello.** Script, domande e siti di riferimento non entrano mai nel
  workspace, nel prompt ne' nel cancello eseguibile di R2.6 (D48).
- **Una regola di giudizio cambiata dopo averla applicata** si scrive come revisione, con data e motivo, e vale anche
  per i compiti non ancora letti.
- **Scrittura incrementale della tesi.** Ogni fase chiusa = sezione di tesi abbozzata subito.
