# Protocollo sperimentale (R0)

> **Cos'e'.** Le regole dell'esperimento, scritte prima delle misure. Si completano una voce alla
> volta durante R0-R1; prima della campagna finale (R6) il file si fissa con un commit pubblicato e
> da quel momento non cambia. Una modifica dopo quel commit va dichiarata e la campagna rifatta.
>
> Legenda: ✅ deciso · 🔲 da decidere. Le sigle D35-D55 rimandano al registro in `PIANO_completo.md`.

## 0. Revisione del 29 ottobre 2026: piano MVP (D55)

Scritta prima di qualunque esecuzione di B, C o D sui compiti. Dove contraddice le sezioni seguenti, vale questa.

- **§1 Ipotesi.** L'ipotesi resta la stessa, ma la campagna non ha la potenza per dimostrarla: il risultato si
  presenta come **stima con intervallo** sui 5 compiti di sviluppo, e la bassa potenza si dichiara qui, prima delle
  misure. La domanda secondaria si limita a D e V; H si aggiunge solo se c'e' tempo.
- **§2 Compiti.** Niente compiti di test separati: la campagna usa i 5 compiti di sviluppo, gli stessi su cui il
  sistema e' costruito. Rischio di adattamento dichiarato.
- **§3 Bracci.** B, C, D, una esecuzione ciascuno; V composta da B e D; H facoltativo. C e' lo sciame minimo:
  piano di Opus, worker in parallelo, cancello, una sola correzione di Opus se il cancello rifiuta il sito finale,
  nessun critico. B ha gli stessi strumenti e lo stesso cancello visibile, senza passo di autocritica.
- **Cancello (D48).** Accetta se il sito si avvia con `start.sh` entro 60 s, la pagina `/` risponde con stato
  HTTP < 400 e non da' errori JavaScript al caricamento; altrimenti rifiuta con il motivo. Lo stato HTTP e' stato
  aggiunto il 2 nov 2026 (R2.6), prima di qualunque run: senza, un server che risponde 404 su `/` passava.
