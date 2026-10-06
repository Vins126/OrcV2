# ORC — Piano d'azione operativo (roadmap di sviluppo)

> **Cos'è.** La traduzione operativa di `PIANO_completo.md` (otto decisioni accettate
> — D1-D5, D7-D9 — mentre D6 è rimandata a M2b per scelta). Qui c'è *cosa fare, in che
> ordine, come testarlo e quando considerarlo finito*. Ogni sessione di lavoro parte
> da questo file.
>
> **Come si usa.**
> 1. Apri la fase corrente, prendi il **primo task non spuntato**.
> 2. Leggi `Passi`, implementa, esegui il `Test`.
> 3. Se il test passa: segna il task come fatto (⬜ → ✅ nel titolo del task; le
>    caselle `- [ ]` delle Definition of Done si spuntano a fine fase), **commit**
>    con messaggio in italiano, passa al successivo.
> 4. A fine fase: verifica la **Definition of Done**, aggiorna lo stato qui sotto,
>    scrivi/aggiorna la sezione di tesi corrispondente **mentre è fresca**.
>
> I punti marcati **[SCELTA TUA]** sono manopole di comando dell'autore: valori e
> politiche li fissi tu, il codice li rende solo configurabili.
>
> Le fasi lontane (M2b, M7) sono volutamente meno granulari: si dettagliano quando
> ci si arriva, con l'esperienza delle fasi precedenti.

## Stato generale

| Fase | Nome | Stato |
|---|---|---|
| M1 | Agente singolo | ✅ completata |
| M2a | Infrastruttura di misura | ✅ completata |
| **M2s** | **Routing statico role-based (stadio S1)** | 🔜 **corrente** |
| UX1 | Sessione chat persistente | ⬜ (backlog prodotto) |
| M3 | Parallelismo | ⬜ |
| M4 | Swarm (Planner, Orchestratore, stato condiviso, Gate L1) | ⬜ |
| M2b | Intelligenza di routing (Judge L2, Cascade S2, Router S3) | ⬜ |
| M7 | Campagna sperimentale | ⬜ |

**Percorso critico:** M2a → M2s → M3 → M4 → M2b(S2) → M7.
**Dove sta il contributo:** nel router appreso (S3). S0, S1 e S2 sono l'apparato che lo
rende misurabile e difendibile, non un obiettivo alternativo (D13, settembre 2026 — prima
S3 era marcato opzionale). Se S3 non desse risultati, S0-S2 resterebbero un risultato di
ingegneria, non di ricerca: un'uscita di emergenza, non un traguardo.

> **Nota sul backlog UX1.** La chat persistente e' utile per l'uso quotidiano,
> ma non e' un prerequisito del percorso sperimentale della tesi. E' pianificata
> **dopo M2s** (vedi la sezione omonima fra M2s e M3) e **resta fuori dal percorso
> critico** M2a → M2s → M3 → M4 → M2b → M7: non blocca nessuna fase e nessuna fase
> dipende da lei. Va realizzata senza confondere una sessione umana con una run ReAct
> misurabile.

## Regole operative permanenti

- **Sviluppo con modello economico.** Durante lo sviluppo `ORC2_MODEL` punta a un
  modello cheap. Da M2s in poi il modello per ruolo lo decide il registro
  (`models.toml`); `ORC2_MODEL` resta solo come default per gli script mono-agente.
- **Ogni feature nasce col suo test.** Se non sai come testarla, il design va rivisto
  prima di scriverla.
- **CI sempre verde.** Push solo con `pytest` verde in locale; se la CI si rompe,
  sistemarla è il primo task della sessione successiva.
- **Il log è sacro.** Da M2a in poi ogni esecuzione produce un file di log
  strutturato: non cancellarli, sono il dataset del flywheel e i dati della tesi.
- **Scrittura incrementale della tesi.** Ogni fase chiusa = sezione di tesi
  abbozzata subito (architettura, scelte, misure). Non accumulare debito di scrittura.
- **Ogni esecuzione con un tetto di spesa.** `--budget-usd` su ogni comando reale. Il
  guardiano esiste e funziona (una run si e' fermata da sola: vedi
  `docs/esempio_run/`, dove pero' le risposte del modello sono riprodotte); usarlo sempre trasforma il rischio di spesa in un numero
  deciso prima di premere invio. Le spese della tesi non hanno un fondo dietro.
- **Percorso diretto ai fornitori.** Ipotesi, da verificare in M2s.4: passando da
  un aggregatore la prompt cache potrebbe non sopravvivere, o non essere fatturata
  con lo sconto del fornitore. I log (ago-set 2026, `minimax-m2-7`, LiteLLM →
  OpenRouter) sono contrastanti: token in cache nella run 24255293 (443 alla 2ª e
  3ª chiamata), zero nella run dell'1 settembre; il ledger calcola sul listino,
  quindi non dice cosa e' stato fatturato; opus-5 non e' mai stato eseguito. Un
  rifiuto di `cache_control` con 404 non e' registrato nei log. Decisione
  invariata: da M2s.2 ogni fornitore si chiama direttamente; l'aggregatore resta
  un'opzione di comodo per lo sviluppo, mai per le misure della campagna.
- **Due metriche non sono la stessa metrica.** «−X% di token» e «−X% di dollari»
  divergono di un ordine di grandezza dove la cache è attiva. In tesi si riportano
  **dollari**, e la percentuale di token solo come dato ausiliario.
- **TODO letture:** MasRouter (PDF integrale) prima di scrivere il related work;
  Trinity/Conductor prima di M2b. **Aggiunte ago 2026:** DeLM (2606.10662) —
  concorrente più diretto, riporta metà costo a qualità superiore su SWE-bench;
  FlyRoute (2605.22057) — prior più vicino sulle competenze apprese, **da leggere
  prima di rivendicare novità**; LLM-as-a-Verifier (2607.05391) — giudice a logit e
  torneo O(Nk); GoAgent (2603.19677); agentic plan caching (2506.14852).

---

## Problemi aperti (settembre 2026)

Emersi prendendo sul serio il fatto che la qualita' da valutare e' **soggettiva**.
Ordinati per **dipendenza**: ognuno condiziona quelli sotto, quindi si affrontano uno alla
volta, dall'alto. Il ragionamento completo e' in `TESI_master.md` §5.8-§5.11.

| # | Problema | Perche' in questa posizione |
|---|---|---|
| **1** | **«Migliore» in che senso?** Bellezza, chiarezza, o efficacia (la pagina fa il suo lavoro)? I criteri soggettivi di `TESI_master.md` §5.1 sono tutti estetici: una pagina puo' essere splendida e non vendere nulla. | Va definito per primo: non si sceglie un giudice ne' si fissa una soglia su qualcosa di non definito. E una domanda precisa alza l'accordo fra annotatori, quindi il soffitto della tesi |
| **2** | **Il giudice sa giudicare quel criterio?** I modelli di punta usati cosi' come sono restano lontani dagli esperti nel giudizio estetico (VAB, 2605.12684: 26,5% contro 68,9% degli esperti, su arte e fotografia) | Il **rischio piu' grosso** della tesi. Dipende da 1 |
| 3 | **Cio' che non si vede in uno screenshot**: resa su mobile, stati al passaggio del mouse, animazioni, funzionamento effettivo | Il giudice guarda immagini ferme, a entrambi i livelli (M4.4) |
| 4 | **τ ha due significati**: soglia sul singolo output durante il lavoro (`TESI_master.md` §5.6.4) e non-inferiorita' statistica nella campagna (M7.4) | Bradley-Terry da' un punteggio relativo, senza zero assoluto: τ va ancorata alla baseline (M2b.3) |
| 5 | **Varianza fra esecuzioni**: lo stesso modello sullo stesso prompt produce pagine diverse | Decide quante ripetizioni servono, quindi il costo della campagna |
| 6 | **Il pareggio del cheap-first con qualita' graduata**: il 95,8% calcolato vale solo per esiti netti | Nel soggettivo l'output economico non «fallisce»: e' peggiore *di quanto*, e vicino alla soglia si escala spesso |

**Risolti in questa revisione:**

- **Attribuzione del merito** e **validazione circolare** → giudizio a due livelli,
  sezione e pagina (M4.4, D14).
- **Coerenza fra sezioni** → il planner fissa il sistema di stile prima dei worker (M4.1, D15).
- **Art director separato** → un planner solo con due uscite; separarlo e' un esperimento
  misurabile, non un'assunzione (M4.1, D15).
- **Dominio** → resta il sito web intero (D16). Ridurlo a componenti isolati avrebbe
  semplificato la valutazione svuotando la ragione d'essere dello swarm: un componente si
  genera con una chiamata sola, non c'e' niente da scomporre ne' da instradare.
- **Annotatori per il kappa** → c'e' un secondo annotatore disponibile.

### Problemi aperti sul controllo del costo (ottobre 2026)

Emersi chiedendosi a cosa serva un tetto di spesa. Oggi il guardiano e' un **freno**: a
tetto raggiunto ferma l'agente (`budget_guard.py`), per agente e per vita dell'agente. Con
tetto 10 e sito da 12 si ottiene un sito **incompleto**; con un sito da 9 il tetto non
cambia nulla. Il guardiano non **sterza**: non cambia modelli o scelte in base al tetto.
Quello che si vuole e' che, fissato un tetto, il sistema consegni il lavoro **completo
entro** quel limite, adattando le proprie scelte.

**Decisioni dell'autore** (5 ottobre 2026):

- **Si da solo il tetto**, non anche una qualita' minima: le AI economiche completano ormai
  quasi tutte le task, quindi la completezza e' quasi garantita e la variabile e' la qualita'.
- **La task deve essere completa entro il tetto.** Rispettare il tetto viene prima della
  qualita': a tetto stretto si abbassa la qualita', non si lascia il lavoro a meta'.
- **Due casi, a seconda di dove nasce il problema:**
  1. *La stima iniziale regge.* Il sistema stima il costo **prima** di partire e sceglie
     modelli, numero di candidati ed escalation in modo da consegnare tutto con la qualita'
     che quel budget puo' comprare («qualita' proporzionale al budget»).
  2. *La stima si rivela sbagliata durante la run.* Il sistema rivaluta tutto e **si ferma a
     chiedere all'utente**, che sceglie, invece di decidere da solo:
     - **sforare**: «il sito costera' x+y invece di x, procedo comunque?»;
     - **degradare**: «finora e' costato x, il minimo per finire e' y ma la qualita' scende,
       accetti?».
