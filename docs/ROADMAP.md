# ORC — Roadmap

> **Cos'e'.** Il piano vigente del progetto: cosa fare, in che ordine e quando una fase e' finita.
> Le fasi M1-M7 scritte fino al 18 ottobre 2026 sono in `ROADMAP_storico.md`: M1, M2a e M3 sono
> completate e restano la base del codice; M2s e' chiusa come superata; M4, M2b e M7 sono state
> sostituite dalle fasi R0-R7 (decisioni D35-D44 in `PIANO_completo.md`).
>
> **Come si usa.** Si apre la fase corrente e si prende la prima voce non spuntata. Una fase si
> chiude quando tutte le sue voci sono spuntate e verificate; a fine fase si aggiorna la tabella
> qui sotto e si abbozza la sezione di tesi corrispondente.

## Stato generale

| Fase | Nome | Stato |
|---|---|---|
| M1 | Agente singolo | ✅ completata |
| M2a | Infrastruttura di misura | ✅ completata |
| M3 | Parallelismo | ✅ completata (decisioni D30-D34) |
| M2s | Routing statico per ruolo | ✅ chiusa come superata (D43): il dato su `f` lo dara' il braccio D |
| M4, M2b, M7 | Swarm, routing, campagna | ↪️ sostituite da R0-R7 (D43); testo in `ROADMAP_storico.md` |
| R0 | Decisioni e protocollo | ✅ completata il 21 ott 2026 (D35-D47, `PROTOCOLLO.md`); alcuni valori si fissano in R1-R2 per regola |
| **R1** | **Banco di prova (compiti, rendering, controlli, giudice, voti umani)** | ⬜ **prossima** |
| R2 | Baseline Opus 5.5 (pilota e preventivo misurato) | ⬜ |
| R3 | OrcV2 minimo: sciame per sezioni | ⬜ |
| R4.0 / R4 | Studio delle ottimizzazioni / ottimizzazione manuale | ⬜ |
| R5 | Ottimizzazione automatica (facoltativa) | ⬜ |
| R6 | Campagna finale e ablazioni | ⬜ |
| R7 | Router grossolano (facoltativo) | ⬜ |

**Percorso:** R0 → R1 → R2 → R3 → R4.0 → R4 → (R5) → R6 → (R7).

**Dove sta il contributo (D36):** il sistema e la scomposizione misurata del risparmio, cioe' quale leva
(strumenti, sezioni, verifica, ottimizzazione) produce quanto risparmio a qualita' non inferiore. La valutazione
e' co-centrale; il router appreso e' facoltativo (R7).

## Fasi R0-R7 (riprogettazione del 18 ottobre 2026)

**Perche'.** Prima di aprire M4 e' stata fatta un'analisi della letteratura recente (STORM, CAID, AgentRoom,
Kim et al. 2512.08296, AgentRouter, AgentCARD) e dei dati per tentativo pubblicati da DeepSWE v1.1 e Terminal-Bench
4.0, senza spesa. Esiti principali: a parita' di modello un sistema multi-agente costa 1,5-4,4 volte l'agente singolo;
il risparmio viene dai modelli economici, ma solo se il risultato viene **verificato** (prevedere in anticipo quale
modello basta perde 8-14 punti fuori campione, per la casualita' dei singoli tentativi); il risparmio dipende dal tipo
di compito; l'harness pesa quanto il modello. Da qui il riordino.

**Cosa resta uguale.** La frase della tesi (`min costo s.t. qualita' >= τ`), il dominio dei siti web (D16, confermato da
D35), l'architettura (planner, worker, verifica), tutto il codice di M1-M3.

**Cosa cambia.** Contributo = il sistema e la scomposizione misurata del risparmio, router facoltativo (D36); modelli
(D38); confronto equo con Opus dotato degli stessi strumenti (D39); valutazione a tre livelli verificata con voti umani
(D41); una fase di ottimizzazione dell'harness (D42); l'ordine dei lavori (D43).

### R0 — Decisioni e protocollo ✅
- [x] Decisioni D35-D44.
- [x] **Protocollo**: un file con le regole dell'esperimento (compiti con divisione sviluppo/test, bracci A-D,
      metriche dei tre livelli, domande della checklist del giudice, margine di non inferiorita' τ, ripetizioni,
      analisi statistica, modelli). Si fissa con un commit pubblicato prima della campagna finale (R6).
      Testo in `docs/PROTOCOLLO.md`. Decisioni prese una alla volta:
      - [x] R0-1 Come si fissa: un commit pubblicato prima di R6, senza altro meccanismo (19 ott).
      - [x] R0-2 Tipo di compito: meta' siti di contenuto, meta' applicazioni che girano nel browser (21 ott).
      - [x] R0-3 Bracci B, C, D; 20 compiti di test + 8 di sviluppo; una esecuzione per compito (D45, 21 ott).
      - [x] R0-4 Controlli automatici come punteggio con credito parziale, non come cancello (21 ott).
      - [x] R0-5 Due metriche affiancate, «funziona» e «piace», non inferiorita' su entrambe (D46, 21 ott).
      - [x] R0-6 Giudice con voto graduato −2..+2; τ_funziona = 10; τ_piace dopo il pilota di R2 (D46, 21 ott).
      - [x] R0-7 Checklist: sei domande fisse + 2-4 per compito (21 ott).
      - [x] R0-8 Analisi: bootstrap sui compiti al 2,5%, test t di controllo (21 ott).
      - [x] R0-9 Punteggio «funziona» = quota di passi dello script superati; sbordo e accessibilita' a parte (21 ott).
      - [x] R0-10 Seme 20261021; modello economico DeepSeek V4.1 Flash `-1017` al posto di V4 Pro (D47, 21 ott).