- **Parita' (R2.3, 2 nov 2026).** ✅ Regole scritte prima di qualunque run di B, C o D:
  - *Modelli.* B e il piano e la correzione di C: Opus 5.5. Worker di C e braccio D: DeepSeek V4.1 Flash `-1017`
    (D47, confermato contro Kimi K3.1 Pro: sui siti Kimi e' avanti di circa 15 Elo nella classifica Website di
    Design Arena, cioe' circa il 52% di preferenze, a un prezzo 13-17 volte maggiore; la tesi misura il costo a
    qualita' pari e con 5 compiti si legge solo una differenza di costo grande).
    **Modifica del 2 nov 2026 (R3), prima di qualunque run:** il worker di ogni pezzo di C lo sceglie il planner
    nel piano, fra DeepSeek V4.1 Flash (ruolo `worker_cheap`) e Kimi K3.1 Pro (ruolo `worker`). Il planner vede i
    prezzi del listino e il dato di Design Arena qui sopra, con la regola di usare il worker caro solo dove la
    difficolta' del pezzo lo giustifica. C diventa cosi' uno sciame con instradamento dei costi deciso dal planner,
    senza addestramento. Il braccio D resta DeepSeek V4.1 Flash da solo (`--arm D`). Il registro dello sciame
    riporta il modello di ogni pezzo: la quota di spesa di Kimi si dichiara nell'analisi, perche' rende meno
    netto il confronto C contro V (il vantaggio di C puo' venire dalla scomposizione o dal worker piu' forte).
  - *Strumenti.* Gli stessi per ogni agente di ogni braccio (`tools/__init__.py`, `build_default_tools`).
    Dal 4 nov 2026, prima della campagna, ogni agente ha anche `load_skill` (sei skill fissate a un commit
    in `docker/skills.toml`) e i programmi preinstallati Playwright (Python, Chromium in `/usr/bin/chromium`),
    Lighthouse, Biome, HTMLHint, vnu (Nu HTML checker), Hurl e Vitest. I limiti della sandbox sono 2 GB di
    memoria, 1024 processi e 300 s per comando, uguali per tutti i bracci.
    *Skill obbligatorie (7 nov 2026, prima della campagna).* Le skill non sono piu' solo offerte: ogni agente
    ha un elenco che il prompt di sistema nomina e che l'harness impone, rifiutando ogni altro strumento e la
    risposta finale finche' l'elenco non e' caricato (`tools/load_skill.py`, `agent.py`). Le skill di design
    (frontend-design, design-taste-frontend) vanno a chi decide lo stile, quelle di lavoro (frontend-design,
    webapp-testing, verification-before-completion) a chi scrive il codice: B e D ricevono l'unione, in C il
    planner le prime e worker e correzione le seconde. Le altre due restano facoltative. Si garantisce che le
    istruzioni siano lette, non che gli script delle skill siano eseguiti.
  - *Tecnologia (4 nov 2026, prima della campagna).* L'interfaccia si costruisce in React con Vite per tutti i
    bracci: la cornice di R1.2 lo chiede, la tecnologia del server resta libera. Prima la tecnologia era libera e
    i siti della prova sono usciti in HTML e JavaScript semplici; la regola comune toglie una fonte di varianza
    fra bracci e permette componenti condivisi (shadcn/ui). La build si fa durante la generazione, `start.sh`
    avvia soltanto.
  - *Rete.* Durante la generazione `bridge` con il firewall del progetto per tutti i bracci, come in §5: la
    cornice di R1.2 chiede di installare le dipendenze nella run. La valutazione resta senza rete. I default del
    codice sono `none`: il programma della campagna passa `bridge` in modo esplicito, con un test che lo controlla.
  - *Uscita per turno.* `max_tokens` = 32.000 per ogni modello (`config.MAX_TOKENS_TURNO`, R2.2).
  - *Ragionamento.* Fissato nella richiesta a `reasoning.effort = "high"` per Opus 5.5 e DeepSeek V4.1 Flash
    (`models.toml`, `extra_body`); dal 2 nov (R3) anche per Kimi K3.1 Pro, che il planner puo' scegliere come
    worker. Era anche il default del catalogo OpenRouter letto il 2 nov 2026 (Opus:
    ragionamento obbligatorio; DeepSeek: acceso). Limite: lo stesso livello non e' la stessa quantita' di
    ragionamento su due modelli diversi.
  - *Temperatura.* Non si invia a nessun modello: vale quella del fornitore. Opus 5.5 non accetta il parametro,
    quindi un valore comune non e' fissabile. Limite dichiarato.
  - *Ciclo di verifica.* B non ha un passo di autocritica, perche' C non ha critico; B vede gli stessi strumenti e
    lo stesso cancello di C. Il cancello si vede attraverso lo strumento «guarda il sito» (`view_site`), che
    restituisce le stesse osservazioni su cui decide: avvio, motivo del mancato avvio, stato HTTP di `/` (aggiunto
    il 2 nov, R3) ed errori JavaScript. Non esiste uno strumento a parte che dia il verdetto.
  - *Tetti.* Uguali per tutti. Un tetto serve a fermare i guasti, non deve scattare nel lavoro normale.
    *Iterazioni: 80 per ogni agente (5 nov 2026)*: e' l'unico tetto che fa parte della misura. La run di prova di D
    con l'ambiente comune definitivo si e' fermata al limite predefinito di 30 con il sito gia' costruito e in
    verifica, quindi la regola iniziale (2 × il massimo usato) non era applicabile e il valore si e' fissato prima
    della campagna. Il tempo resta limitato dalle iterazioni e dai 300 s per comando.
    *Dollari: 5 $ per run, uguale per tutti i bracci (per C vale per la squadra intera), 7 nov 2026.* E' una rete di
    sicurezza sulla spesa, non una regola di misura: le run di prova sono costate 0,05 $ (D) e 0,36-1,42 $ (C).
    Se una run la tocca, lo si dichiara nei risultati. Il tetto della campagna intera si fissa con il preventivo
    (§11). La regola iniziale (dollari e tempo pari al doppio dei massimi della run di prova) e' stata abbandonata
    prima della campagna: un secondo e un terzo tetto avrebbero aggiunto modi di tagliare una run senza proteggere
    di piu'.
  - *Guasti della macchina (8 nov 2026, fissato dopo le prime run interrotte e prima di leggerne la qualita').*
    Una run che arriva alla fine (esito `completed`, `max_iterations` o `budget_exhausted`) conta com'e', anche se
    al suo interno un agente e' stato interrotto da un guasto (per C: un pezzo o la correzione); lo si dichiara nei
    risultati. Si ripete invece, sullo stesso compito e con gli stessi parametri, in una campagna di ripetizione
    `<id>-r` (poi `-r2`), una run che non e' arrivata alla fine perche' un errore del fornitore (`provider_error`
    nel registro) l'ha fermata mentre il computer che esegue la campagna era in stop (registro di sistema) o il
    credito del fornitore era esaurito (HTTP 402): esito `service_unavailable`, o `plan_failed` con errore
    `service_unavailable`. Si ripete allo stesso modo un compito che non e' partito per il tetto di spesa del
    braccio. Per ogni compito conta la prima run arrivata alla fine; le run interrotte, e quelle lanciate in
    ripetizione su compiti che avevano gia' una run arrivata alla fine, restano in `runs/` ma non entrano nei
    dati. Un errore del fornitore a computer acceso e con credito disponibile conta com'e'. Origine: nella
    campagna MVP del 7-8 nov il computer, a batteria, e' rimasto in stop dalle 19:18 alle 10:48 (ora locale), e
    alle 11:21 il credito del fornitore si e' esaurito. Regola corretta l'8 nov (scelta dell'autore): in una
    prima versione si ripetevano anche le run arrivate alla fine con un agente interrotto.
- **§7 τ_piace = 1** (2 nov 2026, fissato prima di qualunque misura, senza pilota). Un gradino intero della scala
  −2..+2; motivazione e ruolo descrittivo in §7.
- **§10 Analisi.** Stessi calcoli (bootstrap sui compiti, test t appaiato, rapporto di costo C/B) sui 5 compiti.
  Le conclusioni si scrivono come stime; «non inferiore» e «costa meno» si dichiarano solo se i criteri di §10 sono
  soddisfatti, cosa improbabile con 5 compiti. Niente ablazioni.

## 1. Ipotesi ✅

OrcV2 (braccio C) costa significativamente meno di Opus 5.5 con gli stessi strumenti (braccio B), con una
qualita' non inferiore di piu' di τ, nella generazione di siti web (D36). Condizione di convenienza dichiarata
prima delle misure: `m / r + q < 1` (D37).

- ✅ **Meccanismo (23 ott 2026, D48):** OrcV2 decide quando passare dal modello economico al forte con un
  **cancello eseguibile** (controlli gratuiti sul sito prodotto, visibili all'agente), non con una previsione. Il
  cancello non vede mai script, domande o siti di riferimento della valutazione (§6).
- ✅ **Domanda secondaria (23 ott 2026, D49):** quanto del risparmio spiega ciascuna leva, confrontando C con
  politiche piu' semplici che usano gli stessi modelli e strumenti (bracci D, V, H di §3). Condizioni di convenienza
  di V e H dichiarate prima delle misure in `TESI_master.md` §0.2.

## 2. Compiti

- ✅ **Tipo (21 ott 2026, rivisto lo stesso giorno in R1):** meta' **siti di contenuto** con interattivita'
  leggera (landing, portfolio, evento; menu, galleria, form) e meta' **applicazioni web complete**, anche con un
  server (Node o Python nella sandbox) e con framework che richiedono una compilazione (Vue, React). Esclusi i
  compiti che richiedono un'API a pagamento o con chiave, un servizio di AI o l'invio di email, e quelli che non
  producono un sito (mini-program WeChat, programmi desktop). Ogni sito consegnato si avvia con un solo comando
  su una porta fissa. Motivo della revisione: compiti piu' vicini a quelli reali, e il server e' una parte del
  lavoro dove il risparmio con modelli economici e' plausibile (da misurare).
- ✅ **Fonti (D40):** WebGen-Bench (arXiv 2505.03733, dati con licenza MIT) e ArtifactsBench (arXiv 2507.04952,
  licenza CC BY 4.0, va citato), piu' alcuni compiti scritti per questa tesi.
- ✅ **Copie usate (21 ott 2026):** WebGen-Bench da GitHub `mnluzimu/WebGen-Bench`, file `data/test.jsonl` al
  commit `c89e0743438e458d617cebaf7a682e0e66e41049`; il repository non dichiara una licenza, vale la MIT della
  scheda Hugging Face `luzimu/WebGen-Bench` degli stessi autori (le 101 righe coincidono campo per campo,
  verificato il 21 ott 2026). ArtifactsBench da GitHub `Tencent-Hunyuan/ArtifactsBenchmark`, file
  `dataset/artifacts_bench.json`, licenza CC BY 4.0 dal file `LICENSE` del repository (la scheda Hugging Face
  dello stesso dataset indica CC BY-NC 4.0: fa fede il `LICENSE` della copia usata).
- ✅ **Numero e divisione (rivisto il 21 ott 2026 in R1; prima D45: 8 di sviluppo e 20 di test):** per ora
  5 compiti di **sviluppo**, completi (contratto delle rotte e domande per compito), su cui si lavora fino a R4.
  Il numero dei compiti di **test** si decide piu' avanti, prima di R6; si prenderanno proseguendo lo stesso
  ordine estratto con il seme, dopo i compiti di sviluppo, cosi' la loro scelta e' fissata gia' ora. Attenzione
  alla potenza: con 20 compiti e una deviazione standard ipotizzata di 25 punti, anche con C uguale a B la non
  inferiorita' con τ = 10 si dimostrerebbe circa 4 volte su 10 (calcolo e opzioni in `ROADMAP.md`, R6.1).
- ✅ **Consegna (22 ott 2026):** ogni braccio consegna nella radice del workspace un file `start.sh` che avvia il
  sito in primo piano sulla porta 8080; il valutatore lo lancia e aspetta la porta al massimo 60 secondi.
  `start.sh` mancante o che non apre la porta in tempo: «funziona» = 0.
- ✅ **Dipendenze e compilazione (22 ott 2026):** le installa e le compila l'agente durante la generazione, dentro
  il workspace, con un lockfile; la valutazione non scarica nulla. In `runs/` il workspace si archivia senza
  `node_modules`.
- ✅ **Immagini (22 ott 2026):** i bracci possono generare immagini con uno strumento comune, uguale per tutti,
  che chiama un modello d'immagini via OpenRouter; il costo entra nel costo per pagina. Modello: GPT Image 2.5 Sunburst (`openai/gpt-image-2.5-sunburst`, 22 ott 2026).
- ✅ **Revisione della regola di giudizio (22 ott 2026):** si scartano anche i compiti il cui contenuto principale
  e' in una lingua o in un dominio che giudice e votanti non sanno verificare. Aggiunta dopo aver gia' scelto i
  compiti di sviluppo: per questo `1594` (poesie di Su Shi, tenuto il 21 ott) esce e si sostituisce con il successivo
  valido nell'ordine di ArtifactsBench. La regola vale anche per i compiti di test.
- ✅ **Compiti di sviluppo, stato finale (22 ott 2026):** `000098`, `000040`, `000058` (WebGen-Bench), `842`, `684`
  (ArtifactsBench). Nessuna quota per tipo nello sviluppo. Dopo `1594`, letti nell'ordine: `1701` ❌ dati statistici
  non verificabili; `1618` ❌ programma desktop; `1236` ❌ mini-program e AI; `1024` ❌ specifica insufficiente;
  `684` ✅. Verdetti in `campaigns/r1_compiti.toml`; il codice rifa' la scelta dai file veri.
- ✅ **Testo dei compiti (22 ott 2026):** il testo arriva ai bracci com'e' nel benchmark, compreso il preambolo di
  ArtifactsBench («You are a code expert…»), uguale per tutti i bracci.
- ✅ **Composizione del prompt (24 ott 2026):** testo del compito com'e', poi la cornice comune
  (`campaigns/r1_prompt/cornice.md`: `start.sh` sulla porta 8080, dipendenze e build nel workspace con lockfile,
  niente rete ne' CDN, `data-testid` obbligatori, `datetime-local`, contratto rispettato esattamente), poi il
  materiale del compito (`campaigns/r1_prompt/<id>.md`: contratto delle rotte se c'e', marcatori, note). Il
  materiale del prompt sta in file separati da quelli di valutazione e ammette solo tre sezioni; codice in
  `webprompt.py`. Prompt in inglese, come i testi dei compiti: contratti e marcatori approvati in italiano sono
  tradotti, con test che ne controllano l'allineamento (stessi marcatori, stesse rotte).
- ✅ **Scelta:** prima si filtrano i compiti che rispettano le regole qui sopra, poi si estraggono a sorte con un
  seme scritto in questo file, separatamente per siti e applicazioni.
- ✅ **Seme del sorteggio:** 20261021.
- ✅ **Ordine registrato (24 ott 2026):** l'ordine di lettura estratto di ciascuna fonte sta in
  `campaigns/r1_ordine.json` e il codice lo confronta con quello calcolato: un ordine diverso (per esempio con
  un'altra versione di Python) e' un errore, non uno spostamento silenzioso.
- ✅ **Compiti della calibrazione del giudice (24 ott 2026):** solo compiti di ArtifactsBench dalla 300ª posizione
  dell'ordine registrato in poi; i compiti di test si prendono dall'inizio dello stesso ordine e non la raggiungono.
  Coppie dalle risposte pubblicate di ArtifactsBench (CC BY 4.0, con attribuzione), solo HTML in un file, piu'
  almeno 20 coppie dal pilota di R2 per i siti con server.
- ✅ **Modo del filtro (21 ott 2026):** un pre-filtro per etichetta toglie le categorie che non sono siti ne'
  applicazioni nel browser; i candidati si mescolano con il seme e si leggono nell'ordine estratto, tenendo chi
  rispetta le regole fino al numero richiesto. E' equivalente a filtrare tutto e poi estrarre: in un ordine
  casuale i primi N validi sono un campione casuale dei validi. La regola di giudizio si scrive prima di leggere;
  ogni compito letto, anche scartato, si registra con il motivo.
- ✅ **Contratto delle rotte (21 ott 2026):** per ogni applicazione con server si scrivono, prima di generare,
  le rotte e i dati che si scambiano; il contratto va nel prompt, uguale per tutti i bracci. I test colpiscono il
  server direttamente: creazione, lettura, modifica, cancellazione, input sbagliato rifiutato, dati presenti
  dopo un riavvio del server. Il server deve partire con il suo comando entro 60 secondi, altrimenti
  «funziona» vale 0.
  Il contratto si scrive per i compiti il cui testo chiede di salvare, elaborare o condividere dati dell'utente
  (22 ott 2026): fra i compiti di sviluppo `000098`, `000040`, `000058`, `684`; non `842`.
  Il contratto copre sempre le quattro operazioni (crea, leggi, modifica, cancella) sulle risorse del compito, anche
  quando il testo non le nomina tutte (es. cancellare un file in `684`): il sistema deve completare cio' che un
  utente si aspetterebbe (22 ott 2026).
- ✅ **Giochi esclusi (21 ott 2026):** il pre-filtro toglie le categorie *Game Development-\** di ArtifactsBench e
  *Browser-Based Games* di WebGen-Bench. Molti giochi disegnano su `<canvas>` e cambiano stato nel tempo: lo
  script di interazione di §6 non avrebbe elementi affidabili da controllare. Limite dichiarato: la tesi non
  dice nulla sui giochi.
- ✅ **Pre-filtro di ArtifactsBench (21 ott 2026):** passano solo *Web Applications-\**, *Management Systems-\**,
  *Utility Tools-\** tranne *Web Scraping*, e *Data Science-Data Visualization Dashboards*. Restano fuori SVG,
  Mermaid, Simulation & Modeling (disegnano su `<canvas>` come i giochi), Multimedia Editing, le altre voci di
  Data Science (quasi sempre in Python) e *Other-\** (etichette sparse da un compito). WebGen-Bench: tolti solo i
  giochi.
- ✅ **Compiti di sviluppo estratti (21 ott 2026).** Regola di completezza: il testo nomina almeno 3 funzioni
  verificabili; si scartano anche i compiti non verificabili nella sandbox (camera, microfono). Ordine: ogni fonte
  ordinata per identificativo e mescolata con `random.Random(20261021).shuffle`; 3 da WebGen-Bench, 2 da
  ArtifactsBench.
  - WebGen-Bench: `000098` noleggio auto (applicazione) ✅; `000068` meteo e qualita' dell'aria in tempo reale ❌
    dati esterni con chiave; `000040` sito di consulenza con vendita di servizi (sito) ✅; `000058` coaching uno a
    uno (applicazione) ✅.
  - ArtifactsBench: `1100` appello in classe ❌ specifica insufficiente; `569` videoriunioni ❌ camera e microfono;
    `225` login Flask+Vue ❌ specifica insufficiente; `909` formattazione SQL ❌ specifica insufficiente; `1020`
    merge sort ❌ specifica insufficiente; `842` «Security Center 3.7», cruscotto di monitoraggio (applicazione) ✅;
    `1594` poesie di Su Shi con indice, navigazione, pinyin e lettura (sito) ✅.
- 🔲 Compiti di test (numero e lettura) e compiti scritti per la tesi: rimandati, prima di R6.

## 3. Bracci ✅ (D39, modificata da D45)

| Braccio | Cosa |
|---|---|
| B | Opus 5.5 da solo con gli stessi strumenti e lo stesso ciclo di verifica di OrcV2 |
| C | OrcV2 |
| D | Il modello economico dei worker di OrcV2, da solo, con gli stessi strumenti |
| V | Cascata (D49): il sito di D se supera il cancello di D48, altrimenti il sito di B. Non si esegue a parte: si compone dalle esecuzioni di B e D, perche' B parte da zero e non dipende da D |
| H | Plan/Execute (D49): agente singolo, Opus 5.5 fino alla prima scrittura di un file, poi il modello economico con tutta la storia, stessi strumenti |

Il braccio A (Opus senza strumenti) e' stato tolto per costo (D45). Ogni strumento dato a C si da' anche a B, D e
H (D42).

- 🔲 **Cancello di V (e di C):** cosa controlla, scelto in R2 (ROADMAP R2.6) prima del pilota.
- 🔲 **H:** cosa conta come «prima scrittura» e se Opus riceve un'istruzione di pianificare prima di scrivere,
  scelti in R2 (ROADMAP R2.7) prima del pilota.

## 4. Modelli ✅ (D38)

Versioni, fornitori e listini in `models.toml` (letti il 19-24 ott 2026). Modello economico: DeepSeek V4.1 Flash
`-1017` sull'endpoint DeepSeek (D47), usato dai worker di C e dal braccio D. Le run a pagamento si lanciano fuori
dalla fascia oraria in cui DeepSeek raddoppia il prezzo (giorni feriali, 01-04 e 06-10 UTC).

- ✅ **Intermedio (24 ott 2026, D51, modifica D38):** Kimi K3.1 Pro sostituisce GPT-6.1 Sol nella rosa e nel
  ruolo `worker`. Identificativo OpenRouter `moonshotai/kimi-k3.1-pro`, endpoint standard Moonshot
  `moonshotai/mxfp4`: input 2, output 10, lettura cache 0,20 dollari per milione di token, letti dal catalogo
  pubblico degli endpoint il 24 ottobre. GPT-6.1 Sol e Kimi K3 restano nel registro senza ruolo per i dati
  storici. La scelta non cambia DeepSeek di D47 ne' decide l'assegnazione finale dei worker di C (R2.3).
  Nessun confronto di qualita' ne' costo per compito misurato con K3.1 Pro.

## 5. Ambiente ✅ (21 ott 2026)

Sandbox Docker con rete `bridge` e il firewall del progetto (blocca la macchina e la rete locale), uguale per
tutti i bracci.

- ✅ **Limite dichiarato (22 ott 2026):** durante la generazione i bracci hanno internet e le soluzioni di alcuni
  compiti sono pubbliche (risposte di 20 modelli pubblicate da ArtifactsBench). Nessuna contromisura: e' un limite
  dichiarato, uguale per tutti i bracci.

## 6. Qualita' (D41)

- ✅ Tre livelli: controlli automatici, giudice a coppie in entrambi gli ordini con famiglie non in gara, voti
  umani alla cieca (4-6 persone) per verificare il giudice. Giudice scelto in R1 fra Gemini 4 Argon e Gemini 3.8
  Flash per accordo con i voti umani. **Rivisto il 24 ott 2026 (D52):** giudice GPT-6.1 Sol via Codex CLI con
  l'abbonamento dell'autore (famiglia non in gara dopo D51); si usa solo se l'accordo con i voti umani regge.
- ✅ **Controlli automatici (livello 1, 21 ott 2026):** Playwright apre il sito e verifica: (1) apertura senza
  errori JavaScript in console; (2) nessuno scorrimento orizzontale a 375, 768 e 1440 px; (3) problemi gravi di
  accessibilita' secondo axe-core; (4) uno script di interazione scritto prima della generazione (per le
  applicazioni si riusano i casi di prova di WebGen-Bench). Il risultato e' un **punteggio con credito parziale**,
  non un cancello: un sito con un solo passo fallito non vale quanto un sito vuoto.
- ✅ **Checklist del giudice (21 ott 2026):** prima di votare il giudice risponde si'/no, per ciascun sito, a sei
  domande fisse e a 2-4 domande scritte per quel compito. Domande fisse: (1) la pagina fa cio' che chiede il
  compito? (2) le informazioni sono organizzate in modo chiaro? (3) il testo e' leggibile a tutte e tre le
  larghezze? (4) colori, caratteri e spaziature sono coerenti? (5) su telefono il layout si adatta senza elementi
  tagliati o sovrapposti? (6) nel complesso sembra un sito professionale? Le domande per compito si scrivono
  prima di generare qualunque sito: per ArtifactsBench si partono dalle voci specifiche della sua checklist, per
  WebGen-Bench dai casi di prova di aspetto. Le risposte non entrano nella metrica: servono a guidare il giudice
  e a capire dove C perde.
- ✅ **Validazione del giudice (R1.10, 25 ott 2026, fissata prima di vedere i voti umani):**
  - *Dati:* le 150 coppie principali di `campaigns/r1_coppie.json`, votate da 7-8 persone sulla scala −2..+2
    con il segno riportato all'ordine della coppia. Per le 5 coppie ripetute conta il primo voto; le ripetizioni
    misurano solo la coerenza di ciascun votante. Un votante che non finisce entra con le coppie votate.
  - *Voto del giudice:* uno per coppia, media dei due ordini (D46). Un «non valutabile» esce da tutti gli accordi
    (anche da quelli fra umani, perche' i due numeri restino sulle stesse coppie) e si riporta a parte.
  - *Metrica principale (D1):* accordo sul segno a tre classi (A meglio, pari, B meglio) con **Scott's π**
    (Scott 1955), riportato insieme all'accordo percentuale come in Thakur et al. 2406.12624.
  - *Confronto (D2):* π(umani-umani) e' la media di π su tutte le coppie di votanti; π(giudice-umani) e' la media
    di π fra il giudice e ciascun votante. Ogni π si calcola sulle coppie votate da entrambi.
    Δ = π(giudice-umani) − π(umani-umani). L'accordo fra umani e' un riferimento, non un tetto: Δ > 0 e' possibile.
  - *Intervalli:* bootstrap sulle coppie, 10.000 ripescaggi, seme 20261025; si ricalcolano entrambi gli accordi
    sullo stesso ripescaggio (Vanbelle e Albert 2008, esteso da κ a π).
  - *Accettazione (D3, D4):* il giudice si usa se (1) il 2,5° percentile di π(umani-umani) e' sopra 0, (2) quello di
    π(giudice-umani) e' sopra 0, (3) quello di Δ e' sopra **−0,10**. Limite dichiarato: con 150 coppie e 7 votanti,
    in simulazione, un giudice poco peggiore di un votante umano passa circa una volta su due.
  - *Metriche secondarie, senza soglia:* α ordinale di Krippendorff sui voti graduati (giudice con i mezzi punti
    della media); accordo a due classi sulle coppie senza pareggi, per confronto con Zheng et al. 2306.05685.
  - *Piano B (D5):* se manca una delle tre condizioni, «piace» resta metrica principale ma in R6 le coppie C-B si
    fanno votare alle persone (l'autore escluso, perche' non cieco su C); τ_piace si fissa sulla variabilita' dei
    voti umani. Se in R6 i votanti non bastano, la scelta fra questa strada e «piace» secondaria e descrittiva si
    rifa' prima di vedere qualunque coppia C-B. Nessun secondo giudice si calibra sugli stessi voti.
  - *Scostamento nei dati (29 ott 2026, scritto prima di calcolare gli accordi):* raccolta dichiarata chiusa
    dall'autore il 29 ott. Esportati 7 votanti invece di 7-8 con 150 coppie ciascuno: coppie principali votate
    78, 44, 31, 6, 3, 1, 0; tutti seguono lo stesso ordine, quindi solo 44 coppie su 150 hanno almeno due voti
    umani. La regola si applica senza modifiche sui voti disponibili. Lo script richiede che coppie votate e
    giudicate coincidano: si passano i voti del giudice sulle sole 78 coppie con almeno un voto umano (le altre 72
    non entrano in nessun π); il bootstrap ripesca fra queste 78.
  - *Esito (29 ott 2026): giudice non accettato, si attiva il piano B.* 78 coppie, 6 votanti con almeno un voto,
    0 non valutabili, 10.000 ripescaggi, seme 20261025. Stima [2,5%; 97,5%]: π(umani-umani) 0,048 [−0,444; 0,146];
    π(giudice-umani) 0,345 [−0,018; 0,492]; Δ 0,297 [0,124; 0,652]. Condizioni (1) e (2) mancate, (3) soddisfatta.
    Secondarie: accordo percentuale umani-umani 0,696, giudice-umani 0,665; senza pareggi 0,831 e 0,855; α
    ordinale 0,062 e 0,522. Lettura: con questi voti l'accordo fra persone non si distingue dal caso, quindi la
    prova non ha un riferimento su cui misurare il giudice; il risultato non dice che il giudice sia peggiore delle
    persone. Per il piano B vale la clausola sui votanti insufficienti: la scelta fra voti umani sulle coppie C-B e
    «piace» secondaria e descrittiva si fa prima di vedere qualunque coppia C-B.
  - *Revisione dell'esito (29 ott 2026, decisa dall'autore dopo il calcolo):* con 3 votanti utili e 44 coppie in
    comune la prova non ha un riferimento umano stimabile: l'esito si riclassifica **non conclusivo per dati
    insufficienti**, non come bocciatura del giudice. Il ruolo del giudice si decide con una prova su un insieme
    pubblico di voti umani (Vibe Design Arena), con una regola scritta e registrata prima di far giudicare
    qualunque coppia di quell'insieme. La riclassificazione e' decisa dopo aver visto i numeri sopra e va riportata
    come tale.
- **Prova del giudice su voti pubblici (R1.12, 29 ott 2026, fissata prima di far giudicare qualunque coppia):**
  - *Dati:* Vibe Design Arena (`datapointai/vibe-design-arena`, CC-BY-4.0): 60 siti, 1.770 coppie, per ogni coppia
    i totali dei voti umani (30 previsti) e uno screenshot 1440×900 per sito. Si escludono le coppie in parita'.
    Fra le restanti se ne estraggono **150** con seme **20261029**; le altre non si guardano.
  - *Voto del giudice:* stesso modello e sforzo di R1.9, prompt adattato a un solo screenshot per sito e senza
    testo del compito; due ordini e media (D46). Media 0 o «non valutabile» contano come **disaccordo**.
  - *Accordo del giudice:* quota delle 150 coppie in cui il giudice preferisce il sito che ha la maggioranza dei voti.
  - *Riferimento umano:* per una coppia con n voti e m alla maggioranza, una persona presa a caso concorda con la
    maggioranza delle altre n−1 con probabilita' m/n; il riferimento e' la media di m/n sulle stesse coppie.
    Δ = accordo del giudice − riferimento umano.
  - *Intervalli:* bootstrap sulle 150 coppie, 10.000 ripescaggi, seme 20261029, entrambe le quantita' sullo stesso
    ripescaggio.
  - *Accettazione:* il giudice si usa per «piace» sulle coppie C-B se (1) il 2,5° percentile del suo accordo e'
    sopra **0,5** e (2) il 2,5° percentile di Δ e' sopra **−0,10** (stesso margine di R1.10). Altrimenti «piace» e'
    metrica secondaria e descrittiva.
  - *Limiti dichiarati:* siti reali e non generati da modelli per un compito; una sola larghezza; voti solo
    aggregati, quindi niente accordo fra singole persone; chi sono i votanti non e' indicato.
  - *Esito (2 nov 2026): giudice non accettato; «piace» e' metrica secondaria e descrittiva.* Regola e campione
    committati prima dei giudizi (`c991a56`, `campaigns/r1_vibe_coppie.json`). 150 coppie giudicate fra il 29 ott e
    il 2 nov (quota esaurita all'ultima coppia, ripresa con gli stessi metadati), 0 non valutabili, 21 pareggi del
    giudice. Stima [2,5%; 97,5%]: accordo con la maggioranza 0,507 [0,427; 0,587]; riferimento umano 0,637 [0,623;
    0,650]; Δ −0,130 [−0,205; −0,052]. Condizioni (1) e (2) mancate. Descrittivo, fuori dalla regola: il giudice
    concorda in 18 coppie su 52 con maggioranza sotto il 60%, 26 su 50 fra 60% e 70%, 32 su 48 dal 70% in su; nei
    due ordini sceglie lo stesso sito in 129 coppie su 150.
- ✅ **Date e orari (23 ott 2026):** quando un compito chiede di scegliere data e ora, il prompt impone campi
  `datetime-local` (data e ora nello stesso campo), uguali per tutti i bracci.
- ✅ **Marcatori per lo script (22 ott 2026):** il prompt di ogni compito elenca fino a 12 attributi `data-testid` (5-8 fino al 22 ott, alzato
  perche' ogni funzione richiesta abbia il suo)
  obbligatori, uguali per tutti i bracci; lo script di interazione trova gli elementi solo attraverso quelli. Un
  marcatore mancante fa fallire il passo che lo usa.
- ✅ **Esecuzione e controlli (22 ott 2026):** il sito si avvia e si apre in un'immagine «renderer» costruita sopra la
  sandbox piu' Chromium (Playwright, versione bloccata), con server e browser nello stesso container e **senza
  rete**. Screenshot a pagina intera tagliati a 4000 px, un solo stato: la pagina iniziale; per i compiti con contratto,
  la pagina dopo la «vetrina» dello script, cioe' dati d'esempio preparati via rotte (22 ott 2026: ogni passo dello
  script riparte da un sito pulito, quindi «dopo lo script» non indica uno stato unico). Errori: eccezioni non gestite e `console.error`, al caricamento e durante lo script;
  le risorse mancanti come la favicon non contano. Sbordo: `scrollWidth > clientWidth + 1` a ciascuna larghezza dopo
  il caricamento dei font. Accessibilita': violazioni axe-core di impatto `critical` e `serious`, con `axe.min.js`
  (MPL-2.0) nel repository. Il risultato di una valutazione e' un file JSON.
- ✅ **Script d'interazione (22 ott 2026):** un file Python per compito (rivisto il 22 ott: il formato
  dichiarativo non reggeva calcoli, confronti nel tempo e riavvii), scritto con una libreria comune di funzioni ed
  eseguito da un interprete unico; ogni passo riporta il caso di prova o la voce di checklist da cui deriva. Se un passo fallisce, i passi che
  ne dipendono contano come falliti. I test diretti sulle rotte non entrano in «funziona»: formano la metrica
  secondaria «funziona-server» (quota di test superati, 0-100), riportata per C contro B sui compiti con contratto,
  con il suo intervallo e senza dichiarazione di non inferiorita'.
- ✅ **Passi preparati via rotte (22 ott 2026):** quando un passo d'interfaccia prepara i dati chiamando le rotte del
  contratto e la preparazione fallisce, il passo e' «non valutabile»: non conta ne' come superato ne' come fallito,
  esce dal denominatore e si riporta a parte. Il contratto non rispettato si conta una volta sola, nei test delle
  rotte. Se nel pilota i passi non valutabili risultano molti, si aggiunge una mappa fra le rotte del contratto e
  quelle del sito fatta da un modello economico di un'altra famiglia, registrata per ogni sito.
- ✅ **Punteggio «funziona» (21 ott 2026):** quota di passi dello script di interazione superati, da 0 a 100; 0 se
  la pagina non si apre. Sbordo alle tre larghezze e problemi di accessibilita' si riportano a parte, per braccio,
  e non entrano nel punteggio.
- Revisione: le domande si possono rivedere sui compiti di sviluppo (R1, R4); si congelano prima di R6.

## 7. Metrica principale e margine τ

- ✅ **Due metriche affiancate, nessun voto unico (21 ott 2026):** (1) **funziona**: differenza media fra C e B nel
  punteggio del livello 1 (0-100), sugli stessi compiti; (2) **piace**: voto medio del giudice nel confronto a
  coppie C contro B, su una scala graduata da −2 (B molto meglio) a +2 (C molto meglio), 0 = pari. Ogni coppia si
  giudica in entrambi gli ordini e si fa la media dei due voti, col segno riportato dalla parte di C. C e' «non
  inferiore» solo se lo e' su entrambe. *Dopo R1.12 (2 nov 2026, §6):* il giudice non e' accettato, «piace» e'
  secondaria e descrittiva e la dichiarazione di non inferiorita' si regge solo su «funziona».
- ✅ **τ_funziona = 10 punti** (21 ott 2026): la media di «funziona» di C puo' stare fino a 10 punti su 100 sotto quella di B (con 5-8 passi per compito un singolo passo vale 12-20 punti: τ e' una differenza media sui compiti, non un passo per sito).
- ✅ **τ_piace = 1 (2 nov 2026).** La regola del 21 ott (valore dopo il pilota di R2) decade con D55: il pilota non
  si fa e il valore si fissa prima di qualunque misura, sulla scala −2..+2. *Motivazione:* 1 e' un gradino intero,
  da «pari» a «B meglio», il gradino piu' usato sia dal giudice (78 e 75 voti medi su 150 in R1.9 e R1.12) sia dalle
  persone (107 voti su 165 in R1.10); differenze sotto un gradino si leggono come trascurabili. *Ruolo:* con
  «piace» descrittiva (§6), τ_piace non decide nulla: e' la linea di riferimento a −1 nella tabella e nel grafico
  costo-«piace» di §10, e si riporta se il limite basso dell'intervallo bootstrap sta sopra o sotto. *Limiti
  dichiarati:* (1) il margine e' largo: un C giudicato «B meglio» in ogni compito starebbe esattamente sulla linea;
  (2) con 5 compiti e uno scarto tipico dei voti medi del giudice di 1,28-1,38 (R1.12, R1.9), meta' intervallo vale
  circa 1,1 punti: anche con τ = 1 la linea si supera solo se C e' in media circa pari a B o meglio.

## 8. Costo ✅

Dollari per pagina, misurati dal ledger; i token solo come dato ausiliario.

## 9. Ripetizioni ✅ (D45)

Una esecuzione per compito e per braccio.

## 10. Analisi ✅ (21 ott 2026)

- Per ogni metrica di §7: differenza C − B per compito, media sui compiti di test, intervallo con **bootstrap**
  sui compiti (10.000 ricampionamenti). **C e' non inferiore** se il limite basso al 2,5% e' sopra −τ, su entrambe
  le metriche.
- Controllo: si riporta anche il test t appaiato. Se i due metodi danno conclusioni diverse, il risultato e' «non
  dimostrato».
- Costo: rapporto C/B con il suo intervallo bootstrap; «costa meno» e' dimostrato se tutto l'intervallo sta sotto 1.
- Il braccio D e le ablazioni si riportano e si commentano, senza dichiarazioni di significativita': la prova
  principale e' una sola, C contro B.
- ✅ **Scala di politiche (23 ott 2026, D49):** B, D, V, H e C si riportano sullo stesso piano costo-«funziona» e
  costo-«piace», ciascuno con il rapporto di costo su B e la differenza da B con intervallo bootstrap, senza
  dichiarazioni di significativita'. «Piace» di V: nei compiti in cui il cancello accetta vale il voto della coppia
  D-B, negli altri 0 (stesso sito di B); «piace» di H: coppie H-B giudicate come C-B. Si riportano anche `a` (quota di compiti in cui D supera il cancello) e la
  quota di spesa di Opus in H e in C.
- ✅ **Semi delle analisi (8 nov 2026).** Il seme 20261108 dei bootstrap dell'analisi della campagna MVP e' stato
  scelto durante l'analisi, non prima. Con 5 compiti gli intervalli coincidono con il bootstrap esatto (tutti i 3125
  ricampionamenti), e con i semi gia' registrati 20261021, 20261025 e 20261029 nessun esito cambia (unica differenza:
  limite basso di D−B −14,7 invece di −15,3). Dalle prossime misure ogni analisi usa il seme **20261021**, scritto
  qui prima dei dati; con 8 compiti o meno si riporta il bootstrap esatto.

## 11. Spesa ✅ (D44)

Preventivo prima di ogni fase (misurato per le campagne), tetto deciso fase per fase, `--budget-usd` su ogni
esecuzione.