- **Proporzionalita'.** Le opzioni offerte dipendono dall'ordine di grandezza del budget:
  con x = 1000 € (che presuppone una qualita' altissima) non si propone «2 € in piu' con
  qualita' pessima»; con un tetto di 5 € si e' disposti ad abbassare la qualita' per
  spendere meno. Il menu non puo' quindi offrire opzioni sotto una soglia di qualita'
  coerente con il budget iniziale.
- **Il «selettore».** Davanti allo sforamento l'utente sceglie fra piu' possibilita':
  «sforeremo i 5 € previsti: n1 costa z con la stessa qualita', n2 costa z2 con qualita'
  minore».
- **Fase di analisi avanzata.** Prima di partire il sistema puo' stimare qual e' il budget
  migliore per quella task in funzione dell'obiettivo (qualita' o prezzo).

**Come si incastra col resto** (ragionamento, non decisione):

- E' il **duale** dell'obiettivo della tesi: `min costo s.t. qualita' ≥ τ` diventa
  `max qualita' s.t. costo ≤ B`. Sono due modalita' di funzionamento sulla stessa frontiera
  costo-qualita', non due sistemi. Variando B si ottiene proprio la curva di Pareto di M7.4:
  il tetto diventa il parametro che la percorre.
- Il guardiano **resta** il freno di sicurezza; a sterzare e' l'orchestratore (M4.2). Il
  guardiano emette gia' un evento alla soglia morbida (80%): puo' fare da innesco, ma conviene
  scattare sulla **proiezione** della spesa, non su quella gia' fatta. Non contraddice la
  scelta di M2a.5 di non iniettare messaggi nel contesto del modello: a reagire e' chi
  orchestra, non l'agente, e la baseline S0 resta senza controllore.
- Con agenti persistenti (M2s.3) fermarsi a chiedere all'utente e' economico: l'agente
  mantiene il proprio stato e riprende dopo la risposta.
- Il costo dell'analisi preventiva, in quanto lavoro sul task, va contato nel tetto
  (proposta, da confermare).

| # | Problema | Note |
|---|---|---|
| **B1** | **Stima del costo prima di spendere.** Senza una previsione per sotto-task il planner non puo' rispettare un tetto. | Oggi il costo si conosce solo a chiamata avvenuta (limite intrinseco di §9.6). Fonti: le formule sul listino e le misure per ruolo che il ledger accumula (dataset del flywheel, M2b.3). Serve una riserva per l'incertezza, come in qualunque progetto con un budget. |
| **B2** | **Routing sotto vincolo.** Dato B, scegliere modelli, numero di candidati (best-of-N, M4.7), profondita' di escalation ed `effort` in modo che il costo atteso stia dentro B. | Letteratura da leggere: allocazione online di risorse sotto budget e tempo (2605.06110, finora letta solo in sintesi); i «task budget» dei fornitori, un tetto in token che il modello vede e usa per dosarsi. |
| **B3** | **Monitoraggio e innesco della ricalibrazione.** Confronto fra spesa e avanzamento ai checkpoint (M4.4); se la proiezione supera B, si ristima. | Misura di avanzamento: sezioni completate / sezioni del piano. |
| **B4** | **Negoziazione con l'utente.** Il menu di opzioni (sforare, degradare, parziale), la regola di proporzionalita', la soglia di qualita' sotto la quale non si scende. | Il menu e' **strutturato**: ogni opzione ha costo aggiuntivo, costo totale, livello di qualita' ed etichetta. Prima di M2b non ci sono punteggi di qualita' per le opzioni: all'inizio **livelli grossolani** (alta / media / bassa, legati alla fascia dei modelli), con punteggi numerici dopo M2b.5 (vedi M2b.7). |
| **B5** | **Senza risposta.** Cosa fare se nessuno risponde alla richiesta di scelta. | **Deciso**: se nessuno risponde entro un tempo limite e' un guasto tecnico: si ferma e si riporta, con lo stato conservato (gli agenti persistenti lo permettono). Nelle run non presidiate della campagna (M7) la regola va fissata prima, perche' fa parte della condizione sperimentale. |
| **B6** | **Tetto globale per il task e analisi preventiva del budget.** Un guardiano sulla **somma** dei contabili, in capo all'orchestratore; e la fase che propone budget alternativi in funzione dell'obiettivo. | In parallelo (M3) il limite intrinseco peggiora: N agenti possono leggere «sotto soglia» prima che uno registri la spesa. Mitigazione da valutare: **prenotare** il costo stimato prima di ogni chiamata. Il tetto per agente resta utile: ferma un singolo agente in loop senza aspettare che consumi il budget di tutti. |

**Decisioni prese sulle domande aperte** (5 ottobre 2026):

- **Senza risposta (B5).** Se nessuno risponde entro il tempo limite e' un guasto tecnico: **si
  ferma e si riporta**, conservando lo stato.
- **Opzione «consegna il parziale» (B4).** Nel menu, per ultima, marcata come incompleta,
  mai come scelta predefinita.
- **Livelli di qualita' grossolani all'inizio (B4).** Alta / media / bassa legati alla fascia
  dei modelli; i punteggi numerici arrivano dopo il giudice di M2b. L'interfaccia verso l'utente non cambia fra le due versioni: cambia la precisione.
- **Valuta.** Dollari ovunque nel sistema, come il listino; un tasso di cambio in
  configurazione serve solo a **mostrare** gli euro.

**Dove si realizza** (versione 1 grossolana in M4, versione 2 con dati in M2b, verifica in M7):

| Pezzo | Task |
|---|---|
| tetto globale, monitoraggio sulla proiezione, negoziazione, livelli grossolani, valuta (B3, B4, B5, B6) | **M4.2c** |
| stima del costo da dati, routing sotto vincolo, punteggi numerici, analisi preventiva del budget (B1, B2, B4, B6) | **M2b.7** |
| scansione del tetto per la curva di Pareto, regola per le run non presidiate della campagna | **M7.3b** |

---

# FASE M2a — Infrastruttura di misura ✅

**Obiettivo:** ogni chiamata LLM produce numeri (token, €); ogni task produce un log
strutturato e un report; nessun task può spendere oltre il tetto.
**Prerequisiti:** nessuno. Si parte da M1 così com'è.
**Sezione di tesi che alimenta:** capitolo "Contabilità dei costi e osservabilità".