- [x] `models.toml` con la nuova rosa (D38), versioni e fornitori fissati sull'endpoint della casa, supporto alle
      immagini verificato (19 ott 2026). Kimi K3 e MiniMax M3 restano nel registro, senza ruoli, per prezzare le run
      gia' fatte. Dal 21 ott il modello economico e' DeepSeek V4.1 Flash `-1017` (D47); V4 Pro resta nel registro
      senza ruolo.
- [x] Condizione di convenienza (D37) scritta in tesi prima delle misure (`TESI_master.md` §0.1, 21 ott).
- Restano aperti **per regola**, non per ritardo: elenco dei compiti filtrati e domande per compito (R1), τ_piace
  (dopo il pilota di R2, prima di ogni confronto C contro B). Il protocollo si congela con un commit prima di R6.

### R1 — Banco di prova ⬜
- Compiti: circa 10 WebGen-Bench (MIT), circa 10 pagine ArtifactsBench, alcuni nostri; caricamento nel formato del progetto.
- Rendering con Playwright nella sandbox; screenshot a 375, 768 e 1440 px.
- Controlli automatici: apertura senza errori, errori in console, axe-core, scorrimento orizzontale, script di
  interazione scritti prima della generazione.
- Giudice a coppie in entrambi gli ordini, checklist si'/no, famiglie non in gara; scelta fra Gemini 4 Argon e Gemini
  3.8 Flash per accordo con i voti umani.
- Strumento di voto alla cieca per 4-6 persone (circa 50 coppie a testa); accordo fra persone e fra persone e giudice.
- Domande della checklist per compito (2-4 ciascuno) scritte prima di generare i siti; rilettura delle sei domande
  fisse alla luce dell'accordo giudice-umani.
- Container orfani (`orc-sandbox-*` rimasti dopo un crash o un Ctrl+C): pulizia all'avvio (ex «Da decidere a inizio M4»).
- Test: un compito d'esempio produce screenshot e metriche deterministiche; il giudice, con risposte finte, gestisce
  l'inversione dell'ordine e il pareggio; nessuna chiamata a pagamento nei test.

### R2 — Baseline ⬜
- Opus 5.5 da solo su 3 compiti pilota con `--budget-usd`; token e costo misurati; preventivo misurato per la
  campagna (circa $20 calcolati, D45).

### R3 — OrcV2 minimo: sciame per sezioni ⬜
- Planner (Opus): divisione in sezioni + sistema di stile (D5, D15), piano validato.
- Worker per sezione in parallelo (modelli economici), un file per sezione: niente scritture sullo stesso file, quindi
  le questioni «cartella condivisa o copie» e «consumi per squadra» non si pongono.
- Critico su screenshot per sezione (modello economico con visione), al massimo 2 giri, si tiene la versione migliore.
- Integratore deterministico (modello di pagina, non un LLM).
- Verifica finale ed escalation a Opus (ex M2b.2).
- Tetto globale del compito sulla somma dei contabili (ex M4.2c), contabile di squadra (D32).
- Strumento di modifica dei file migliore (sostituzione esatta, lettura per intervalli): si decide se riprenderlo da un
  harness aperto.