> **Ordine di lavoro (deciso ago 2026 — "opzione 2"):** prima si costruisce il package
> `accounting` **completamente scollegato** da `agent.py` (registro → contabile,
> ciascuno testato in isolamento), poi si fa l'aggancio in un unico passo. Le prime
> due unità nascono con responsabilità singola e basso accoppiamento, e `agent.py`
> viene modificato **una sola volta**; da lì in poi il contabile è sostituibile senza
> toccare più l'agente (stesso schema di `Tool` / `CommandExecutor`).
>
> **Decisioni di design già prese** (dettagli in `PIANO_completo.md` §3.11, D10):
> package `accounting`; ABC `Accountant` + implementazione concreta; `ModelRegistry`
> **iniettato** nel contabile; metodo `register`; struttura dati propria (non l'oggetto
> dell'SDK OpenAI) con campo `label`; denaro in `float`; il dettaglio per chiamata vive
> nell'implementazione concreta, non nell'ABC. **Contabilità a quantità + unità**
> (token, immagine, secondo, credito, carattere, minuto) → `costo = Σ quantità ×
> prezzo_unitario`, con tutto convergente in $.
>
> ⚠️ **Due trappole di correttezza da rispettare nella formula:** i `reasoning_tokens`
> sono già inclusi in `completion_tokens` e i `cached_input_tokens` in `prompt_tokens`
> — vanno **registrati per analisi ma mai sommati** al costo, pena il doppio conteggio.
> I token da cache, se il registro ne dichiara la tariffa, vanno scorporati e pagati
> a prezzo ridotto.

### Task M2a.1 — Registro modelli, capacità e prezzi (configurazione) ✅
- **Passi:** creare `modelli.toml` (TOML: leggibile con `tomllib`, stdlib, ammette
  commenti). Per ogni modello: **capacità** offerte (C1-C12 di §3.11), e i prezzi
  **per unità** (es. `token_input`, `token_output`, `token_input_cached`, `immagine`,
  `secondo`, `credito`, `carattere`, `minuto`) — solo quelle pertinenti. Nel package
  `accounting`, `ModelRegistry` lo carica e valida. Separare i due momenti: **alla
  lettura** si validano i campi (prezzo mancante o negativo → errore); **al lookup**
  la richiesta di un modello (o di un'unità) non presente → errore chiaro.
- **Costi di accesso (D12):** il registro prevede anche un campo per i **costi fissi**
  (abbonamenti, quote d'ingresso) di ciascun fornitore. Non entra nella formula del
  costo per chiamata — resta marginale — ma va conservato per la tabella "costi di
  accesso" del capitolo sperimentale.
- **Pool iniziale** (verificato ago 2026; i prezzi sono $/milione di token salvo dove
  indicato):

  | Modello | Input | Output | Ruolo |
  |---|---:|---:|---|
  | Claude Opus 5 | $5.00 | $25.00 | frontier — planner, escalation |
  | Kimi K3 | $3.00 | $15.00 | mid (cache −90%: $0.30) |
  | MiniMax M2.7 | $0.24 | $0.96 | cheap — SWE-Pro 56.2% |
  | text-embedding-3-small | $0.02 | — | infrastruttura del router |

  Spread ~21× input / ~26× output. ⚠️ **Qwen3.7 Flash è stato scartato**: pur costando
  $0.03/$0.13, è un modello *vision* (coding #180, punteggio 40/100, nessun benchmark
  pubblicato dal produttore) — inadatto a una tesi su agenti di programmazione. Un
  modello economico che fallisce costa più di uno mediocre che completa, perché paghi
  tutte le iterazioni sprecate più l'escalation.
  Gradino ultra-economico opzionale: **Amazon Nova Lite** ($0.06/$0.24), tracciato per
  coding. Fascia media da infittire più avanti: **DeepSeek-V4** ($0.14/$0.28).
- **Capacità non testuali** (si aggiungono al TOML quando servono, non ora):
  immagini → Flux Schnell $0.003/img → Imagen 4 Fast $0.02 → Flux 2 Pro $0.055;
  video → Veo 3.1 Lite $0.03/s → Kling 3.0 $0.09-0.14 → Veo 3.1 Standard $0.75
  (unico con audio nativo); vision input → Gemini 3 Flash $0.50/$3;
  **3D → Tripo in pay-as-you-go** (~$0.01/credito, 20-30 crediti per modello completo
  ≈ $0.20-0.30; 300 crediti gratuiti per la misurazione iniziale). Meshy scartato per
  D12 (API solo su abbonamento).
- **[SCELTA TUA]:** confermare o modificare il pool; verificare i prezzi al momento di
  scrivere il TOML (cambiano in fretta: Gemini 3.6 Flash è uscito il 21 luglio al
  triplo del 3 Flash) e verificare quale canale li espone tutti (probabilmente
  OpenRouter).
- **⚠️ Da verificare sul campo prima di fissare i prezzi a unità non-token:** le API di
  Tripo (e in generale dei servizi a crediti) riportano i **crediti effettivamente
  consumati** nella risposta? Se sì si registra il valore reale chiamata per chiamata e
  la varianza dichiarata (10-30 crediti) cessa di essere un problema: si misura invece
  di stimare, coerentemente col resto del progetto.
- **Test:** file valido → prezzi giusti per unità; lookup di modello o unità non
  presente → eccezione parlante; file malformato o prezzo negativo → eccezione alla
  lettura. Usare file temporanei (`tmp_path`).
- **Fatto quando:** cambiare un prezzo, aggiungere un modello o una capacità NON
  richiede di toccare codice Python (criterio D9). Nessuna modifica ad `agent.py`.

### Task M2a.2 — Contabile dei costi ✅
- **Passi:** nel package `accounting`: struttura dati del record di consumo
  (quantità + unità + metadati), **ABC `Accountant`** (dichiara `register(...)` e i
  totali) e implementazione concreta in memoria (aggiunge il dettaglio per chiamata).
  Il `ModelRegistry` arriva **per iniezione**, non creato all'interno.
- **Campi del record** (tutti gratuiti, nessun costo aggiuntivo): modello, quantità
  per unità, `cached_input_tokens` e `reasoning_tokens` (solo per analisi, vedi
  trappole sopra), `finish_reason` (`length` = risposta troncata → segnale di qualità
  gratuito, utile in cascade), `n_tool_calls`, `latency_s`, `attempt`, `timestamp`,
  `label`. Esposti: costo totale, token totali in/out, numero di chiamate, dettaglio.
- **Test:** costo calcolato a mano nel test (es. 100 tok in × prezzo + 50 tok out ×
  prezzo) → deve coincidere; più registrazioni si sommano; unità non-token (es. una
  immagine) contabilizzata correttamente e sommata in $; reasoning/cached **non**
  raddoppiano il costo; modello non a registro → errore. Registro finto con prezzi
  tondi, nessuna lettura di file.
- **Fatto quando:** il contabile è corretto e testato **senza che `agent.py` sappia
  che esiste**.
- **Nota tesi:** poiché il log conserva le **quantità grezze**, i costi sono sempre
  **ricalcolabili** se cambiano i listini o migliora la formula — proprietà da
  dichiarare come scelta metodologica (robustezza della campagna ai cambi di prezzo).

### Task M2a.3 — Aggancio alla frontiera LLM ✅
- **Problema risolto:** `agent.py:_chiama_llm` scartava `risposta.usage`; inoltre
  registrare il record nell'agent avrebbe mescolato ciclo ReAct, SDK e accounting.
- **Implementato:** `Agent` dipende dal protocollo `ChatGateway`; `OpenAIChatGateway`
  esegue la chiamata remota, misura la latenza, passa la risposta completa al mapper e
  registra il `UsageRecord`. `Agent` riceve soltanto il messaggio per il ciclo ReAct.
  Il retry protegge solo la rete: un errore di mapper/listino non ripete una risposta
  potenzialmente gia' fatturata.
- **Correttezza:** cache scorporata dall'input, reasoning solo analitico e `usage`
  mancante esplicitamente non prezzabile (`UnpricedUsage`), mai trasformato in $0.
- **Test:** gateway, mapper chat/Responses/immagini/video e ciclo Agent sono coperti
  con fixture senza rete. Suite verde.
- **Fatto:** accounting live sul percorso chat; i mapper non testuali sono preparatori,
  ma non attivano ancora tool o endpoint (vedi M4.0 e M4.6).

### Task M2a.4 — Ledger strutturato per run ✅
- **Passi:** introdurre un `RunContext` (`run_id`, task id/hash, agente/ruolo,
  timestamp start/end, stato terminale, schema version) e un writer append-only. Ogni
  `UsageRecord` prezzato diventa una riga in `runs/<run_id>/usage.jsonl`; errori di
  provider, usage non prezzabile, stop per budget/loop/max-iter diventano eventi
  separati, non falsi record di costo.
- **Riepilogo:** a fine run scrivere `summary.json`: esito, durata, iterazioni,
  costo totale, chiamate, quantità e costo per modello/operazione, record non
  prezzabili e motivo di terminazione. La somma del summary deve derivare dal ledger,
  non da un secondo contatore indipendente.
- **Sicurezza/riproducibilità:** directory creata in modo deterministico e scrittura
  atomica; log di sviluppo in `.gitignore`, artefatti M7 archiviati/versionati. Mai
  API key o prompt completi per default; usare hash/redazione o una politica esplicita.
- **Test:** dopo un run finto: directory e file esistono, JSONL valido, `run_id`
  coerente, nessun segreto, somma delle righe prezzate = summary, evento `unpriced`
  non incrementa il costo.
- **Fatto quando:** ogni esecuzione lascia una traccia completa, persistente e
  ri-analizzabile: questo e' lo schema iniziale del dataset del flywheel.

### Task M2a.5 — Budget guard ✅
- **Policy decisa:** il budget e' espresso in **USD**, mai in numero di passi:
  una chiamata Opus/Fable puo' costare molto piu' di una MiniMax. Il tetto duro e'
  un parametro **opzionale della singola run**, non un default globale nel codice o
  nell'ambiente; senza tetto la run non viene limitata. La soglia morbida e' derivata
  automaticamente all'80% del tetto duro. La policy effettiva va scritta nel ledger
  all'avvio, per rendere confrontabili le run.
- **Passi:** riusare il pattern di `alerts.py`/`RilevatoreLoop`: un `GuardianoBudget`
  con soglia morbida e tetto duro sul costo accumulato del task. Il controllo vive
  nel gateway, PRIMA della chiamata LLM: se costo ≥ tetto → stop pulito (evento +
  report); se ≥ soglia morbida → log/evento una sola volta, come il loop detector.
  L'`Agent` non conosce prezzi o listini: riceve solo l'esito terminale
  `budget_exhausted`.
  **Limite intrinseco da capire e documentare:** il costo di una chiamata si conosce
  solo DOPO averla fatta, quindi il controllo pre-chiamata non può impedire che
  l'ultima chiamata sfori il tetto — può solo impedire di farne un'altra. Lo
  sforamento massimo possibile è il costo di una singola chiamata: va scritto nel
  report e dichiarato in tesi (è un vincolo del modello a consumo, non un difetto).
- **Comportamento soft deciso:** non iniettare messaggi nel contesto del modello
  (es. "concludi presto"): altererebbe invisibilmente la politica dell'agente e
  sporcherebbe la baseline sperimentale. Solo log/evento.
- **Test:** fake con costi crescenti → sotto soglia OK; alla soglia scatta AVVISA una
  volta sola; al tetto il task si ferma e il report dice perché.
- **Fatto quando:** nessun task effettua altre chiamate una volta raggiunto il
  tetto; l'eventuale sforamento residuo (≤ costo di una chiamata) è riportato nel
  report.

### Task M2a.6 — Report di fine task ✅
- **Passi:** a fine `run` (qualunque esito: completato, max-iter, loop, budget,
  LLM giù) stampare e loggare: esito, iterazioni, token in/out, costo totale,
  costo per iterazione, durata.
- **Test:** il report compare in tutti gli esiti (parametrizzare il test sugli esiti).
- **Fatto quando:** lanci un task e leggi immediatamente quanto è costato e perché è
  finito.

### Definition of Done — M2a
- [x] Un task d'esempio stampa e salva token in/out e costo, per iterazione e totale.
- [x] Prezzi e modelli si cambiano solo editando `models.toml`.
- [x] Sforare il tetto ferma il task in modo pulito e documentato.
- [x] Tutti i nuovi moduli hanno test; suite e CI verdi; moduli documentati con
      docstring in stile del progetto.
- [x] Sezione di tesi "contabilità e osservabilità" abbozzata → `TESI_master.md` §9.

---

# FASE M2s — Routing statico role-based (stadio S1)

**Obiettivo:** istanziare agenti con modelli diversi in base al ruolo, da tabella di
configurazione, **chiamando ogni fornitore direttamente**. È lo stadio sperimentale S1.
**Prerequisiti:** M2a completa.

> **Il routing ha due dimensioni** (deciso ago 2026). La letteratura modella solo
> *quale modello*, perché assume accesso diretto alle API. Calcolato sul listino del
> progetto, lo **stesso modello** costerebbe **2,25×** a seconda del percorso, se
> l'aggregatore perdesse lo sconto di cache (calcolo su opus-5, mai eseguito;
> ipotesi da verificare in M2s.4). La seconda dimensione — *attraverso quale
> percorso* — è misurabile con i campi `api_provider` / `billing_provider` che
> `UsageRecord` ha già, e non risulta pubblicata da nessuno.

### Task M2s.1 — Ruoli e filtro per capacità nel registro ✅
- `models.toml` mappa anche `ruolo → modello`. **[SCELTA FATTA]:** due ruoli —
  `planner` → `opus-5` (`requires` = reasoning, code) e `worker` → `minimax-m2-7`
  (`requires` = code). Rapporto di prezzo ~21× in input, ~26× in output: è il
  contrasto da cui nasce il numero della tesi. Il `reviewer` si dichiara in M2b,
  quando esiste qualcuno che lo istanzia.
- **Capability-aware (D10/D11):** il filtro per **capacità richieste** precede quello
  sul costo — un modello privo della capacità necessaria non è confrontabile sul
  prezzo, per quanto economico. Esempio: due modelli video con e senza audio nativo
  non sono comparabili al secondo, perché il secondo richiede uno step audio extra
  (costo + latenza).
- **Test:** ruolo noto → modello giusto; ruolo ignoto → errore parlante; richiesta di
  una capacità che nessun modello del pool offre → errore parlante.

### Task M2s.2 — Percorso diretto e gateway per fornitore ✅
È il primo incasso del disegno di M2a: `ChatGateway` è un Protocol, quindi un secondo
gateway entra **senza toccare `Agent`**.

- **Passi, in ordine:**
  1. `requirements.txt`: SDK `anthropic` accanto a `openai`.
  2. `models.toml`: `[providers.*]` guadagna `api_key_env` (il **nome** della
     variabile, mai il valore) e `base_url`. I segreti restano nel `.env`.
  3. `config.py`: credenziali risolte **per fornitore**, non più una coppia globale.
  4. `llm_contracts.py`: rendere **esplicito** il contratto gateway→agente. Oggi
     `Agent` dipende in modo implicito dalla forma del messaggio OpenAI
     (`msg.tool_calls[i].function.name`); Anthropic usa blocchi `tool_use`. Il
     secondo fornitore costringe a formalizzare ciò che era implicito.
  5. `accounting/mappers/anthropic.py`: mapper nuovo.
  6. `AnthropicChatGateway` con `cache_control` sul prefisso stabile.
- ⚠️ **Trappola all'opposto di quella di M2a.** In OpenAI `prompt_tokens` **include**
  i token da cache e vanno scorporati. In Anthropic `input_tokens` sono **già solo**
  quelli non in cache, e `cache_read_input_tokens` / `cache_creation_input_tokens`
  sono voci separate. Copiare la logica di scorporo dal mapper OpenAI **sottrae due
  volte e sottostima il costo**.
- **Test:** risposta finta Anthropic → record con le tre voci corrette e nessuna
  sottrazione; stesso task sui due gateway → esiti equivalenti per l'agente.
- **Fatto quando:** lo stesso ruolo gira su due fornitori diversi cambiando solo
  configurazione, e la cache compare nei `quantities`.

### Task M2s.3 — Fabbrica di agenti ✅
- Una funzione/classe che, dato un ruolo, costruisce un `Agent` col modello dal
  registro, **il gateway del suo fornitore**, il SUO contabile, il SUO ledger, il SUO
  workspace e il SUO budget.
- Il workspace per agente non è un dettaglio: è la decisione che in M3 evita il
  problema della corruzione. Deciderlo qui costa una riga, deciderlo lì costa un bug.
- **Decisioni prese:**
  - `build(ruolo)` restituisce una **piccola struttura** (`BuiltAgent`) con agente,
    contabile e ledger, non il solo agente: il contabile viaggia con il suo agente, e in
    M3 sommare i costi della squadra diventa un ciclo sulle strutture invece di una
    ricerca nella fabbrica.
  - **L'agente è persistente** (ottobre 2026): ha la propria finestra di contesto, che
    cresce incarico dopo incarico, e vive finché chi lo ha creato — in futuro
    l'orchestratore — non lo elimina con `dismiss()`. `Agent.run` non riparte più da zero:
    la conversazione si accoda (`Agent.messages`). `build(ruolo)` non riceve più il task.
  - **Ledger per incarico**, contabile per vita: ogni task assegnato (`BuiltAgent.assign`)
    è una run completa con il proprio ledger e il proprio `summary.json` (stesso
    `agent_id` in tutti); il contabile è uno per agente e somma tutta la sua vita.
    Motivi: il costo per task è già nel summary (serve a CPT-τ, M7.4b), un incarico è una
    riga del dataset del router (M2b.3), e un incarico concluso ha il suo riepilogo anche
    se il programma si interrompe dopo. `RunLedger` è rimasto invariato; `LedgerAccountant`
    ha guadagnato `attach(ledger)`.
  - **Il tetto di spesa è per agente e vale per tutta la sua vita** (un contabile, un
    guardiano). Il guardiano ha uno stato — l'avviso morbido va emesso una volta sola —
    quindi non si condivide fra agenti. Un tetto per l'intero task non esiste ancora:
    vedi «Problemi aperti sul controllo del costo».
  - **Mappa esplicita provider → classe di gateway** (`anthropic` → gateway Anthropic;
    `openai`, `moonshot`, `minimax` → gateway chat.completions, con `base_url` diverso).
    Un provider non mappato (es. `tripo`) è un errore parlante, mai un default silenzioso.
  - **`api_model`** ✅ già fatto: campo facoltativo in `models.toml` con il nome che il
    fornitore usa per il modello; `ModelRegistry.api_model_for()` lo restituisce, il
    gateway lo invia, record e ledger restano sulla chiave del progetto. Dichiarato solo
    per `opus-5` (`claude-opus-5`) e `minimax-m2-7` (`MiniMax-M2.7`), entrambi letti sulla
    documentazione del fornitore; `kimi-k3` coincide con la chiave e lo si omette.
  - **Fatto:** `agent_factory.py` (`AgentFactory.build(ruolo)` → `BuiltAgent` con `assign`
    e `dismiss`), mappa `BACKEND_PER_PROVIDER`, test in `tests/test_agent_factory.py`.
    `dismiss()` restituisce per ora solo un riepilogo minimo della vita dell'agente: le
    regole di chiusura e il fascicolo da lasciare sono in M4.2b. **`main.py` la usa** (ottobre 2026): `python main.py --role <ruolo>` costruisce l'agente col
    modello e il fornitore del ruolo. `--via-proxy` conserva il percorso vecchio (endpoint
    unico in `.env`) **fino a M2s.4**, perché la prima misura confronta lo stesso modello nei
    due percorsi; dopo quella misura il ramo si toglie. Con `--via-proxy --role X` il modello
    inviato al proxy è quello del ruolo, così il confronto è a parità di modello.
- **Test:** due ruoli → due agenti con modelli e fornitori diversi; i costi finiscono
  su contabili separati; i workspace non si sovrappongono.

### Task M2s.4 — Prima misura reale ⬜
Tre numeri, tutti dal confronto di `summary.json`. È la prima micro-misura del
progetto (richiede proxy/API attivi e Docker acceso).

| Misura | Come | Perché serve |
|---|---|---|
| **Tassa dell'aggregatore** | stesso task, stesso modello, due percorsi | non risulta pubblicata da nessuno |
| **Tasso di fallimento `f`** | N task con `opus-5` e con `minimax-m2-7`, conta gli `status: completed` | determina dove cade l'ottimo di decomposizione in M4 |
| **Quota di output** | `quantities_by_unit` con cache attiva | se supera il 50%, la strategia di ottimizzazione va riorientata dal contesto alla generazione |

- **Fatto quando:** hai i tre numeri e un primo dato da citare in tesi.

**Stato e ordine di lavoro (6 ottobre 2026):**
- **M2s.4a — per primo, via proxy** ⬜: usa le chiavi che ci sono gia' (`ORC2_BASE_URL`,
  `ORC2_API_KEY`). Si parte con una **run di prova** (`python main.py --via-proxy --role
  worker --budget-usd 0.02`, stima circa $0.001): e' il primo giro reale con un fornitore
  vero. Poi il tasso di fallimento `f` e la quota di output sul `worker` (`minimax-m2-7`).
  Vincoli emersi: la **sandbox non ha Python** (ha bash, perl, awk, sed, grep), quindi i task
  devono essere risolvibili con la shell; il proxy espone `minimax-m2-7` ma **non
  `opus-5`** (espone `opus`, forse un altro modello), quindi `opus-5` via proxy richiede un
  alias nella configurazione di LiteLLM.
- **M2s.4b — il resto, dopo** ⬜: richiede **account con credito presso MiniMax e Anthropic**
  (indicativamente $5 ciascuno) e le chiavi `ORC2_MINIMAX_KEY` e `ORC2_ANTHROPIC_KEY` nel
  `.env`. Comprende la **tassa dell'aggregatore** (stesso modello, percorso diretto contro
  proxy), la **prima chiamata reale del gateway Anthropic** (finora provato solo con client
  finti: da verificare `cache_control`, `output_config` e `api_model`), la conferma del nome
  `MiniMax-M2.7` e dei campi di usage, e `f` su `opus-5`. Ogni lancio col preventivo in
  dollari mostrato prima.
- Per chiudere la **Definition of Done di M2s** servono entrambe: senza la 4b restano aperte
  le caselle sul fornitore e sulla tassa.

**Da fare, emerso dal controllo dei log di `runs/` (ottobre 2026):**
- [ ] **Misurare il costo addebitato, non solo quello calcolato.** Il ledger prezza i
  token dichiarati sul listino di `models.toml`, quindi il confronto fra `summary.json`
  dei due percorsi dice se la cache compare nei token, **non** se lo sconto e' applicato
  in fattura. Per la tassa dell'aggregatore serve registrare anche il costo che
  OpenRouter riporta per ogni richiesta (o la fattura) e confrontarlo con quello
  calcolato. Prima di costruire l'esperimento, quantificare in dollari il preventivo.
- [x] **Sistemare la presentazione delle due run di `docs/esempio_run/`** (testo corretto il 6 ott; resta aperta la causa della riproduzione). Sono
  descritte come «esecuzioni reali» e «non esempi costruiti», ma le risposte del
  modello sono riprodotte da una registrazione (stessi `request_id` della run
  `fd9ea9c2` del 24/08, latenze di 10-20 ms contro 1,4-6,2 s). Da correggere in
  `README.md` (sezione sui risultati), in questa ROADMAP (regola sul tetto di spesa) e
  in `docs/esempio_run/README.md`. Per la spiegazione serve ritrovare che cosa
  abbia prodotto la riproduzione: nel codice attuale non c'e'.