### R4.0 — Studio delle ottimizzazioni ⬜
- Sessione dedicata: skill (es. `frontend-design`), server MCP (es. Playwright), plugin, codice di harness aperti
  (SWE-agent, OpenHands, mini-swe-agent, Aider, Codex CLI) con licenza, prove e costo. Scelta dell'autore.

### R4 — Ottimizzazione manuale ⬜
- Una ottimizzazione alla volta, misurata sui compiti di sviluppo; ogni strumento dato anche al braccio B (D42).
- Revisione della checklist del giudice con i dati raccolti sui compiti di sviluppo; versione finale congelata
  prima di R6.
  Candidati con prove: prompt stabili per la cache, gestione del contesto, arresti che consegnano il lavoro fatto,
  strumento di piano per i modelli economici, Opus come consigliere, fotografia dell'ambiente, HTML + Tailwind, skill
  di design, critico per sezione.

### R5 — Ottimizzazione automatica (facoltativa) ⬜
- Ottimizzazione dei prompt (GEPA) e adattamento automatico dell'harness per modello, con divisione di test congelata.

### R6 — Campagna finale ⬜
- 20 compiti di test, bracci B, C, D, una esecuzione per compito (D45), ablazioni (uno strumento tolto alla volta), costo per pagina accettata,
  curva costo-qualita', risultato in funzione del rapporto di prezzo (D37).

### R7 — Router grossolano (facoltativo) ⬜
- Solo se i dati mostrano tipi di pagina in cui conviene andare subito su Opus.

### Dove finiscono le voci precedenti
M4.1 planner, M4.2 orchestratore, M4.4 gate -> R3. M4.2c tetto globale -> R3. M4.2b vita degli agenti -> solo la
gestione del contesto, in R4. M4.3 stato condiviso -> sezioni in file separati (R3). M4.7 best-of-N -> opzione in R4.
M4.8 ottimo di scomposizione -> numero di sezioni come variabile in R6. M4.0 e M4.6 (immagini, altre capacita') ->
rimandate; immagini solo se date anche al braccio B. M2b.1 giudice -> R1. M2b.2 cascata -> R3. M2b.4 router -> R7.
M2b.5 e `quality/` -> metriche di R1.

## Problemi aperti ancora validi

Dalle sezioni «Problemi aperti» di settembre e ottobre 2026 (testo completo in `ROADMAP_storico.md`), con la
fase in cui si risolvono.

| Problema | Dove |
|---|---|
| «Migliore» in che senso: bellezza, chiarezza o efficacia della pagina | R0 (checklist del giudice) |
| Il giudice sa giudicare quel criterio? E' il rischio piu' grosso | R1 (accordo con i voti umani, D41) |
| Cio' che non si vede in uno screenshot: mobile, passaggio del mouse, funzionamento | R0-R1 (tre larghezze, script di interazione) |
| τ: margine di non inferiorita' della campagna | R0 |
| Varianza fra esecuzioni dello stesso modello | R0: una esecuzione per compito, 20 compiti (D45) |
| Tetto di spesa che consegna il lavoro completo invece di troncarlo (B1-B6) | R3 (tetto globale), R4 (arresti che consegnano) |

## Regole operative permanenti

- **Ogni feature nasce col suo test.** Se non si sa come testarla, il design va rivisto prima di scriverla.
- **CI sempre verde.** Push solo con `pytest` verde in locale; se la CI si rompe, sistemarla e' il primo lavoro
  della sessione successiva.
- **Il log e' sacro.** Ogni esecuzione produce un log strutturato in `runs/`: non si cancella, sono i dati della tesi.
- **Ogni esecuzione con un tetto di spesa.** `--budget-usd` su ogni comando reale, con preventivo prima.
- **Fornitore fissato.** Ogni modello di chat ha il fornitore fissato in `models.toml`: senza, OpenRouter puo'
  instradare a un endpoint quantizzato e il listino smette di descrivere cio' che si paga.
- **Due metriche non sono la stessa metrica.** «−X% di token» e «−X% di dollari» divergono dove la cache e'
  attiva. In tesi si riportano **dollari**, i token solo come dato ausiliario.
- **Scrittura incrementale della tesi.** Ogni fase chiusa = sezione di tesi abbozzata subito.