- [ ] **Capire perche' la run dell'1 settembre ha zero token in cache.** Stesso
  percorso e stesso modello della run 24255293, che li ha. Va ripetuta in condizioni
  controllate (stesso prompt, chiamate ravvicinate) prima di scrivere qualunque
  conclusione sulla cache via aggregatore.

### Definition of Done — M2s
- [x] Cambiare l'assegnazione ruolo→modello non tocca codice (`main.py` interroga i ruoli del registro).
- [ ] Cambiare fornitore per un ruolo non tocca codice.
- [ ] Due agenti con modelli diversi completano task con costi tracciati separati.
- [ ] Tassa dell'aggregatore, `f` e quota di output misurati e annotati.
- [ ] Test e CI verdi.

---

# BACKLOG UX1 — Sessione chat persistente ⬜

**Collocazione:** parte dopo la chiusura di M2s, perche' una sessione a piu' turni ha senso solo con la fabbrica di agenti e la prima misura reale gia' in piedi.

**Obiettivo:** permettere all'utente di inviare piu' messaggi nella stessa sessione
CLI, mantenendo il contesto conversazionale e il workspace, senza perdere
attribuzione, costi o riproducibilita'. Non e' nel percorso critico M2a → M2s → M3 → M4 → M2b → M7.

- **UX1.1 — Contratto di sessione:** introdurre `session_id`, `turn_id` e indice del
  turno. Una sessione contiene molti turni utente; ogni turno avvia una **nuova run
  ReAct** con il proprio `run_id`. Il ledger di turno deve referenziare il
  `session_id`, senza salvare prompt completi per default.
- **UX1.2 — Modalita' interattiva CLI:** flag `--interactive`; ciclo input → run →
  risposta → nuovo input, uscita esplicita con `/exit`. Il normale comando one-shot
  resta invariato e continua a essere preferibile per gli esperimenti.
- **UX1.3 — Contesto e budget:** mantenere in memoria solo la storia della sessione
  attiva; definire una policy esplicita di compattazione quando il contesto cresce e
  registrarla come evento. **[SCELTA TUA]:** budget complessivo di sessione, budget
  per turno o entrambi; nessuna politica implicita.
- **UX1.4 — Osservabilita':** ledger/summary della sessione con costo aggregato,
  numero di turni e riferimenti ai singoli `run_id`; report di chiusura della
  sessione distinto dal report di turno.
- **Test:** follow-up vede il contesto precedente; `/exit` non invoca l'LLM; due
  turni hanno `run_id` diversi ma lo stesso `session_id`; somme dei ledger di turno
  coincidono col totale di sessione; compattazione e budget non perdono attribuzione.
- **Fatto quando:** una conversazione a piu' turni e' usabile da terminale e ogni
  costo/risposta resta correlabile a sessione, turno e run.

---

# FASE M3 — Parallelismo

**Obiettivo:** N agenti concorrenti senza corruzione, con costi aggregati.
**Prerequisiti:** M2s.

### Task principali (da dettagliare a inizio fase)
- **M3.1** ⬜ Esecuzione concorrente di N agenti su **workspace separati**.
  **[SCELTA FATTA]:** `concurrent.futures.ThreadPoolExecutor`, non `asyncio`. Il
  lavoro è I/O-bound (attesa su HTTP), quindi il GIL non è un vincolo; `asyncio`
  imporrebbe di riscrivere gateway, tool ed executor Docker per reggere migliaia di
  agenti concorrenti, che non servono. I client sync restano invariati.
- **M3.1b** ⬜ **Rendere sicuro ciò che oggi non lo è.** L'iniezione delle dipendenze
  ha già risolto la parte grossa — `ModelRegistry` è di sola lettura dopo `_valida()`,
  i contabili sono per istanza — ma tre punti restano scoperti:
  - `RunLedger` condiviso: `_usage_sequence += 1` è leggi-modifica-scrivi, non
    atomico, e due append concorrenti sullo stesso file si interlacciano. Serve un
    lock se si vuole un ledger **di task** oltre a quelli di agente.
  - `Workspace` condiviso: due agenti che scrivono la stessa cartella si corrompono.
    Risolto in M2s.3 dando un workspace per agente; qui va verificato sotto carico.
  - Docker: N agenti × il limite di memoria per container. Il pool va limitato.
- **M3.2** ⬜ Aggregazione dei log/costi di più agenti in un riepilogo unico
  (il contabile "di squadra" sopra i contabili individuali).
- **M3.3** ⬜ Primo esperimento su **workspace condiviso**: convenzioni di
  non-collisione (file distinti per agente), verifica che la guardia path e la
  sandbox reggano la concorrenza.
- **Test chiave:** N task in parallelo → nessun file corrotto, somma dei costi
  individuali = costo aggregato, ogni log attribuibile al suo agente.

- **M3.4** ⬜ **Aggiornare il limite del budget guard in tesi.** In sequenziale lo
  sforamento massimo è il costo di *una* chiamata (`TESI_master.md` §9.6). In
  parallelo N agenti possono leggere «sotto soglia» prima che uno qualsiasi registri
  la spesa: **lo sforamento massimo diventa N volte** quel costo. Non è un bug da
  correggere, è un limite che si aggrava e va ri-dichiarato.

### Definition of Done — M3
- [ ] N agenti in parallelo, workspace integri, costi aggregati corretti.
- [ ] Deciso e documentato il meccanismo di concorrenza.
- [ ] Ledger di task protetto da lock; sforamento massimo ri-dichiarato in §9.6.

---

# FASE M4 — Swarm (il cuore)

**Obiettivo:** task multi-file completato end-to-end da Planner + Orchestratore +
Worker su workspace condiviso, con checkpoint L1.
**Prerequisiti:** M3. Fase più lunga: dettagliarla a inizio fase, qui la spina dorsale.

> **A cosa serve davvero lo swarm** (chiarito ago 2026). Non a fare più cose insieme:
> a **rendere possibile il modello economico**. Un task monolitico richiede un modello
> che lo regga per intero, quindi con un agente solo non c'è niente da instradare. La
> decomposizione abbassa la difficoltà di ogni foglia fino al punto in cui il modello
> economico ce la fa: **compra la fattibilità del routing**.
>
> **Il costo è una U in K** (numero di worker), come anticipato in `TESI_master.md`
> §2.3. Decomporre di più abbassa il tasso di fallimento delle foglie ma alza il
> coordinamento — ogni agente ripaga il prompt di sistema e l'orchestratore fa più
> turni di integrazione. Calcolata sul listino del progetto con `f` stimato, la curva
> ha un minimo interno intorno a **K≈4** ($0.0993, −69,5% sul baseline) e risale sia a
> K=2 (foglie troppo grosse, escalation continue) sia a K=12 (coordinamento al 90%).
> **`f` è stimato, non misurato**: lo produce M2s.4, e da lì si ricalcola l'ottimo.
> Corollario da tenere presente: «decomponi il più possibile» è sbagliato quanto «non
> decomporre».

### Task principali
- **M4.0** ⬜ **Infrastruttura capability-to-tool**: `ModelRegistry.capabilities`
  dichiara cosa un modello sa fare, ma non lo rende invocabile. Definire contratti
  separati per `ChatGateway`, gateway generativi e tool; ogni tool restituisce un
  risultato serializzabile piu' un riferimento stabile all'artefatto. Il controller
  testuale resta su `ChatGateway`: immagini/video/audio arrivano come tool call, non
  sostituiscono il suo messaggio ReAct.
  - Test: tool registrato con capability richiesta assente -> errore parlante; tool
    riuscito -> risultato osservabile dal controller e record attribuito alla stessa run.
- **M4.1** ⬜ **Planner**: prompt che produce il piano strutturato (D5: `sotto_task`,
  `dipendenze`, `ruolo`, `visibilita`) + parser + **validatore** (DAG aciclico,
  dipendenze esistenti, ruoli noti) + rigenerazione su piano invalido (max K tentativi).
  - Test: piani finti validi/invalidi → accettati/rifiutati; ciclo nel DAG → rifiuto.
  - **Due uscite, non una** (D15). Oltre alla scomposizione, il planner produce il
    **sistema di stile** — palette, tipografia, spaziature, tono — *prima* che i worker
    partano, e lo scrive nello stato condiviso. La coerenza fra sezioni diventa un
    vincolo di specifica invece di un effetto da sperare: un router addestrato sezione
    per sezione non potrebbe impararla, perche' non la vede. E' la divisione di un team
    di design: art director (planner), designer (worker), revisore (giudice di pagina).
  - **Un planner solo, non due agenti.** Un art director separato aggiungerebbe una
    chiamata al modello forte nel punto gia' piu' caro del sistema, e i due ruoli sono
    accoppiati — il layout cambia la scomposizione e viceversa — quindi dovrebbero
    iterare. Separarli conviene solo se esiste un modello piu' adatto *ed* economico per
    il design: a settembre 2026 nessuna classifica isola quella capacita', e in cima a
    quelle di sviluppo web ci sono solo modelli di fascia alta. Resta un **esperimento**:
    «separare l'art director migliora la pagina abbastanza da pagare la chiamata in piu'?»
- **M4.2** ⬜ **Orchestratore**: scheduling a ondate dal DAG (foglie senza dipendenze
  pendenti = ondata corrente, in parallelo via M3); dispatch ai worker tramite la
  fabbrica (M2s); budget per agente e per task (M2a.5; vedi «Problemi aperti sul
  controllo del costo», B1-B6).
  - Test: DAG di prova → ondate nell'ordine giusto; fallimento di una foglia →
    le dipendenti non partono.
- **M4.2b** ⬜ **Ciclo di vita degli agenti e regole dell'orchestratore** (ottobre 2026).
  Gli agenti sono persistenti (M2s.3): all'orchestratore va lasciata la **libertà di
  decidere quando un agente ha concluso il suo ciclo** e può essere eliminato. Da
  progettare — non sono ancora regole, sono le domande a cui rispondere:
  - **Regole dell'orchestratore**: quando riusare un agente esistente e quando crearne
    uno nuovo per un ruolo; a chi assegnare un incarico; quando eliminare (task finito,
    contesto troppo grande, qualità in calo, budget dell'agente quasi esaurito).
  - **Regole di chiusura**: cosa succede all'agente e al suo workspace quando viene
    eliminato; chi può eliminare (solo l'orchestratore? anche il budget guard?).
  - **La traccia lasciata — «come un dipendente appena andato in pensione»**: alla
    chiusura va conservato un fascicolo da cui recuperare in seguito le informazioni
    cruciali. Da decidere: cosa è «cruciale» (la conversazione intera? le decisioni
    prese? i file prodotti, che stanno nel workspace? un congedo scritto dall'agente
    stesso prima di andarsene, che costa una chiamata in più?); in che formato e dove;
    come lo si interroga (consultazione diretta, oppure caricato nel contesto di un
    agente nuovo). Il nucleo esiste già: `BuiltAgent.dismiss()` restituisce identità,
    numero di incarichi, `run_id` dei ledger e costo totale; i ledger per incarico sono la
    parte quantitativa del fascicolo.
  - **Politica di durata come variabile sperimentale**: quanti incarichi tenere in vita un
    agente (1, N, fino a una soglia di contesto). Ricalcolato (senza cache): tre incarichi
    da 4 iterazioni su un worker persistente costano 50.100 token di input contro 18.900 se
    riparte da zero (2,65×), ma restano circa 20× sotto un solo agente `opus-5`. Va
    misurato anche l'effetto sulla qualità: un agente che ricorda può lavorare meglio o
    peggio.
  - **Compattazione del contesto**: oggi `Agent.messages` cresce senza limiti e prima o
    poi tocca il limite di contesto del modello. Serve una politica, che è lo stesso
    meccanismo del backlog UX1 (UX1.3).
  - Test: un agente riceve N incarichi e li ricorda; l'orchestratore ne elimina uno e un
    incarico successivo viene rifiutato; il fascicolo contiene le run dell'agente.
- **M4.2c** ⬜ **Controllo del costo, versione 1 (livelli grossolani)** (ottobre 2026;
  vedi «Problemi aperti sul controllo del costo»):
  - **Tetto globale del task**: un guardiano sulla **somma** dei contabili, in capo
    all'orchestratore; il tetto per agente resta (B6). Il `BudgetGuard` ha oggi un tetto
    immutabile: va reso possibile **alzarlo** su decisione dell'utente.
  - **Monitoraggio** ai checkpoint di M4.4: spesa contro avanzamento (sezioni completate /
    sezioni del piano). L'innesco scatta sulla **proiezione**, non sulla spesa gia' fatta (B3).
  - **Negoziazione**: interfaccia strutturata verso l'**utente** (B4/B5). Opzioni: sforare (stessa qualita', costo totale maggiore),
    degradare (qualita' ridotta, costo minore) e, per ultima, «consegna il parziale»
    marcata incompleta. Livelli di qualita' **grossolani**; soglia minima coerente con il
    budget iniziale (proporzionalita'). Nessuna risposta entro il tempo limite → guasto
    tecnico: stop e rapporto, stato conservato.
  - **Valuta**: dollari nel sistema, tasso di cambio in `config.py` solo per la
    visualizzazione.
  - Test: proiezione oltre il tetto → richiesta con le opzioni; «sforare» → il tetto sale e
    la run prosegue; «degradare» → modelli piu' economici sulle foglie rimaste; nessuna
    risposta → esito di guasto con stato conservato; l'opzione parziale non viene mai
    scelta da sola.
- **M4.3** ⬜ **Stato condiviso, coda di task e isolamento del contesto**.
  Struttura presa da DeLM e dal consenso industriale 2026, **senza l'auto-candidatura**:
  - **coda di task**: i worker pescano il lavoro, non se lo assegnano da soli. Chi fa
    cosa lo decide il registro (capacità dure) e in M2b il router (competenze morbide).
    L'auto-valutazione è scartata di proposito — è la forma inaffidabile della stessa
    domanda, ed è il bias di auto-preferenza che è già nella lista dei rischi.
  - **contesto isolato**: l'orchestratore non inoltra mai la propria storia; ogni
    worker ha una finestra di contesto **propria e persistente** (decisione di ottobre
    2026, vedi M2s.3 e M4.2b) e restituisce una sola stringa. L'isolamento è quindi fra
    agenti, non più fra incarichi: dentro un agente la storia si accumula. Misurato in
    letteratura: ~9K token contro 15K, e la sintesi al posto dell'inoltro taglia il
    70–90%. ⚠️ I calcoli di risparmio basati su worker che ripartono da zero vanno
    riletti con la durata di vita come variabile.
  - **artifact store**: i worker scrivono su `Workspace` — che esiste già — e
    restituiscono un **riferimento** (~30 token) invece del contenuto.
    ⚠️ Soglia calcolata: i riferimenti convengono solo se l'orchestratore srotola meno
    del **21,6%** degli artefatti; sopra quella soglia i riepiloghi costano meno.
  - a ogni worker passa SOLO il contesto dichiarato in `visibilita` (qui entra la
    "disciplina del contesto", ex-M5).
  - Test: worker con visibilità limitata non riceve contenuti fuori vista; un
    riferimento non srotolato non porta il contenuto nel contesto dell'orchestratore.
- **M4.4** ⬜ **Checkpoint con gate L1** (D4): a fine ondata esegui i segnali gratuiti
  (build, test, lint — nella sandbox); esito ACCEPT → ondata successiva; REVISE →
  ri-delega della foglia con l'osservazione dell'errore (riuso del Pilastro C a scala
  di swarm). **[SCELTA TUA]:** la spaziatura dei checkpoint e il numero max di ri-deleghe.
  - Test: workspace con test rotti → REVISE e ri-delega; con test verdi → ACCEPT.
  - ⚠️ L'immagine della sandbox (`debian:bookworm-slim`) non ha né Python né Node: i segnali
    L1 (build, test, lint) richiedono un'immagine con gli strumenti, da scegliere e validare.
  - **Giudizio a due livelli** (D14), perche' la qualita' e' soggettiva e l'aspetto di
    una pagina e' una proprieta' dell'insieme:
    - **sezione, durante il lavoro** — ogni sotto-task produce una sezione (hero, prezzi,
      testimonianze) che si giudica da sola. Quel giudizio **e'** l'etichetta del
      sotto-task: nessun merito da ripartire fra piu' contributi. Serve ad
      **addestrare** il router.
    - **pagina, a lavoro finito** — la pagina intera contro quella della baseline. Serve
      a **dimostrare** la tesi.
    Le due metriche sono diverse, quindi il router non puo' «imparare il giudice» con cui
    viene valutato: la validazione non e' circolare.
- **M4.5** ⬜ **End-to-end**: un task realistico multi-file (es. mini web-app con
  pagina + stile + validazione) completato dallo swarm con log completo.
  - Questo run è già materiale di tesi (figura + numeri).
- **M4.6** ⬜ **Toolchain multi-capacita' (demo, non prerequisito M7)**: ogni
  capacita' sotto e' "fatta" solo con gateway, mapper usage, modello+prezzi verificati,
  storage dell'output/job e fixture testate. Un mapper isolato non conta come feature.

  | Capacita' | Integrazione richiesta | Caso limite obbligatorio |
  |---|---|---|
  | `vision_input` | input multimodale file/URL nella richiesta chat e contabilita' token input | file non leggibile/URL scaduta non genera consumo fittizio |
  | `image_gen` | `GenerateImageTool` + gateway + storage dell'immagine + safety/error handling | risposta senza usage usa solo una misura derivata dichiarata, mai $0 silenzioso |
  | `video_gen` | tool + submit/poll/retrieve + `job_id` persistito + storage video | `queued`/restart non duplicano il costo; registra solo al terminale `completed` |
  | `model_3d` | tool/gateway e unita' `credit`, con polling se il provider e' asincrono | crediti reali assenti -> evento non prezzabile |
  | `tts` | tool/gateway, file audio persistito, voce/formato nei metadati | output parziale/fallito non appare come asset completo |
  | `stt` | upload/riferimento audio, transcript persistito, durata o usage provider | file troppo grande/errore provider tracciato come evento |
  | `embedding` | servizio RAG: chunking, vector store, upsert/query e accounting | re-indicizzazione e query sono consumi distinti |
  | `rerank` | stadio retrieval query-documenti-risultati con listino e metriche ranking | input vuoto e provider senza usage sono espliciti |

  - Test chiave: per ogni gateway, fake provider -> asset/job/transcript o risultato
    previsto + record corretto; fallimento/retry/restart non creano doppia fatturazione.

- **M4.7** ⬜ **Best-of-N sugli slot soggettivi**: dove la qualità è di gusto (header,
  palette, copy), N worker economici producono N candidati per lo **stesso** slot e il
  giudice ne sceglie uno. È la forma controllata di ciò che la blackboard a
  volontariato otterrebbe per emergenza: decidi tu N e su quali slot, quindi resta
  attribuibile — e costa N chiamate economiche, non N al modello forte.
  - Dipende dal torneo a pivot di M2b.1 per la selezione: O(Nk) invece di O(N²).
  - **[SCELTA TUA]:** su quali slot, e con che N.
- **M4.8** ⬜ **Misurare l'ottimo di decomposizione**: stesso task a K crescente,
  costo totale per K → la curva a U empirica. È una figura di tesi, e valida (o
  smentisce) il calcolo teorico riportato sopra.

### Definition of Done — M4
- [ ] Task multi-file completato end-to-end senza interventi manuali.
- [ ] Log completo: piano, ondate, costi per agente, esiti L1, ri-deleghe.
- [ ] Token di contesto misurati per worker (disciplina del contesto documentata).
- [ ] Curva costo-vs-K tracciata su dati reali, con l'ottimo indicato.
- [ ] Con un tetto assegnato il task si conclude entro il tetto, oppure l'utente ha
      scelto come proseguire (controllo del costo, versione 1).
- [ ] Se viene inclusa la demo multi-capacita', ogni tool usato soddisfa M4.6 e
      conserva gli asset/job necessari a riprodurre la run.

---

# FASE M2b — Intelligenza di routing

**Obiettivo:** cascade funzionante (S2) e router appreso (S3). S3 e' dove sta il
contributo della tesi (D13), non un traguardo facoltativo.
**Prerequisiti:** M4. Da dettagliare a inizio fase; decisione D6 si prende QUI.

- **M2b.0** ⬜ **Gate a due stadi** (prima di tutto il resto, perché filtra a monte):
  1. **deterministico** — compila? i test passano? il lint tace? Costa **zero token**
     e scarta ciò che non ha senso giudicare. È il gate di ammissione di DeLM, ed è lo
     stesso schema del rilevatore di loop di M1: osserva un segnale di progresso e
     reagisci in modo proporzionato, solo che qui il segnale è oggettivo.
  2. **probabilistico** — solo su ciò che è sopravvissuto al primo.
  - Un output che non passa il primo stadio non inquina il contesto degli altri agenti
    **ed è** il segnale che innesca l'escalation: un meccanismo, due lavori.
- **M2b.1** ⬜ **Judge L2 offline**: harness di confronto pairwise (A vs B, ordine
  scambiato, gate hard, aggregazione Bradley-Terry) sui prodotti dello swarm.
  - **Punteggi continui invece di voti interi** (LLM-as-a-Verifier, 2607.05391):
    l'attesa sulla distribuzione dei logit dei token di punteggio elimina i pareggi,
    che sono il difetto pratico dei giudici a scala 1–5.
  - **Torneo a pivot**: ordinare N candidati in **O(Nk)** invece di O(N²). Conta
    perché ogni confronto è una chiamata a pagamento — è il problema O(N²) applicato
    al giudizio, dove morde più che nella comunicazione.
  - **[SCELTA TUA]:** il modello giudice. Va scelto su tre assi insieme — accordo coi
    tuoi giudizi umani (kappa), costo per punteggio, e bias di auto-preferenza verso i
    modelli candidati. Un giudice che è anche produttore va escluso su quello slot.
  - ⚠️ **Il giudice va verificato prima di usarlo.** Il Visual Aesthetic Benchmark
    (2605.12684, maggio 2026) mostra che i modelli di punta **usati cosi' come sono**
    restano lontani dagli esperti nel giudizio estetico: 26,5% contro 68,9%. Il dominio e'
    arte e fotografia, non interfacce, e la misura e' severa (indovinare migliore *e*
    peggiore in tre ordini diversi) — ma la direzione e' chiara: non basta chiedere a un
    modello forte «quale e' piu' bello?». La stessa ricerca mostra pero' che addestrare un
    modello piu' piccolo sui giudizi degli esperti lo avvicina a uno dieci volte piu'
    grande: il segnale estetico **si insegna**. E' il Layer 1 di `TESI_master.md` §5.5.
  - **Procedura:** poche centinaia di giudizi umani (due annotatori sulle stesse coppie)
    → kappa fra gli umani → accordo fra giudice e umani → solo se si avvicina al kappa
    umano il giudice si usa sul resto. Criteri **espliciti** invece della domanda
    generica: la vaghezza abbassa l'accordo sia per il modello sia per gli umani
    (problema aperto 1).
  - **Candidato economico: Jev** (TypeSafe AI, accesso anticipato dal 15 settembre 2026).
    Non genera testo: restituisce un valore tipizzato con una confidenza (`A · 0.87`).
    Input a $0.042 per milione, output gratuito. Come *worker* e' inutile (non scrive
    codice); come *router* non conviene (l'embedding previsto costa gia' $0.02 per
    milione); come *giudice* si', perche' li' il concorrente e' un modello frontier: un
    confronto costa $0.000084 contro $0.015, circa **180 volte** meno. **Da verificare**
    che sappia giudicare l'estetica e che legga immagini: nessuno dei due e' documentato.
- **M2b.2** ⬜ **Cascade (S2)**: politica di escalation — foglia che fallisce L1
  (o REVISE ripetuto) → riassegnata a modello superiore; log dell'escalation
  (quale modello ce l'ha fatta, a che costo). **[SCELTA TUA]:** la scala di escalation.
- **M2b.3** ⬜ **Dataset dal flywheel**: estrazione dai log di coppie
  (caratteristiche sotto-task → modello minimo sufficiente, costo, qualità).
  - ⚠️ **Nel soggettivo il dataset non e' un sottoprodotto gratuito della cascade.** Per
    il codice deterministico la cascade etichetta da sola: i test passano, quindi il
    modello economico e' bastato. Per l'estetica il gate deterministico da' solo un
    *pavimento* — una sezione puo' compilare ed essere brutta. Etichettare «il modello
    economico e' bastato» richiede di **generare anche la versione di confronto** e di
    farle giudicare.
  - **La baseline e' il metro** (problema aperto 4). Bradley-Terry da' un punteggio
    relativo, senza zero assoluto: «qualita' ≥ τ» ha senso solo rispetto a un
    riferimento, e l'unico disponibile e' la baseline. Quindi ogni etichetta richiede la
    baseline eseguita su quello stesso sotto-task.
  - **Costo per etichetta**, calcolato sul listino (sotto-task da 5 iterazioni):

    | | costo |
    |---|---|
    | deterministica — cascade con 35% di escalation | $0.0225 |
    | **soggettiva** — modello economico + baseline + un giudizio economico | **$0.0587** |

    Le etichette soggettive sono anche **rumorose**: servono all'incirca il triplo degli
    esempi per la stessa accuratezza, e c'e' un soffitto — il router non puo' superare
    l'accordo fra gli umani.
  - **L'unita' e' il sotto-task, non il sito**: un sito da 6 sezioni produce 6 etichette.
  - **Quante etichette: non si indovina, si misura.** Curva di apprendimento: si addestra
    con un primo lotto, si misura l'accuratezza su dati tenuti fuori, si aggiunge, si
    riaddestra; ci si ferma quando la curva si appiattisce. E' incrementale — si puo'
    interrompere in qualunque momento senza aver sprecato nulla — ed e' una **figura di
    tesi**: risponde a «quanti dati servono per un router utile?», che nessuno dei lavori
    censiti riporta.
  - **Apprendimento attivo:** dopo il primo lotto, i nuovi esempi si generano sui
    sotto-task dove il router e' **meno sicuro**, invece che uniformemente. Riduce
    tipicamente il fabbisogno di etichette di 2-5 volte: i soldi vanno dove c'e'
    incertezza.
- **M2b.4** ⬜ **Router appreso (S3)** — il contributo della tesi (D13): decisione
  D6 (default: testa leggera su embedding); training con subset del pool (D9);
  confronto contro S1/S2 su task tenuti fuori.
- **M2b.5** ⬜ **Competenze morbide apprese** — capacità a due livelli:

  | | domanda | dove vive |
  |---|---|---|
  | **dure**, binarie | *può* farlo? vision, image_gen, video_gen | `models.toml`, scritte a mano, verificate al caricamento — **già fatto in M2s.1** |
  | **morbide**, graduate | *quanto bene* lo fa in quella categoria? | tabella appresa, scritta dal flywheel, letta dal router |

  La premessa è che la preferenza soggettiva ha **struttura a livello di popolazione**
  — non è rumore individuale — che è la stessa assunzione su cui poggia Bradley-Terry
  (§5.6) e il motivo per cui RLHF funziona.
  ⚠️ La tabella morbida **non va scritta a mano**, o è un'opinione hardcoded travestita
  da configurazione. Va misurata, e va tenuta separata dal listino per la stessa
  ragione per cui listino e politica sono separati: uno è un fatto, l'altra una stima.
  ⚠️ **Leggere FlyRoute (2605.22057) prima di rivendicare novità**: fa profiling di
  agenti auto-evolvente via flywheel, ed è il prior più vicino. Il delta difendibile
  non è il meccanismo — è applicarlo a **categorie estetiche soggettive** invece che
  alla correttezza verificabile.
- **M2b.6** ⬜ **Riuso dei piani fra task simili** (agentic plan caching, 2506.14852).
  Non è una micro-ottimizzazione: nel sistema ottimizzato **l'orchestratore è l'87%
  della spesa** (calcolo in `docs/`, artefatto «Le leve di costo»), quindi
  qualunque leva sul planner domina tutte le altre. Limite dichiarato: dipende dalla
  somiglianza fra i task — che su una campagna con task volutamente omogenei è alta
  per costruzione.

- **M2b.7** ⬜ **Controllo del costo, versione 2 (stime e punteggi)** — la parte che richiede
  dati (ottobre 2026):
  - **Stima del costo per sotto-task** dal ledger, con riserva per l'incertezza (B1).
  - **Routing sotto vincolo**: dato B, scelta di modelli, numero di candidati ed escalation
    (B2). Dipende dal router (S3) e dalle competenze morbide (M2b.5).
  - **Livelli di qualita' numerici**: i livelli grossolani di M4.2c diventano punteggi
    stimati dal giudice; stessa interfaccia verso l'utente, piu' precisa.
  - **Analisi preventiva del budget** (B6): dato il compito e l'obiettivo (qualita' o
    prezzo), proposta di budget alternativi con la qualita' attesa di ciascuno; il suo costo
    conta nel tetto.
  - Test: la stima si confronta con il costo reale su task tenuti fuori; con tetto stretto il
    routing sceglie configurazioni piu' economiche e il costo finale resta nel tetto.

### Definition of Done — M2b
- [ ] Escalation osservabile nei log con delta di costo quantificato (S2).
- [ ] Gate deterministico a monte del giudice, con costo in token pari a zero.
- [ ] Giudice verificato contro almeno due annotatori umani: kappa umano e accordo
      giudice-umani dichiarati.
- [ ] Dataset estratto e descritto, con la curva di apprendimento.
- [ ] Router appreso (S3) confrontato con S1 e S2 su task tenuti fuori.
- [ ] Stima del costo per sotto-task e routing sotto vincolo validati (controllo del costo,
      versione 2).

---

# FASE M7 — Campagna sperimentale

**Obiettivo:** i numeri della tesi. Da dettagliare a inizio fase.

> **Preventivo** (settembre 2026, calcolato sul listino — va rifatto coi costi misurati
> in M2s.4). 30 task × 3 ripetizioni × 3 condizioni = 270 run:
>
> | voce | costo |
> |---|---|
> | esecuzione del sistema (S0 + S1 + S2) | ~$24 |
> | stessa esecuzione con Batch API | ~$12 |
> | giudice progettato male — frontier, 4 candidati per slot | +$21.60 |
> | giudice progettato bene — economico, 2 candidati per slot | +$0.14 |
>
> Il fattore 150 fra le ultime due righe dipende solo da due scelte di progetto: quanti
> candidati si confrontano e quale modello giudica. **La voce da tenere sotto controllo
> e' il giudizio, non la generazione.** Il dataset per S3 e' a parte: vedi M2b.3.

- **M7.1** ⬜ **Set di task**: 3 categorie (frontend, backend/logica, refactor),
  pochi task curati e ripetibili, criteri L1 definiti *a priori* per ciascuno.
  **[SCELTA TUA]:** i task concreti.
- **M7.2** ⬜ **Campagna S0** (baseline mono-modello = M1 col modello top).
- **M7.2b** ⬜ **Batch API per la campagna.** Anthropic, OpenAI e Google offrono una
  corsia asincrona al **50%** con SLA 24h, e si somma alla cache.
  ⚠️ **Non riduce il costo del sistema**: dentro un ciclo ReAct il turno `t+1` dipende
  da `t`, quindi non è batchabile. Riduce il costo di **eseguire l'esperimento**, dove
  le run sono indipendenti. Il valore non è il denaro: **a parità di budget raddoppi
  le ripetizioni**, e le ripetizioni sono ciò che rende significativo un risultato.
- **M7.3** ⬜ **Campagne S1, S2** (e S3 se esiste) — stessi task, stessa sandbox,
  stessi criteri; cambia solo la politica di routing.
- **M7.3b** ⬜ **Scansione del tetto**: stesso task a tetti crescenti → curva qualita'-costo
  (la figura di Pareto percorsa dal parametro B); si misura anche l'**aderenza**, cioe' la
  quota di run concluse entro il tetto. Prima va fissato cosa succede nelle **run non presidiate** della campagna (per default: stop e rapporto), perche' e' parte della condizione sperimentale.
- **M7.4** ⬜ **Analisi** (D8): tabella per condizione (costo, qualità-vettore,
  latenza, completamento autonomo, qualità÷costo) + **grafico di Pareto** con gli
  stadi come punti + test di **non-inferiorità** della qualità.
- **M7.4b** ⬜ **CPT-τ come metrica primaria.**

  ```
  CPT-τ  =  costo totale della campagna  /  task completati con qualità ≥ τ
  ```

  È la funzione obiettivo della tesi scritta come si misura: `min Σ costo s.t.
  qualità ≥ τ` diventa «minimizza CPT-τ». Assorbe in un numero solo quattro cose che
  la letteratura tiene in nota a piè di pagina: i tentativi economici falliti, il
  costo dell'escalation, l'overhead di coordinamento, e i task che a τ non arrivano
  mai. Nessuno dei lavori censiti la riporta — DeLM dà $/task e pass@4 separati,
  GoAgent dà % di token e accuratezza separate, il blackboard non dà costi affatto.
  Tutti i campi necessari sono già in ogni `summary.json` da M2a.
- **M7.5** ⬜ **Calibrazione umana**: piccolo campione di giudizi umani, kappa
  inter-annotatore, dichiarazione del soffitto di validità.
- **M7.6** ⬜ *(opzionale, se esce un modello nuovo durante la tesi)* **Flywheel dal
  vivo**: aggiunta al registro + ri-esecuzione → dimostrazione anti-obsolescenza.

### Definition of Done — M7
- [ ] Tabella e Pareto a 3-4 stadi; non-inferiorità documentata; kappa dichiarato.
- [ ] **CPT-τ riportato per ogni stadio**, decomposto per ruolo, operazione e percorso.
- [ ] Log delle campagne archiviati e versionati.
- [ ] Curva qualita'-costo al variare del tetto e aderenza al tetto riportate.

---

## Promemoria posizionamento (per la scrittura)

La novità difendibile, verificata contro la letteratura (dettagli in
`PIANO_completo.md` §2): (1) cost-routing in uno swarm su artefatto condiviso
(MasRouter dichiara il problema aperto); (2) valutazione **di stato** execution-based
ai checkpoint (nessun vicino la fa); (3) safety/sandbox + budget dove OI-MAS e
Trinity dichiarano i propri limiti.

**Aggiunte dopo la rassegna di agosto 2026** — tre rivendicazioni nuove, tutte
misurabili con l'infrastruttura che esiste già:
- **(4) Il routing ha due dimensioni.** Quale modello *e attraverso quale percorso*.
  Calcolato, da misurare in M2s.4: 2,25× di differenza sullo stesso modello (ipotesi
  che l'aggregatore perda lo sconto di cache). La letteratura assume accesso
  diretto alle API e non modella la seconda.
- **(5) Token ≠ dollari.** Dove la cache è attiva le due metriche divergono di un
  ordine di grandezza: il −17% di token di GoAgent vale −2,5% di spesa. È il divario
  esattamente nel punto in cui la letteratura misura.
- **(6) CPT-τ.** Costo e qualità come **un solo numero** vincolato, invece di due
  numeri accostati.

⚠️ Nessuna delle tre è ancora verificata contro tutta la letteratura: sono candidate,
non risultati. Prima di rivendicarle vanno letti per intero DeLM e FlyRoute.

**Aggiunta di settembre 2026:**
- **(7) Il vincolo e' il giudizio, non la generazione.** Nel lavoro soggettivo ogni
  etichetta richiede un giudizio, e un giudizio frontier puo' costare piu' del lavoro che
  giudica. La regola di fondo della tesi — mandare ogni compito al modello piu' economico
  capace di svolgerlo — va applicata **al giudice stesso**. La forza della tesi sta nei **numeri**: ogni
fase di questa roadmap esiste per produrne.
