# Router pronti, Switchyard e ottimizzazione di OrcV2

**Dossier tecnico e metodologico per la revisione della tesi**  
**Data di riferimento: 22 ottobre 2026**

Questo documento raccoglie in un unico file l'analisi di Switchyard, Conduit e NadirClaw, i router con pesi già addestrati, i servizi di routing via API e le conseguenze per il progetto OrcV2. È materiale di studio e di proposta: non sostituisce il protocollo vigente, non ratifica nuove decisioni e non dichiara implementata un'integrazione.

I collegamenti ai sorgenti esterni sono, quando possibile, fissati a un commit: un identificativo immutabile della versione letta. Le pagine dei servizi ospitati, i prezzi, i modelli e le condizioni di accesso possono cambiare. Le affermazioni sulle API indicano disponibilità documentata, non accesso già provato con un account o qualità già misurata sui siti di OrcV2.

I collegamenti ai file locali puntano al checkout osservato. Per trasferire il documento su un'altra macchina si usano anche le etichette `percorso/dal/progetto:riga`; i numeri di riga descrivono lo stato letto e possono spostarsi con modifiche successive. Non sostituiscono le fonti pubbliche fissate a versione.

## Indice

- [1. Come leggere il dossier e quali conclusioni sono già solide](#sezione-1)
- [2. Contesto OrcV2: che cosa va preservato](#sezione-2)
- [3. Tassonomia: cosa significa davvero router pronto](#sezione-3)
- [4. Mappa comparativa delle alternative](#sezione-4)
- [5. Switchyard: analisi completa della libreria e del servizio](#sezione-5)
- [6. Conduit: apprendimento, feedback e limiti del riuso](#sezione-6)
- [7. NadirClaw: servizio standard, librerie e numeri di ricerca](#sezione-7)
- [8. Router preaddestrati e servizi API: catalogo approfondito](#sezione-8)
- [9. Integrazione in OrcV2: tre strade concrete e i loro contratti](#sezione-9)
- [10. Economia: quali costi possono annullare il risparmio](#sezione-10)
- [11. Esperimenti che distinguono le spiegazioni del risparmio](#sezione-11)
- [12. Conseguenze per la revisione della tesi](#sezione-12)
- [13. Priorità proposte, dipendenze e questioni aperte](#sezione-13)
- [14. Glossario essenziale per la rilettura](#sezione-14)
- [15. Indicazioni per una successiva revisione del progetto](#sezione-15)
- [16. Fonti principali e verifica del documento](#sezione-16)

<a id="sezione-1"></a>
## 1. Come leggere il dossier e quali conclusioni sono già solide

### 1.1 Risposta pratica

**Esistono router già pronti e router già addestrati integrabili in OrcV2. Non è necessario addestrare da zero un selettore per cominciare a sperimentare.** Le tre strade principali sono:

1. **Servizio ospitato:** inviare le richieste a un router già operativo, come Switchyard su OpenRouter; il servizio instrada ed esegue le chiamate.
2. **Selettore via API:** chiedere quale modello usare a un servizio come Not Diamond e far eseguire la chiamata dal proprio gateway, cioè dal componente OrcV2 che già dialoga con il fornitore e registra i consumi.
3. **Pesi scaricabili o politica locale:** eseguire un router preaddestrato, come quelli RouteLLM, oppure incorporare una politica deterministica. I pesi sono i parametri appresi dal modello; una politica deterministica usa regole esplicite e non richiede addestramento.

Il fatto che un router sia pronto riduce il lavoro necessario per usarlo. Non stabilisce, da solo, se sia conveniente sul dominio dei siti web, se mantenga la qualità, se riconosca bene i modelli scelti per OrcV2 o se misuri tutte le chiamate che fa.

### 1.2 Risultati principali dell'analisi

| Risultato | Significato per la tesi |
|---|---|
| Switchyard implementa routing durante un lavoro agentico, compreso Plan/Execute | Il solo schema forte che pianifica ed economico che esegue è già un meccanismo disponibile; la domanda di ricerca deve essere più precisa |
| Lo stesso progetto è utilizzabile come libreria o come servizio OpenRouter, con funzioni differenti | Prima di scegliere un'integrazione bisogna stabilire quale variante si vuole misurare |
| Esistono selettori preaddestrati e servizi commerciali | L'alternativa non è limitata a scrivere o addestrare un router nuovo |
| Conduit contiene algoritmi di apprendimento, ma non un verificatore affidabile dei siti | Il feedback di qualità resta un problema del banco di prova, anche usando una libreria esistente |
| NadirClaw distingue componenti di ricerca, prodotto e verificatori differenti | I numeri di una configurazione non si trasferiscono automaticamente al percorso standard del servizio |
| I risparmi pubblicati spesso comportano qualità diversa, prezzi ricalcolati o condizioni specifiche | Una percentuale di risparmio non dimostra la non inferiorità richiesta da OrcV2 |
| Un proxy può fare più chiamate di quelle visibili nella risposta finale | La contabilità deve comprendere classificatori, consiglieri, risposte scartate, ripetizioni ed errori con consumo |
| Il singolo economico può già essere competitivo | Il braccio D è essenziale per capire se servono routing e sciame |
| Un singolo agente ibrido è un confronto aggiuntivo plausibile | Permette di confrontare la configurazione OrcV2 con una politica che usa gli stessi modelli senza la stessa organizzazione a sciame |

### 1.3 Legenda delle evidenze

Nel documento si distinguono:

- **Sorgente verificato:** un comportamento ricavato dalla lettura di file e configurazioni della versione citata. La conclusione può essere forte sul percorso letto, ma non equivale a una riproduzione eseguita.
- **Risultato pubblicato:** misure dichiarate dagli autori o dal benchmark. Sono riportati dominio, unità di costo, numero di esecuzioni e limiti quando disponibili.
- **Calcolo:** una quantità derivata esplicitamente dai numeri pubblicati o da un esempio ipotetico. Non è una nuova misura.
- **Proposta:** un possibile confronto, adattamento o cambiamento da discutere. Non è una decisione approvata.
- **Non verificato:** disponibilità per l'account, comportamento con fornitori veri, prestazione sui siti OrcV2, requisito non stabilito dalle fonti o ipotesi che richiede un esperimento.

La CI, integrazione continua, è l'insieme dei test e controlli automatici eseguiti dal progetto su GitHub. Una CI verde è utile per giudicare la cura del software, ma non dimostra il risultato scientifico pubblicizzato né la compatibilità di ogni modello con ogni strumento.

### 1.4 Perimetro della ricerca

Sono stati esaminati sorgenti, documentazione, configurazioni sperimentali, schede dei modelli, metadati pubblici e risultati dei benchmark. Le verifiche sono documentali e statiche. Non sono stati installati i progetti esterni, addestrati modelli, effettuate nuove chiamate a pagamento o generate nuove pagine web per confrontarli.

Sono inclusi i problemi che cambiano concretamente una scelta per la tesi: qualità del feedback, costi nascosti, stato dell'arte, licenze, riproducibilità, comportamento effettivo del servizio e compatibilità con la struttura OrcV2. Le limitazioni non autorizzano a concludere che una repository non funzioni: indicano cosa va verificato prima di attribuirle una proprietà sperimentale.

### 1.5 Versioni e aggiornamenti osservati

| Oggetto | Versione di riferimento | Nota |
|---|---|---|
| Switchyard | `7558a1d8a5f21824c6fd81ddbf73a041e1a317c9`, 22 ottobre 2026 | L'analisi estesa usa questo snapshot; i risultati dei benchmark provengono da revisioni diverse dichiarate nei profili |
| Conduit | `e93981c0d9304fc7fbff21b3771a77d81429ec2b`, 29 gennaio 2026 | Archivio confermato il 22 ottobre; nessun aggiornamento del codice rispetto alla prima ricognizione |
| NadirClaw | `8a75cdb647dc392de4498c02e86ed90962c08214`, release 0.25.1 | Snapshot della verifica del codice |
| NadirClaw, aggiornamento documentale | `5f60ffe753e30499daa3738bf89f21e884bc9df9`, 22 ottobre 2026 | Modifica solo il README relativo al prezzo Pro; i percorsi di codice analizzati restano identici |
| RouteLLM | `0b64fdafe049e596a3f5657c219329f24af24198` | Snapshot di main verificato per controller e configurazioni |
| RouteFM | `e7e650610850eee055016ed1dab06f08e833663b`, v1.0.1 | Rilascio fissato, distinto dalla scheda e da main successivi |
| Servizi commerciali e schede dei pesi | Pagine consultate il 22 ottobre 2026 | Quando manca una revisione immutabile si tratta di una fotografia documentale, non di una versione congelata |

Per Nadir la differenza fra i due commit è verificabile nel [confronto delle revisioni](https://github.com/NadirRouter/NadirClaw/compare/8a75cdb647dc392de4498c02e86ed90962c08214...5f60ffe753e30499daa3738bf89f21e884bc9df9). È importante per non presentare una tariffa commerciale precedente come attuale.

<a id="sezione-2"></a>
## 2. Contesto OrcV2: che cosa va preservato

### 2.1 Il contributo vigente

La fonte interna è [docs/ROADMAP.md:42](/Users/vincenzomattioli/Documents/OrcV2/docs/ROADMAP.md:42): il contributo è il sistema e la scomposizione misurata del risparmio fra le leve, a qualità non inferiore. Il router appreso è facoltativo. La riprogettazione è esplicitata anche in [docs/TESI_master.md:25](/Users/vincenzomattioli/Documents/OrcV2/docs/TESI_master.md:25).

```text
Contributo vigente: sistema e scomposizione del risparmio
Valutazione: parte centrale della prova
Router appreso: facoltativo
```

Questo evita due letture sbagliate: considerare la scoperta di un router esistente come annullamento automatico della tesi, oppure considerare qualsiasi integrazione di quel router come contributo originale sufficiente. Il valore da dimostrare è l'effetto della configurazione OrcV2 sul dominio scelto.

La tesi riguarda siti web interi, anche con un server e contratti delle rotte. Una rotta è un indirizzo dell'API del sito, per esempio il punto con cui creare o leggere una risorsa. R1 sta costruendo il banco di prova. R2 riguarda strumenti comuni e confronto iniziale; R3 lo sciame; R4 lo studio delle ottimizzazioni; R6 la campagna finale; R7 il router grossolano facoltativo.

### 2.2 Bracci già previsti

Un braccio è una configurazione del sistema sottoposta allo stesso insieme di compiti. [docs/PROTOCOLLO.md:96](/Users/vincenzomattioli/Documents/OrcV2/docs/PROTOCOLLO.md:96) stabilisce:

| Braccio | Configurazione |
|---|---|
| B | Modello forte singolo con gli stessi strumenti e un ciclo di verifica comparabile a OrcV2 |
| C | OrcV2 |
| D | Modello economico dei worker, singolo, con gli stessi strumenti |

```text
Prova principale: C contro B
Controllo economico: D
Ogni strumento comune dato a C viene dato anche a B e D
```

Il protocollo indica DeepSeek V4.1 Flash come economico, mentre la roadmap segnala ancora una scelta aperta fra quel ruolo e l'assegnazione di `worker` a GPT-6.1 Sol nel registro. Il dossier non risolve questa scelta. La rosa effettiva va fissata prima di definire qualsiasi nuovo confronto con un router.

### 2.3 Qualità: due risultati finali, non un solo voto

Secondo [docs/PROTOCOLLO.md:167](/Users/vincenzomattioli/Documents/OrcV2/docs/PROTOCOLLO.md:167), le due metriche sono:

- **Funziona:** quota dei passi d'interazione superati, sulla scala da zero a cento. Il margine attuale di non inferiorità è dieci punti medi fra compiti.
- **Piace:** confronto graduato fra C e B, da meno due, B molto migliore, a più due, C molto migliore; zero significa pari. Il margine va ancora fissato secondo il protocollo prima del confronto finale.

```text
Non inferiorità: richiesta su entrambe le metriche
Costo: dollari per sito, con incertezza del confronto
```

Non inferiorità significa dimostrare che la perdita media è contenuta entro un margine considerato accettabile e fissato prima della prova. Non coincide con osservare due medie vicine o non trovare una differenza statisticamente significativa.

I controlli comprendono anche errori JavaScript, adattamento alle larghezze e accessibilità, ma il protocollo precisa che non tutti entrano nella metrica principale. Il test del server è una metrica secondaria. Queste distinzioni vanno conservate quando si confronta OrcV2 con benchmark che usano solo risposte corrette/sbagliate.

### 2.4 Le criticità già aperte non vengono risolte da un router

La roadmap segnala la numerosità dei compiti, la parità fra configurazioni e la validità del giudice. Aggiungere un sistema esterno aumenta le alternative da confrontare; non aumenta il numero di siti indipendenti e non risolve l'incertezza sulle metriche visive.

Nel piano attuale ci sono cinque compiti di sviluppo. Il numero finale dei compiti di test e alcuni dettagli del protocollo sono ancora da stabilire. Le vecchie quantità riportate nelle decisioni storiche non devono essere trattate come congelate se il protocollo successivo le ha rimandate.

<a id="sezione-3"></a>
## 3. Tassonomia: cosa significa davvero router pronto

### 3.1 Decisioni che vanno tenute separate

| Dimensione | Domanda | Esempio |
|---|---|---|
| Organizzazione del lavoro | Chi svolge quale pezzo e con quali dipendenze? | Sciame per sezioni OrcV2 |
| Scelta del modello | Chi produce la prossima risposta? | Forte o economico |
| Scelta del fornitore | Chi serve quel medesimo modello? | Endpoint della casa o aggregatore |
| Controllo operativo | Il lavoro deve essere corretto o escalato? | Critico, consigliere, esito dei test |
| Valutazione scientifica | La pagina finale è abbastanza buona? | Funziona, piace, voti umani |

Un router di fornitori migliora accesso o affidabilità, ma non è necessariamente un selettore di modelli. Un modello che classifica il dominio di un prompt non stima automaticamente la qualità della risposta economica. Un verificatore del testo non verifica automaticamente un sito eseguibile.

### 3.2 Pronto, preaddestrato e specializzato

- **Pronto:** il software o servizio può prendere decisioni senza sviluppare l'algoritmo da zero.
- **Preaddestrato:** sono già stati appresi parametri da un insieme di dati. È necessario conoscere cosa predicono e su quali dati.
- **Configurato:** modelli, soglie e regole sono impostati. Una configurazione può essere pronta senza un classificatore addestrato.
- **Calibrato:** il punteggio o la soglia sono stati controllati su dati pertinenti. Un punteggio di 0,8 è calibrato come probabilità solo se gli esiti coerenti con quella previsione si verificano con una frequenza compatibile.
- **Specializzato nel nostro dominio:** ha evidenza su siti, strumenti, modelli e criteri sufficientemente vicini a quelli di OrcV2. Non deriva dal solo nome code, agent o quality.

Le soglie possono richiedere taratura anche con pesi già addestrati. Tarare una soglia non equivale a riaddestrare l'intero modello, ma deve avvenire sui dati di sviluppo, non sul test finale.

### 3.3 Prima o dopo la risposta

Nelle descrizioni Switchyard, **Capable** indica il ruolo configurato come più capace e **Efficient** il ruolo configurato come più economico. Non sono nomi di modelli né certificazioni delle loro prestazioni. Nel servizio ospitato i due ruoli vengono assegnati in base agli estremi di prezzo dei candidati: il modello più caro non è per questo dimostrato migliore sul compito.

**Routing prima della generazione:** decide guardando richiesta e storia; risparmia se evita una chiamata costosa, ma deve prevedere l'esito.

**Routing durante il lavoro:** decide a ogni turno o fase, osservando anche strumenti e avanzamento. Richiede sessioni, compatibilità della storia e contabilità di ogni chiamata.

**Cascata dopo la risposta:** genera prima con l'economico, verifica e talvolta ripete col forte. Se si escala, si pagano entrambi i tentativi e il controllo. Un controllo che dipende dalla risposta già generata dal forte non è gratuito in produzione.

### 3.4 Granularità: sito, pezzo o turno

R7 prevede una scelta grossolana per tipo di pagina, per esempio scegliere subito il forte oppure OrcV2. Un router nato per scegliere fra nomi di modelli può essere adattato a scegliere strategie, ma è un problema differente. Scegliere modello per worker richiede attribuire esiti ai pezzi; scegliere a ogni turno richiede affrontare anche il credito ritardato: il risultato del sito si conosce alla fine, mentre le decisioni sono state molte.

<a id="sezione-4"></a>
## 4. Mappa comparativa delle alternative

| Alternativa | Natura della decisione | Già operativa senza nuovo training | Pesi scaricabili | Esecuzione delle chiamate |
|---|---|---|---|---|
| Switchyard, libreria | Regole, stato, giudice LLM; Prefill separato | Sì per le politiche configurate | Non implica un checkpoint universale pronto per ogni strategia | Runtime scelto dall'integratore |
| Switchyard, OpenRouter | Sottoinsieme di politiche del servizio ospitato | Sì, come API documentata | Non necessario per usare il servizio | OpenRouter |
| Conduit | Bandit che apprendono da feedback; controlli non appresi | Il software parte, ma il risultato dipende dai dati e dal feedback | Non un router universale già allenato sui nostri siti | Executor o integrazione, oppure adattamento selettivo |
| NadirClaw | Classificatore e regole; librerie di cascata distinte | Sì, secondo il percorso realmente attivato | Alcuni artefatti sono presenti; non tutti i dati di training | Proxy o librerie |
| Not Diamond | Selettore preaddestrato o personalizzato via API | Sì per il percorso documentato; accesso effettivo da verificare | Nessun checkpoint pubblico assunto | Può restare nel gateway dell'applicazione |
| RouteLLM | Router appresi fra forte ed economico | Sì, con checkpoint e dipendenze | Sì | Controller o adattatore |
| Arch-Router | Associazione fra intento e descrizione delle rotte | Sì, con modello e preferenze configurate | Sì | Serve poi una chiamata al modello scelto |
| RouteFM | Previsione a partire da osservazioni dei candidati e rappresentazioni delle richieste | Sì, ma occorrono esiti dei candidati anche senza riaddestramento | Sì | Il router non raccoglie né genera da solo gli esiti |
| OpenRouter Auto | Classificazione del compito e ranking di spesa aggregata | Sì | Non necessario | OpenRouter |
| OpenRouter Pareto Code | Selezione entro fasce di punteggio coding | Sì | Non è presentato come predittore appreso del nostro esito | OpenRouter |

Questa tabella indica il tipo di alternativa, non una classifica misurata di qualità. Le sezioni seguenti documentano le differenze effettive, i limiti e le fonti. La disponibilità di un servizio non prova l'accesso al nostro account; la disponibilità di pesi non elimina costo di esecuzione, licenza e lavoro di adattamento.

<a id="sezione-5"></a>
## 5. Switchyard: analisi completa della libreria e del servizio

Data di verifica: **22 ottobre 2026**. Questa sezione distingue fatti documentati, lettura statica dei sorgenti e proposte sperimentali. Nessuna integrazione è stata eseguita; nessun modello è stato chiamato; nessuna prestazione è stata misurata su OrcV2. Le raccomandazioni non modificano le decisioni già fissate nel protocollo.

### 5.1 Identità, versione e conclusione operativa

Switchyard è una libreria di instradamento: sceglie quale modello deve servire una richiesta e può applicare controlli durante il lavoro di un agente. Un *proxy* è un servizio intermedio al quale il programma invia le richieste; un *runtime incorporato* esegue invece la logica direttamente nel programma ospitante. Switchyard offre entrambe le superfici. Non fornisce automaticamente un sistema che scomponga un sito in sezioni, esegua i componenti in parallelo e valuti il risultato estetico.

**È utilizzabile senza addestrare un router proprio.** Stage, Plan/Execute e Random sono politiche già operative; Capability ed Escalation possono usare un modello esistente come giudice. Il percorso Prefill, che richiede un classificatore appreso specificamente per il proprio insieme di modelli, è un caso separato.

Lo snapshot analizzato è **`7558a1d8a5f21824c6fd81ddbf73a041e1a317c9`**, commit del **22 ottobre 2026 alle 12:55:28 UTC**, intitolato “feat(runner): support OpenAI Decisions (#1070)”. È successivo allo snapshot `34ca48efb9ab8b3be9a26deb378466c125390022` usato nella prima ricognizione. La release pubblicata più recente consultata è **v0.3.0 del 22 settembre 2026**; il codice successivo in `main` non va presentato come se fosse già tutto incluso nel pacchetto distribuito. [Commit](https://github.com/NVIDIA-NeMo/Switchyard/commit/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9), [release v0.3.0](https://github.com/NVIDIA-NeMo/Switchyard/releases/tag/v0.3.0).

Il giudizio è favorevole a una prova circoscritta. Il valore maggiore è duplice: un componente operativo da integrare e un confronto scientifico vicino a OrcV2. La disponibilità di un singolo agente che alterna modelli rende più importante misurare quale beneficio aggiungano coordinamento e scomposizione.

### 5.2 Architettura: dove entra nel sistema

La configurazione distingue tre oggetti:

| Oggetto | Responsabilità |
|---|---|
| Client | Indirizzo del servizio, formato dei messaggi, credenziali e politica dei tentativi |
| Target | Un modello concreto raggiungibile attraverso un client |
| Route | Nome visto dall'applicazione e politica che sceglie fra target |

Un nome di route come `switchyard/stage` è un alias, non l'identità del modello che ha consumato i token. Due route possono condividere i target; due target possono condividere il trasporto. Questa distinzione è essenziale per evitare di prezzare ogni chiamata con un listino medio del router. [Concetti e configurazione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/core_concepts.md).

Il percorso principale è: ricezione della richiesta, conversione in tipi comuni, decisione, chiamata al servizio, conversione della risposta. `switchyard-protocol` descrive messaggi, strumenti, consumi ed eventi; `libsy` contiene gli algoritmi; `switchyard-translation` converte i formati; `switchyard-llm-client` gestisce le chiamate; runner e server costruiscono il servizio configurato. [Architettura](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/architecture.md).

La libreria può delegare all'ospite ogni chiamata necessaria. Nel file `crates/libsy/src/core/algorithm.rs:106`:

```rust
pub struct CallModel {
    pub algorithm: String,
    pub request: Request,
    pub models: Vec<ModelId>,
```

L'ospite riceve anche `CallDecision` per decisioni tipizzate e `Done` per il risultato finale. *Tipizzata* significa che una decisione booleana, una scelta fra alternative o un punteggio hanno un contratto esplicito, distinto dal normale testo libero. Le chiamate possono essere eseguite e registrate dal sistema ospitante. [Interfaccia e ciclo](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/core/algorithm.rs#L543-L572).

**Implicazione per OrcV2:** esiste un'integrazione che conserva il controllo sulle chiamate reali. Non occorre sostituire il contabile con le statistiche del server. Serve comunque un adattatore fra i contratti Python del progetto e quelli della libreria: non è un cambio di una sola riga.

### 5.3 Mappa completa degli algoritmi

| Nome | Meccanismo | Richiede addestramento proprio? | Chiamate aggiuntive |
|---|---|---:|---|
| Auto | Preset di Stage con impostazioni fisse | No | Nessuna nel preset della libreria |
| Execution / Stage | Regole su strumenti, errori e avanzamento | No | Giudice facoltativo nei turni ambigui |
| Task / Capability | Previsione del giudice prima dell'esecuzione | No | Secondo frequenza configurata |
| Composite | Giudice iniziale e Stage durante il lavoro | No | Giudice ai confini configurati |
| Plan/Execute | Forte fino alla prima modifica, poi economico | No | Nessun giudice |
| Escalation | Economico, giudizio sul turno, eventuale forte | No | Giudice e possibili risposte scartate |
| Custom | Prompt, schema e politica personalizzati | No, salvo scelta esterna | Giudice |
| Advisor Gate | Esecutore più revisore che approva o rimanda | No | Revisioni limitate |
| Sub-agent policy | Politica separata per richieste delegate | No | Secondo la politica scelta |
| VGR | Candidato locale, verifica, eventuale cloud | No come prerequisito del framework | Verificatori e giudici |
| Prefill | Classificatore su attivazioni interne | **Sì: pesi compatibili da procurare/addestrare** | Inferenza dell'encoder |
| Random / Passthrough / Noop | Casuale, fisso, diagnostico | No | Nessun giudice |

La tabella è un catalogo della libreria, **non** una promessa che tutte le integrazioni offrano tutti gli algoritmi. Gli identificatori concreti e i limiti sono documentati nell'[overview](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/overview.md); gli algoritmi esportati sono verificabili in [lib.rs](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/lib.rs#L25-L61).

#### 5.3.1 Auto e Stage: pronto non significa appreso

Auto non confronta automaticamente tutte le strategie. È un preset: economico come default, soglia 0,5, tre risultati recenti degli strumenti, mantenimento del forte per due richieste dopo una promozione, nessun classificatore. Il numero 0,5 misura l'accordo dei segnali secondo la formula implementata; **non significa 50% di probabilità di riuscita**.

Stage combina intensità delle modifiche, gravità degli errori e segni di stallo. Una funzione `tanh` limita il punteggio tra -1 e 1; il segno indica il livello e il valore assoluto viene chiamato confidence. Non risulta un addestramento statistico di questi pesi nel percorso standard. [Scorer](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/util/stage.rs#L319-L350).

Tre eventi prevalgono sul punteggio: errore critico, ripetizione significativa dello stesso fallimento e compattazione riconosciuta del contesto. La compattazione è la sostituzione della storia lunga con un riassunto: i segnali scomparsi potrebbero altrimenti riportare erroneamente la scelta all'economico. [Precedenze](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/util/stage.rs#L352-L425).

Per evitare un continuo cambio di modello, il forte resta attivo brevemente; un test pulito può interrompere anticipatamente questo mantenimento. La modalità `capable_first` parte invece dal forte, ma è dichiarata sperimentale e non ha la stessa base empirica. La semantica degli strumenti è estendibile con nomi di osservazione, modifica, pianificazione e avanzamento neutro; non è una classificazione automatica arbitraria dei loro effetti. [Stage](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/stage_router_routing.md).

**Utilità per OrcV2:** è un candidato concreto per decidere quando un worker economico necessita assistenza. Gli errori negli strumenti sono solo segnali del processo: un sito può compilare e risultare esteticamente scarso senza produrre alcun errore. Stage non sostituisce la valutazione del sito.

#### 5.3.2 Capability: previsione del compito e soglie

Il giudice stima `p_solve`, probabilità dichiarata che il livello economico completi l'intero compito. Produce anche il requisito più difficile, una regola di capacità e la categoria supported/uncertain/unsupported/unmatched. La politica confronta la stima con una soglia di base, aumentata per le categorie meno favorevoli. Una stima emessa dal modello non è automaticamente calibrata sui siti.

Nel percorso ordinario il giudice vede il compito iniziale e l'ultimo messaggio umano; una finestra aggiuntiva può mostrare storia recente. Il default `every_request` può farlo intervenire anche su ogni prosecuzione degli strumenti; `user_turn` o `new_session` riducono la frequenza se l'identità della sessione è conservata. [Contratto e frequenze](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/llm_classifier_routing.md#when-the-judge-runs).

**Discrepanza rilevante fra guida e codice.** La guida descrive errori HTTP e timeout come interruzioni della richiesta. Nel sorgente fissato, la costruzione di Capability imposta invece il recupero degli errori da `config.fail_open`, il cui default è vero; un verdetto assente ricade normalmente sul livello capace. [Costruzione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/llm_class.rs#L687-L719). Il giudice converte gli errori ricevuti e gli errori di parsing in assenza di verdetto quando il percorso lo consente. [Gestione del verdetto](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/util/llm_judge.rs#L266-L305).

La lettura statica supporta un comportamento dipendente da configurazione e percorso d'esecuzione. La prova deve includere JSON invalido, HTTP 429, timeout e interruzione del flusso. Non è corretto affermare senza condizioni né “ogni guasto passa al forte” né “ogni guasto ferma tutto”.

#### 5.3.3 Composite e modelli decisionali

Composite oggi realizza una composizione specifica: un classificatore imposta la preferenza iniziale e Stage può modificarla durante l'esecuzione. Non è ancora un linguaggio generale per collegare arbitrariamente qualsiasi router. Conservare una decisione iniziale richiede identità di sessione o stato gestito dall'ospite. [Composite](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/composite_routing.md).

Il giudice può essere un LLM ordinario o un *decision model*, servizio che risponde direttamente a domande strutturate. I percorsi presenti includono `system_one` e, nel nuovo commit, `openai_decisions`. Nell'esempio Jev si confronta il vantaggio previsto del candidato capace rispetto all'economico, con soglia separata. È diverso dal limitarsi a stimare se un generico modello piccolo sappia risolvere il compito.

La presenza del client OpenAI Decisions dimostra il supporto del trasporto nel sorgente: **non dimostra che un account abbia accesso, che un dato modello sia disponibile o che la probabilità sia calibrata sul progetto**. [Schema dei client decisionali](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/reference/toml_schema.md#decision_clientsname), [implementazione OpenAI](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy-llm-client/src/openai_decisions.rs).

Il servizio decisionale restituisce una decisione o un punteggio, non il sito finito. La sua chiamata e la successiva generazione sono operazioni distinte, ciascuna con il proprio consumo o prezzo se fatturata.

#### 5.3.4 Plan/Execute: dettaglio che cambia l'esperimento

Il forte esplora e pianifica. La prima chiamata riconosciuta come edit o write fa passare il seguito all'economico. Nel file `crates/libsy/src/algorithms/plan_execute.rs:90`:

```rust
let mutation_seen = signals.edit_count > 0 || signals.write_count > 0;
```

**Anche una modifica fallita può causare il passaggio.** Non esiste qui una certificazione che il piano sia completo o che il primo file sia quello giusto. Un prompt chiede al forte di pianificare prima della prima modifica; resta un'istruzione al modello. [Guida Plan/Execute](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/plan_execute_routing.md#planexecute-routing), [scelta della fase](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/plan_execute.rs#L87-L119).

La sessione memorizza il passaggio anche dopo una compattazione. L'istanza conserva fino a 4.096 identità in esecuzione; `session_final` le libera, mentre il riavvio elimina lo stato. Per rilevare il primo cambiamento servono le chiamate originali degli strumenti: un solo risultato più `previous_response_id` può non contenere il nome dello strumento.

È un confronto particolarmente pulito per OrcV2: distingue il beneficio di un piano forte seguito da lavoro economico dal beneficio aggiuntivo dello sciame. È anche un candidato operativo, purché la prima modifica sia una frontiera sensata per costruire un sito.

#### 5.3.5 Escalation: una cascata con costo interno

Una *cascata* prova un modello e può passare a un altro dopo averne osservato il lavoro. Escalation genera un turno economico e lo trattiene, poi il giudice valuta quanto accaduto. Se le conferme raggiungono la soglia, scarta il turno e chiama il forte; altrimenti restituisce l'economico.

Con il default servono due verdetti consecutivi con nuova evidenza nella stessa categoria di fallimento. La promozione può restare fissata alla sessione; una de-escalation configurata può consentire il ritorno all'economico. Una richiesta promossa può quindi pagare **economico + giudice + forte**. Questo non è il modello di costo di una semplice scelta prima dell'esecuzione. [Escalation](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/escalation_router_routing.md#how-the-decision-works).

Il filtro “nuova evidenza, stesso problema” serve a evitare che un singolo errore vecchio venga contato più volte. Per OrcV2 è utile come principio di controllo, ma l'intervento può arrivare quando sono già stati modificati file. Il risultato finale dipende dalla traiettoria precedente: non si può dedurre l'esito della cascata sommando risposte indipendenti.

#### 5.3.6 Advisor Gate: esecutore e controllo forte

Qui il forte non sostituisce normalmente l'esecutore. Quest'ultimo lavora; quando dichiara concluso un turno senza strumenti o raggiunge un punto di controllo per lo stallo, qui chiamato checkpoint, l'advisor legge la trascrizione, approva oppure propone un piano di correzione. Il turno iniziale può essere scartato e la correzione viene passata all'esecutore.

I default del codice sono una revisione, 2.048 token massimi per l'advisor e `fail_open=true`; la trascrizione è limitata a 200.000 caratteri conservando testa e coda. Sono **limiti di revisioni, token e testo**, non una prenotazione monetaria. [Default](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/advisor_gate.rs#L137-L149).

Il codice annota anche i consumi del turno scartato prima di costruire la richiesta correttiva. Conservare questa spesa è necessario: testo non mostrato non equivale a inferenza gratuita. [Redo](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/advisor_gate.rs#L342-L371). Il profilo benchmark usa parametri diversi, descritti più avanti.

L'advisor è un controllore interno che contribuisce al sito. Il giudice scientifico di R1 valuta dopo la generazione: confondere i due ruoli renderebbe ambiguo che cosa si sta misurando.

#### 5.3.7 Policy per subagenti e Custom

La policy `subagents` seleziona modelli diversi per richieste già delegate da un sistema esterno; non crea i subagenti, il grafo delle dipendenze o l'integrazione degli artefatti. È disponibile su Passthrough, Stage e Composite. Occorrono identità di sessione e agente; senza identità del figlio la richiesta segue la route principale. Sono supportate assegnazione fissa o classificazione personalizzata. [Policy delegate](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/subagent_routing.md).

Custom consente un prompt e uno schema che nominano direttamente il target. Questo rende possibile una regola specifica per dominio e anche più destinazioni; la qualità della regola e delle descrizioni resta responsabilità della sperimentazione. Un campo chiamato confidence non diventa una garanzia di successo per il solo fatto di comparire nel JSON.

Per OrcV2 la policy può servire dopo che il sistema di delega è definito. Importarla prima non risolve la scelta di chi fa che cosa né la qualità dell'unione finale.

#### 5.3.8 Verification-Gated Routing, presente ma sperimentale

VGR genera una risposta sul livello locale e raccoglie evidenza prima di rilasciarla. Un esito finale non verificato, dati mancanti o verificatori indisponibili portano al cloud; i turni che chiamano strumenti hanno una politica distinta. Esistono modalità off, shadow, evaluate e active: shadow calcola una decisione mentre continua a servire il cloud.

Il default è off. La modalità active richiede una dichiarazione esplicita prevista dal software; non va scambiata per una validazione scientifica già compiuta. Il catalogo dichiara il percorso non benchmarkato. [VGR](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/vgr_routing.md), [catalogo](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/overview.md#compare-the-strategies).

La lezione trasferibile è che il controllo deve riferirsi **al candidato concreto che verrà servito**, non a una descrizione vaga delle capacità del modello. Per i siti, però, verificare compilazione o struttura non basta a verificare gradevolezza e interazioni.

#### 5.3.9 Prefill, Random e Passthrough

*Prefill* è la fase in cui il modello elabora il testo di ingresso prima di generare la risposta. Il router usa attivazioni interne ottenute tramite PyTorch/Transformers per un classificatore. La repository non fornisce un checkpoint supportato, un esportatore o gli asset dell'encoder compatibili. La guida suggerisce almeno 3.000–5.000 esempi valutati per ogni modello: è una raccomandazione della guida, non un teorema sulla numerosità. [Percorso Prefill](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/prefill_routing.md).

Nel ramo letto si prende il modello con massima previsione. Non è applicato lì il problema vincolato “minimo costo a qualità almeno τ”; l'assenza di un termine di costo in quella selezione impedisce di identificarla automaticamente con l'obiettivo della tesi. [Selezione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/prefill-router/src/algorithm.rs#L173-L199).

Random distribuisce le richieste secondo pesi; Passthrough sceglie un target fisso; Noop serve come percorso diagnostico. Sono utili per controlli sperimentali. Il “casuale” della libreria e quello ospitato possono mantenere la scelta per intervalli diversi: la granularità va fissata, perché un modello per compito e un modello a ogni turno sono esperimenti differenti.

### 5.4 Modalità ospitata su OpenRouter: sintesi verificata

OpenRouter espone `nvidia/switchyard`, con capability, stage, auto, composite, random e passthrough; non espone Plan/Execute, Advisor o Escalation. Stage ospitato consulta il giudice nei casi ambigui; auto no. Accetta fino a tre candidati: i due estremi di prezzo definiscono i livelli; quello intermedio resta ripiego. Il giudice riceve soprattutto primo/ultimo messaggio umano, senza candidati, prezzi o definizioni degli strumenti. Le sue chiamate sono fatturate separatamente; non è aggiunta una commissione specifica di routing alla risposta principale. Metadati opzionali mostrano strategia, modello risolto e tempi. Per una campagna riproducibile occorrono candidati espliciti. [Documentazione ospitata](https://openrouter.ai/docs/guides/routing/routers/switchyard-router).

**Implicazioni originali per il progetto:** il modello più costoso non è necessariamente il migliore sul compito; un terzo modello non costituisce una vera terza classe di scelta; un giudice con scheda generica può stimare male un economico forte sul codice. Usare la stessa API non riproduce automaticamente i benchmark delle politiche assenti. L'API ospitata è una possibilità concreta per un pilota a basso costo d'integrazione, mentre Plan/Execute e Advisor richiedono un percorso diverso.

### 5.5 Integrazioni, contesto e compatibilità

#### 5.5.1 Python e LiteLLM

Il pacchetto Python richiede almeno Python 3.10 e dichiara zero dipendenze runtime Python; incorpora però un'estensione Rust. La compilazione usa maturin; non è una libreria costituita da un solo file Python. [Packaging](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/pyproject.toml).

L'esempio Python mostra come ricevere `Step.CallModel` ed eseguire la chiamata con un proprio client. È una base concreta per un prototipo che registri ogni consultazione nel contabile esistente. [Esempio](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/examples/libsy.py).

L'integrazione LiteLLM letta è sperimentale, legata al checkout e fissata a LiteLLM 1.102.0. Supporta Stage basato sulla storia e Random; rifiuta gli algoritmi che richiedono chiamate intermedie o risposte già prodotte. Non può quindi servire da collegamento generale per Capability con giudice, Advisor o Escalation.

Il plugin può cambiare istruzioni e alcuni parametri, ma la sua interfaccia non espone tutti i valori originali della richiesta. Il body può conservare l'alias del gruppo; l'header `x-litellm-model-name` identifica il modello concreto. La lista diagnostica dei fallback non configura da sola i ripieghi di LiteLLM. [Contratto dell'integrazione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/examples/litellm/README.md).

#### 5.5.2 NeMo Relay

Il percorso attuale richiede Relay almeno 0.10 e inferiore a 1.0; versioni 0.8/0.9 hanno un problema documentato di propagazione degli errori upstream quando il plugin è attivo. La release di settembre e il main attuale non hanno la stessa indicazione minima. Questo è un motivo concreto per fissare insieme versione del router e del gateway. [Relay](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/integrations/nemo_relay.md).

#### 5.5.3 Protocolli, history e reasoning

Sono supportati Chat Completions, Responses e Anthropic Messages, anche con traduzione fra ingresso e uscita. La compatibilità della forma HTTP non garantisce identità semantica di tutti i campi. Tool call, risultati, ragionamento visibile e contenuti specifici del fornitore richiedono prove sul percorso effettivo.

Una continuazione mediante ID può vincolare la richiesta al modello che conserva quello stato. Il server mantiene anche associazioni locali e, per alcune conversioni, storia in memoria. Le associazioni sono locali al processo e si perdono al riavvio; inviare storia completa permette ai router dinamici di osservare l'avanzamento. [Continuazioni](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/llm_classifier_routing.md#responses-continuations-by-id).

Le note di passaggio aggiungono testo alla richiesta inoltrata. Il codice deve disabilitare il riuso esatto del body originario: altrimenti la traduzione può ignorare l'aggiunta. Questo mostra perché un adattamento della politica richiede anche test sui messaggi reali. [Mutazioni della richiesta](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/util/prompts.rs#L14-L67).

*Reasoning effort* indica lo sforzo di ragionamento richiesto al modello. La sua traduzione dipende dal protocollo: non basta copiare un campo da Chat a Responses o Anthropic. Il confronto deve fissare modello, fornitore, protocollo e controllo effettivamente applicato. La cache del prompt, cioè il riuso fatturato a tariffa ridotta del prefisso, può perdersi passando da un modello all'altro; la documentazione riporta casi in cui il routing ha così aumentato il costo. [Scelta e controesempi](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/model_selection.md#counter-examples).

Se il contesto eccede il limite, il server può tentare altri target; non è una compressione automatica garantita. Il riconoscimento dell'overflow dipende da codici e messaggi specifici; alcuni errori non vengono classificati come tali. [Contesto](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/operations/context_window.md).

### 5.6 Benchmark: numeri, unità e limiti

#### 5.6.1 DeepSWE: il confronto più vicino

La suite contiene 113 compiti di ingegneria del software. L'agente è Codex CLI 0.154.0, il banco esecutivo Harbor 0.13.2, l'interfaccia Responses. Le prove sono closed-book: l'ambiente di esecuzione non può consultare liberamente Internet. L'assenza di rete non esclude che un modello abbia visto un compito durante il proprio addestramento.

Sono ammessi tre ore per agente, senza limite al numero di passi né al costo. Gli errori dell'ambiente e risultati mancanti contano come insuccessi nel punteggio strict. I costi derivano dai consumi osservati riprezzati con listino OpenRouter standard del 9 settembre, non dalle fatture effettive del servizio originale. [Qualificazione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/DEEPSWE_V11_QUALIFICATION.md).

La tabella più coerente si ricava dal solo profilo Plan/Execute:

| Configurazione | Risolti, media ± deviazione standard | Dollari per suite | Dollari per compito, calcolati |
|---|---:|---:|---:|
| Sol singolo | 62,8 ± 3,1% | 720,95 ± 19,47 | 6,380 |
| Plan/Execute Sol → Luna | 60,8 ± 5,3% | 180,51 ± 9,43 | 1,597 |
| Luna singolo | 51,0 ± 3,7% | 50,02 ± 1,04 | 0,443 |

Le tre repliche sono esecuzioni indipendenti dell'intera suite. La deviazione standard descrive la dispersione fra quelle repliche; non è l'intervallo della differenza appaiata fra metodi. Il risparmio calcolato è `1 - 180,51 / 720,95 = 74,96%`; la differenza di successo è -2 punti percentuali.

Planner ed esecutore usano entrambi effort max. Le esecuzioni originali raggiungevano i modelli attraverso NVIDIA Inference Hub; il TOML pubblico li collega a OpenRouter. Conserva la politica, ma non riproduce identicamente la catena di servizio. [Profilo Plan/Execute](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/deepswe-v11-plan-execute-luna-sol.toml#L9-L30).

**Inferenza scientifica:** è evidenza favorevole alla convenienza di quella configurazione su DeepSWE. Non dimostra non inferiorità secondo il margine OrcV2, non prova bellezza dei siti e non è un preventivo della campagna del progetto.

#### 5.6.2 Stage e Advisor: non fondere gli anchor

La pagina riassuntiva pubblica Stage a 61,36% e 466,28 dollari; Advisor a 57,5% e 208 dollari; Sol a 62,8% e 720,95 dollari; Luna a 52,2% e circa 49 dollari. [Tabella generale](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/benchmarks.md#deepswe).

Esistono discrepanze da conservare nella tesi:

- La pagina dice tre repliche per tutti tranne Luna; la qualificazione dice **una** per Stage.
- Il profilo Stage riporta 76 successi su 113, cioè 67,3%, diverso dal 61,36% riassuntivo. Specifica la revisione, una sola prova e il task crashato. Non è lecito scegliere il numero più favorevole senza chiarire quale esecuzione rappresenta.
- Il profilo Advisor indica Sol a circa 743 dollari e due prove valide Luna, mentre Plan/Execute presenta un altro riepilogo degli anchor.
- Le concorrenze e alcune revisioni differiscono.

Advisor usa tre revisioni massime, checkpoint a 30 turni, almeno tre risultati di strumenti prima del controllo, 32.768 token per l'advisor e fail-open disabilitato. Quindi un'integrazione con default 1/2.048/fail-open non riproduce quel risultato. Il profilo segnala 8 fallimenti di memoria su 339 tentativi. [Stage](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/deepswe-v11-stage-router-luna-sol.toml#L11-L36), [Advisor](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/deepswe-v11-advisor-gate-luna-sol.toml#L9-L29).

#### 5.6.3 Terminal-Bench, Jev e assistenza clienti

Per Terminal-Bench 2.1, la pagina pubblica:

| Strategia | Compiti risolti | Dollari per run |
|---|---:|---:|
| Classificatore LLM | 79,40% | 109,04 |
| Stage | 79,03% | 109,81 |
| Escalation | 79,80% | 122,63 |
| Jev, replay | 82,02% | circa 92,12 |
| Opus 4.8 | 77,15% | 148,83 |
| GLM 5.2 | 74,16% | 71,31 |

I profili completi non sono disponibili per ogni riga. Il risultato Jev è **replay**, cioè valutazione sulle tracce disponibili, non una nuova traiettoria completa dopo ogni possibile scelta. Il profilo corrente avverte inoltre che la soglia adattata non è calibrata per quella nuova formulazione. [Profilo Jev](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/tb21-jev-opus-glm.toml#L4-L12).

Su tau2 telecom sono pubblicati un profilo bilanciato con 90,3 ± 7,1% di successo e 45% dei turni sull'economico, e uno aggressivo con 89,1 ± 2,9% e circa 85% dei turni sull'economico. Lo scenario è assistenza clienti, non sviluppo web; il modello locale originale è sostituito da un quasi equivalente nel file pubblico. Non sono presenti qui elementi sufficienti per dedurre automaticamente un risparmio monetario per OrcV2. [Bilanciato](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/tau2-telecom-custom-opus-qwen-balanced.toml#L7-L29), [aggressivo](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/routing-profiles/tau2-telecom-custom-opus-qwen-aggressive.toml#L7-L29).

#### 5.6.4 Controevidenze da includere

Sul campione SWE-Atlas di 40 compiti, GLM singolo, Opus singolo e router corretto risolvono tutti 15 compiti. Il router costa sinteticamente 0,889 dollari per compito contro 0,501 di GLM e 1,176 di Opus. Risparmia sul forte ma spende il 77,4% in più dell'economico senza migliorarne l'accuratezza aggregata. I prezzi sono dichiaratamente sintetici; i giudici sono inclusi, l'infrastruttura e il verificatore esterno no.

Sul sottoinsieme TW, il nominalmente economico supera il nominalmente forte. Rilevare uno stallo non prova quindi che il passaggio al forte abbia valore positivo. [SWE-Atlas](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/SWE_ATLAS_ESCALATION_REPORT.md#paired-benchmark).

LangChain misura 145 compiti agentici: Opus 86% a 11,45 dollari, routing 80% a 3 dollari, Nemotron 77,7% a 0,72 dollari. Il risparmio del 74% rispetto al forte comporta sei punti persi; il guadagno sull'economico è piccolo rispetto alla variazione fra prove. Il giudice pesa il 21,2% del costo del braccio instradato. Lo studio riguarda assistenza, indagini operative e automazioni, non siti. L'articolo distingue il middleware mostrato dalla configurazione server di escalation realmente misurata. [Studio LangChain](https://www.langchain.com/blog/switchyard-agent-routing-benchmark).

Queste controevidenze rafforzano la necessità del braccio D e di contare ogni consultazione. La percentuale di chiamate economiche, da sola, non misura né risparmio finale né qualità.

### 5.7 Compatibilità concreta con OrcV2

Nel progetto, `agent.py:389` serializza il risultato dello strumento in un messaggio tool:

```python
"content": json.dumps(risultato),
```

`tools/bash.py:62` restituisce stdout, stderr ed exit_code; `tools/write_file.py:41` espone il nome write_file. Switchyard ha già riconoscimento di campi exit_code, success ed error e distingue contenuti letti dai veri fallimenti degli strumenti. È quindi **plausibile una buona corrispondenza iniziale**, non una prova che ogni segnale sia interpretato correttamente. [Rilevamento strutturato](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/algorithms/util/tool_signals.rs#L1474-L1516).

Vanno provati almeno: exit_code non zero con testo vuoto; errore di lettura; file che contiene parole come “error” ma letto correttamente; scrittura fallita; tool con nome nuovo; errori ripetuti ma diversi; test passati dopo una correzione. L'obiettivo è verificare l'evidenza utilizzata dalla politica, non soltanto che arrivi una risposta HTTP.

In `llm_gateway.py:196` il record viene associato al modello configurato:

```python
record = self.mapper.to_record(
    response, model=self.model, latency_s=latency_s, attempt=attempt,
```

Sostituire quel modello con un alias dinamico senza adeguare l'attribuzione può rendere scorretto il costo. Il problema comprende anche chiamate del giudice, risposte scartate, tentativi, cache e risposte servite da un ripiego. Le statistiche del router possono aiutare la riconciliazione, ma non sostituiscono automaticamente il ledger del progetto.

**Formula contabile proposta per una futura prova**, non modifica applicata:

```text
costo_generazione =
    esecutori + planner + giudici_di_routing + advisor
    + inferenze_scartate + tentativi_fatturati
```

Il giudice finale scientifico va riportato separatamente secondo il protocollo, perché misura l'artefatto anziché contribuire a produrlo. Token stimati, token osservati, costo ricostruito da listino e addebito del fornitore devono restare categorie distinguibili.

### 5.8 Stabilità, licenza e verifiche disponibili

La classificazione ufficiale è pre-1.0: libsy beta; client e runner alpha; server destinato a demo e valutazione, non dichiarato pronto per produzione. La release 0.3 ha eliminato lo stack server Python precedente e modificato API e configurazione. Il riuso deve fissare release o commit e non mescolare esempi di epoche diverse. [Stabilità dei componenti](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/README.md#components), [migrazione](https://github.com/NVIDIA-NeMo/Switchyard/releases/tag/v0.3.0).

Il workspace Rust dichiara versione minima 1.96.1. Il benchmark aggiunge Docker, harness e agenti; Prefill aggiunge encoder e librerie di apprendimento. “Nessuna dipendenza runtime Python” non equivale a “nessuna dipendenza o costo operativo”. [Workspace](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/Cargo.toml#L29-L39).

La licenza è Apache-2.0. Riutilizzando codice occorre conservare quanto richiesto da licenza e NOTICE, e distinguere l'attribuzione legale dalla citazione scientifica. Il NOTICE contiene anche riferimenti a componenti dello stack precedente: per un'integrazione reale vanno esaminati i file distribuiti e le dipendenze effettive. [Licenza](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/LICENSE), [NOTICE](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/NOTICE).

Lo stato dei workflow e dei controlli associati al nuovo SHA non è stato accertato. **Questo non dimostra né CI passata né assenza di CI:** il risultato resta non verificato per lo snapshot aggiornato. Non sono stati compilati o eseguiti i sorgenti esterni. I controlli su uno SHA diverso non certificano questo commit.

### 5.9 Piano di valutazione proposto, senza modifiche applicate

La scelta più prudente non è “costruire tutto” o “importare tutto”. Sono possibili tre prove distinte:

| Prova | Scopo | Primo requisito |
|---|---|---|
| API ospitata | Misurare un router operativo con minima infrastruttura nuova | Attribuire tutte le generazioni al budget e fissare candidati |
| Libreria originale incorporata | Usare politica e implementazione upstream mantenendo contabile proprio | Adattare richieste, risposte, stato e chiamate intermedie |
| Adattamento Python di una politica | Valutare il meccanismo nel sistema esistente | Dichiarare adattamento e differenze dall'originale |

Un adattamento non deve chiamarsi “riproduzione esatta di Switchyard”. Una prova API non deve chiamarsi “Plan/Execute” se il servizio non offre quella politica.

Sequenza suggerita:

1. **R1:** completare la validazione della qualità dei siti; rende interpretabile ogni confronto successivo.
2. **R2:** scegliere la stessa coppia di modelli e gli stessi strumenti per baseline e prova instradata; verificare entrambi singolarmente.
3. **Pilota di integrazione:** iniziare con la politica più osservabile, senza cambiare contemporaneamente compressione, prompt, effort e strumenti.
4. **R3/R4:** valutare intervento del forte su errori o checkpoint; distinguere advisor operativo e valutatore finale.
5. **Prima di R6:** congelare configurazione, versione, provider, storia inviata e politica della cache. I compiti finali non devono scegliere le soglie.
6. **R7 eventuale:** studiare apprendimento solo se dati e obiettivo giustificano il costo; non serve per utilizzare gli altri percorsi già pronti.

Un confronto aggiuntivo H, singolo agente con alternanza dei medesimi modelli, permetterebbe di confrontare C contro una soluzione più vicina del solo forte B. Va introdotto soltanto come decisione esplicita sul protocollo, con proprio preventivo. C contro H misura l'intera differenza della configurazione: scomposizione, coordinamento, contesti separati e controllo. Non identifica automaticamente l'effetto causale di una sola leva.

### 5.10 Che cosa si può affermare nella tesi

Affermazioni sostenute:

- Esistono politiche operative riutilizzabili che non richiedono un nuovo addestramento.
- Gli esperimenti pubblici mostrano punti favorevoli della relazione costo/qualità, ma anche casi in cui l'economico singolo è preferibile.
- Le spese interne del router e gli effetti della cache possono cambiare la convenienza.
- La trasferibilità a costruzione e valutazione dei siti resta una domanda sperimentale.
- La contribuzione di OrcV2 può concentrarsi sull'integrazione e sulla scomposizione misurata dei benefici, già coerentemente con D36.

Affermazioni non sostenute:

- “Switchyard garantisce la stessa qualità con il 75% di risparmio.”
- “Il router preaddestrato Prefill è pronto per i nostri siti.”
- “Tre candidati producono una scelta appresa a tre livelli nell'API ospitata.”
- “Il prezzo distingue automaticamente il modello migliore da quello peggiore.”
- “Il giudice conosce il pool concreto e tutti gli strumenti.”
- “I risultati di replay provano l'esito di una traiettoria reale.”
- “Collegare base_url basta a conservare la contabilità di OrcV2.”

La scelta operativa resta aperta; l'evidenza giustifica un pilota, non una sostituzione anticipata dell'architettura o una promessa sui risultati della campagna.

### 5.11 Stato delle verifiche e indice delle fonti

**Verificato attraverso fonti primarie:** snapshot e metadati del commit, catalogo e configurazioni, sorgenti dei meccanismi citati, release, licenza, documentazione OpenRouter, risultati pubblicati e loro condizioni.

**Ricavato da analisi statica:** percorsi di fallback capability, compatibilità iniziale dei campi degli strumenti, punti in cui l'attribuzione attuale OrcV2 richiede adattamento, differenza fra massimo punteggio Prefill e vincolo economico della tesi.

**Non verificato dal vivo:** installazione su macOS del pacchetto scelto, comportamento reale su tutti i fornitori, addebiti del giudice e loro riconciliazione, API OpenRouter nell'account del progetto, saturazione delle sessioni, stress e cancellazione, trasferibilità dei risultati ai siti, non inferiorità, stato CI del nuovo SHA.

Le fonti sono collegate sul punto cui si riferiscono. Per ricostruire l'analisi, i gruppi principali sono: [catalogo](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/routing_algorithms/overview.md), [architettura](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/architecture.md), [sorgenti libsy](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/crates/libsy/src/lib.rs), [schema configurazione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/docs/reference/toml_schema.md), [benchmark e qualificazione](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/DEEPSWE_V11_QUALIFICATION.md), [SWE-Atlas](https://github.com/NVIDIA-NeMo/Switchyard/blob/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9/benchmark/SWE_ATLAS_ESCALATION_REPORT.md), [API ospitata](https://openrouter.ai/docs/guides/routing/routers/switchyard-router). Tutti i link GitHub in questa sezione fissano lo stesso SHA salvo commit e release indicati esplicitamente.

<a id="sezione-6"></a>
## 6. Conduit: apprendimento, feedback e limiti del riuso

Data di verifica: 22 ottobre 2026. Repository esatto: https://github.com/ashita-ai/conduit (non altri progetti omonimi).
Snapshot del codice: [e93981c0d9304fc7fbff21b3771a77d81429ec2b](https://github.com/ashita-ai/conduit/commit/e93981c0d9304fc7fbff21b3771a77d81429ec2b), ultimo commit sul ramo principale del 29 gennaio 2026. Analisi statica e verifiche GitHub/API; nessun codice esterno eseguito, nessun pacchetto installato, nessuna chiamata a modelli e nessuna modifica al codice OrcV2.

### 6.1 Giudizio e collocazione

Conduit è utile soprattutto come repertorio di algoritmi semplici da confrontare e di contratti per raccogliere feedback, NON come infrastruttura da inserire integralmente nel progetto attuale. Per R7 può diventare un confronto esterno, dopo un adattamento piccolo e dichiarato. Non risolve R1 (qualità dei siti), né costituisce una prova pubblicata del claim della tesi. Non è uno swarm né un agente di ingegneria del software: sceglie un modello per una query.

L'osservazione più importante: la versione corrente NON fa per default routing in base al tipo di domanda. Il suo Thompson Sampling predefinito apprende un punteggio globale per modello, ignorando le caratteristiche della richiesta nella scelta. Il README mescola questo comportamento con quello opzionale dei router contestuali.

Per la tesi è un vantaggio poter distinguere chiaramente:
- sistema/organizzazione del lavoro e ablazioni (contributo centrale attuale OrcV2);
- apprendimento della scelta del modello (eventuale R7);
- misura affidabile della qualità (R1), che ogni router deve ricevere dall'esterno.

### 6.2 Identità, stato, manutenzione, licenza

- GitHub dichiara repository archiviato dal **23 aprile 2026**, quindi in sola lettura. Fonte: [pagina repository](https://github.com/ashita-ai/conduit).
- Ultimo commit main 29 gennaio 2026, SHA sopra; l'endpoint GitHub releases restituisce elenco vuoto. Il package si dichiara versione 0.1.0, Development Status Alpha: [pyproject.toml:1-20](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/pyproject.toml#L1-L20).
- La CI dell'ultimo commit main è effettivamente **success**, compresi Unit Tests, Integration Tests, Type Check, Lint & Format e Coverage Report: [run 21489599530 del 29 gennaio](https://github.com/ashita-ai/conduit/actions/runs/21489599530). Le PR automatiche successive non vanno scambiate per lo stato del ramo main.
- Non sono stati riconfermati i numeri esatti “1000+ test” e “91% coverage”: sono dichiarazioni README; i log dei tre job richiesti rispondono 410 (non più disponibili). Il tree contiene 77 file di test. Il workflow richiede copertura almeno 80%, una condizione differente dalla copertura 91% dichiarata: [CI:89-203](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/.github/workflows/ci.yml#L89-L203).
- Licenza MIT, copyright Evan Volgas 2025: consente uso/modifica/distribuzione mantenendo avviso di copyright e licenza nelle copie o porzioni sostanziali. Non serve copiare tutta l'infrastruttura per riusare un algoritmo, ma la provenienza deve rimanere dichiarata. [LICENSE](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/LICENSE).

Questo stato non rende il codice inutilizzabile; rende invece OrcV2 responsabile di mantenimento, compatibilità e correzioni se lo incorpora.

### 6.3 Architettura reale

Percorso principale:
Query -> Router.route -> filtro di costo opzionale -> HybridRouter -> QueryAnalyzer -> scelta bandit -> RoutingDecision.

L'esecuzione della chiamata è separata: ModelExecutor usa PydanticAI, oppure il plugin ConduitRoutingStrategy si collega a LiteLLM. Dopo l'esecuzione il chiamante invoca Router.update con modello, costo, qualità, latenza e caratteristiche della query.

Un “bandit” è un algoritmo che prova diverse alternative e riutilizza quelle con risultati migliori; un “braccio” è qui un modello. “Contestuale” significa che sceglie anche in funzione della richiesta corrente, invece di imparare un unico vincitore medio.

#### 6.3.1 Default non contestuale; transizione solo su richiesta

[Router:91-124](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/router.py#L91-L124) usa algorithm="thompson_sampling". [Router:209-275](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/router.py#L209-L275):

```python
"thompson_sampling": {
    "phase1_algorithm": "thompson_sampling",
    "phase2_algorithm": "linucb",
    "switch_threshold": float("inf"),
},
"linucb": {
    "phase1_algorithm": "thompson_sampling",
    "phase2_algorithm": "linucb",
    "switch_threshold": 0,
},
```

L'infinito diventa 999999999 nella costruzione: limite pratico che impedisce la transizione nel normale utilizzo. Per una transizione dopo 2000 query occorre scegliere esplicitamente hybrid_thompson_linucb. La FAQ secondo cui dopo 2000 query si passa a LinUCB descrive dunque un'opzione, non il default corrente.

#### 6.3.2 Thompson Sampling

Tiene per ogni modello una distribuzione Beta(alpha,beta), estrae un campione per ciascuno e sceglie il più alto. I valori iniziali sono alpha=beta=1 per tutti: nessuna preferenza iniziale per un modello qualitativamente migliore. Le caratteristiche della query NON partecipano alla selezione.

[Thompson:140-159, 222-251](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/thompson_sampling.py#L140-L159):

```python
sample_array = np.random.beta(alphas, betas)
selected_id = max(samples, key=samples.get)

window_data = list(self.reward_history[model_id])
self.alpha[model_id] = self.prior_alpha + sum(c * r for r, c in window_data)
self.beta[model_id] = self.prior_beta + sum(
    c * (1.0 - r) for r, c in window_data
)
```

r è il reward composito, c il peso di fiducia del feedback. Questo usa reward frazionari come osservazioni parziali; NON converte il reward in esito binario come lo pseudocodice del README. La soglia 0.85 serve a contare successi per le statistiche, non a decidere gli aggiornamenti.

La finestra mobile consente di dimenticare dati vecchi. Il default del wrapper Router viene da Settings e conserva 1000 osservazioni per modello; il default del costruttore del singolo algoritmo è invece storia illimitata. Nota sul costo di calcolo: anche senza finestra il metodo ricalcola le somme dell'intera storia a ogni aggiornamento; non è l'aggiornamento incrementale O(1) suggerito nella docstring. Nel wrapper con finestra 1000 il lavoro rimane limitato.

#### 6.3.3 LinUCB

LinUCB stima il reward per modello come funzione lineare di un vettore di caratteristiche x e aggiunge un premio all'incertezza per esplorare alternative poco conosciute:
score_m = theta_m^T x + alpha sqrt(x^T A_m^-1 x).
Dopo ogni risposta aggiorna A_m += x x^T e b_m += reward x; theta_m = A_m^-1 b_m.

[LinUCB:146-193 e 232-318](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/linucb.py#L146-L193). L'inversa è mantenuta con aggiornamenti di rango uno (Sherman-Morrison), evitando un'inversione completa a ogni passo.

x è embedding della query + token_count normalizzato + complexity_score. L'embedding è una rappresentazione numerica del testo; non equivale a una misura validata della difficoltà di generare una pagina. [base.py:421-458](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/base.py#L421-L458).

**Difetto concreto:** BanditFeedback.confidence viene documentato come peso anche per LinUCB, ma LinUCB.update non lo legge e aggiorna con pieno peso. Ridurre la fiducia di un feedback non lo rende meno influente con questo algoritmo. Confrontare [contratto base:70-88](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/base.py#L70-L88) con [update LinUCB:232-318](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/linucb.py#L232-L318). È una conclusione statica, non una riproduzione eseguita.

**Altra riserva sul warm start:** la conversione Thompson->LinUCB ricostruisce A identità e mette la media appresa solo in b[0]; x[0] è la prima coordinata dell'embedding, NON una costante/intercetta. Quindi il trasferimento non conserva una qualità globale indipendente dalla query: dipende dal valore, anche negativo, di quella coordinata. [state_conversion:324-379](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/state_conversion.py#L324-L379). Non lo adotterei senza riesame.

#### 6.3.4 Confidence non è probabilità di qualità

La confidence esposta in RoutingDecision è una formula basata sul numero di feedback/pull:
- fase 1: min(.95, .1 + .25 log10(pulls+1));
- fase 2: min(.99, pulls/1000), salvo zero pull -> .1.

Non stima P(qualità >= soglia | query), non è calibrata su siti, e non deve essere usata come sostituto del giudice o come garanzia di non inferiorità. [hybrid_router:588-622](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/hybrid_router.py#L588-L622).

### 6.4 Obiettivo ottimizzato: diverso dalla tesi OrcV2

La formula effettiva è:
R = w_q q + w_c/(1+costo_USD) + w_t/(1+latenza_secondi).
[reward_calculation:65-96, 99-130, 231-246](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/core/reward_calculation.py#L65-L96).

```python
return 1.0 / (1.0 + cost)

reward = (
    quality_weight * quality_norm
    + cost_weight * cost_norm
    + latency_weight * latency_norm
)
```

È una somma pesata di qualità, costo e velocità: può accettare una perdita di qualità se compensata dagli altri termini. NON implementa min costo sotto vincolo qualità >= tau. Dire “la qualità pesa il 70%, quindi è garantita” sarebbe scorretto.

Inoltre la scala dollari comprime le differenze dei costi piccoli. Esempio calcolato (non misurato), con w_c=.2, w_q=.7, stessa latenza:
- costo $0.001 -> efficienza .999001;
- costo $0.01 -> efficienza .990099;
- il guadagno di reward del modello dieci volte meno caro è solo .0017804;
- equivale a circa .002543 di qualità sulla scala 0-1, cioè .2543 punti su 100.
Una lieve differenza nei voti può quindi dominare una riduzione di costo di dieci volte. Non c'è una scala normalizzata al costo del baseline o al budget.

**Incoerenza dei default:** README e YAML dicono .7/.2/.1; il wrapper Router costruisce reward_weights dai Settings che, senza override di ambiente, sono .5/.3/.2. I costruttori dei bandit singoli usano .7/.2/.1. Non è lecito indicare un unico default senza specificare il percorso e la configurazione. [Router:201-207](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/router.py#L201-L207), [Settings:103-117](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/core/config/settings.py#L103-L117).

### 6.5 Il feedback è il vero problema scientifico

#### 6.5.1 Feedback manuale: una buona separazione di responsabilità

Router.update accetta dall'esterno costo, qualità, latenza e caratteristiche. FeedbackCollector separa l'associazione query/risposta dall'arrivo del voto, offre adapter per giudizi umani/successo del task e deduplicazione. Idea utile per OrcV2: registrare quale scelta è stata fatta, su quale oggetto, e quale esito le viene attribuito. [collector:163-219, 221-307](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/feedback/collector.py#L221-L307).

La deduplicazione evita di apprendere due volte dallo stesso evento. Non chiamerei però il metodo una transazione affidabile: consuma la pending query prima della update, poi marca processato; se la update fallisce la query è già stata rimossa. Da controllare se si riusa il componente.

#### 6.5.2 Il feedback automatico LiteLLM non misura qualità software

Nel percorso di successo, feedback.py aggiorna subito il bandit con una qualità euristica: parte da base_quality=.9, penalizza risposta vuota/corta, ripetizioni e scarso overlap di parole con la domanda.

[feedback:447-496](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit_litellm/feedback.py#L447-L496):

```python
quality = cfg["base_quality"]
if len(response_clean) < cfg["min_response_chars"]:
    quality -= cfg["penalties"]["short_response"]
overlap = self._keyword_overlap(query_text, response_clean)
if overlap < cfg["thresholds"]["keyword_overlap_very_low"]:
    quality -= cfg["penalties"]["no_keyword_overlap"]
```

Questo può rilevare alcuni guasti evidenti, ma non distingue sito funzionante da codice plausibile, non apre browser, non misura interazioni, persistenza o estetica. Codice scorretto lungo e ricco delle parole giuste può ricevere un buon punteggio.

L'Arbiter opzionale è avviato dopo la update euristica e in background. Nel metodo esaminato salva il risultato nel database; NON chiama Router.update una seconda volta con quel voto. Non è stato identificato in questo percorso un consumo successivo automatico del voto Arbiter che sostituisca quello euristico.
- [feedback:163-211](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit_litellm/feedback.py#L163-L211)
- [Arbiter:171-212](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/evaluation/arbiter_evaluator.py#L171-L212)

Arbiter confronta output=response.text con reference=query.text usando semantic/factuality. La richiesta non è una soluzione di riferimento, e questi criteri non sono le due metriche di OrcV2 (“funziona”, “piace”). Non adottare questo giudice per R1.

#### 6.5.3 Attribuzione dell'esito nello swarm

Conduit si adatta naturalmente a query -> modello -> risposta -> voto. In OrcV2 una pagina finale dipende da piano, sezioni, integrazione e critica. Dare lo stesso voto della pagina a tutte le chiamate farebbe apprendere premi e colpe non attribuibili al singolo worker. Il componente raccoglie eventi; non risolve l'attribuzione causale né la differenza tra successo locale di una sezione e qualità globale della pagina.

### 6.6 Costo del router, contabilità e budget

#### 6.6.1 Overhead reale non zero

Il selettore Beta è leggero, ma la route corrente chiama QueryAnalyzer.analyze ANCHE in fase non contestuale, poi ignora le caratteristiche per selezionare. [hybrid_router:408-420](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/hybrid_router.py#L408-L420):

```python
features = await self.analyzer.analyze(query.text)
dummy_features = QueryFeatures(
    embedding=[0.0] * 384,
    token_count=len(query.text.split()),
    complexity_score=0.5,
    query_text=query.text,
)
arm = await self.phase1_bandit.select_arm(dummy_features)
```

Su cache miss analyze chiama il provider embedding: [analyzer:176-227](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/analyzer.py#L176-L227). Provider remoto può aggiungere costo, latenza, rete, errori e un altro fornitore; provider locale implica tempo/risorse e dipendenze. I tempi 200ms/5ms presenti nella docstring sono obiettivi/esempi, non una misura replicata qui.

Il costo di embedding non è un campo di RoutingDecision né entra nel Response.cost del ModelExecutor esaminato. Il costo Arbiter viene tenuto separato. In tesi bisogna sommare selezione, etichettatura e tentativi falliti, e distinguere sviluppo da inferenza finale.

#### 6.6.2 Pricing non sostituisce il ledger OrcV2

compute_cost legge prezzi inclusi nella versione installata di LiteLLM; non legge una fattura del fornitore. Supporta tariffe input/output e lettura/scrittura cache, ma:
- ModelExecutor estrae input/output/cache_read; non passa cache_creation_tokens a compute_cost.
- Non sottrae cache_read dall'input: compute_cost assume input escluso cache. Se l'SDK restituisce input inclusivo della cache, il chiamante deve adattare la semantica per non contare due volte.
- Nessun trattamento esplicito di reasoning token separati nel percorso; potrebbe essere coperto se l'SDK li include nell'output, ma non è dimostrato indipendentemente.
- Il lookup recupera la tariffa base; non applica davvero scaglioni per contesto lungo malgrado la docstring dichiari “tiered pricing support”.
- Per modello sconosciuto usa $10/M input e $30/M output; non sono un upper bound universale né un costo misurato.
- Se non riesce a interpretare usage, ModelExecutor può tornare 0.0.
Fonti: [pricing:85-125 e 162-221](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/core/pricing.py#L162-L221), [executor:239-290](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/executor.py#L239-L290).

Il plugin LiteLLM prova a prendere response_cost dai metadati; se assente nel successo salta il feedback per non registrare costo zero. Buona scelta, ma resta da verificare cosa comprenda il costo del gateway/fornitore reale.

#### 6.6.3 “Max cost” non è un tetto di spesa di squadra

CostFilter stima output = input * output_ratio (default 1), conteggia solo query.text e usa una codifica tiktoken fissa. Non è il totale di messaggi di sistema, strumenti, ragionamento, storia e output realmente generati. Se nessun modello rientra nel budget, il default rilassa il vincolo e seleziona il più economico. [cost_filter:68-83, 130-148, 185-225](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/cost_filter.py#L130-L148).

In più il bandit sceglie prima su tutti i modelli: se il vincitore è escluso, HybridRouter prende il modello ammesso con expected_quality più alta, NON massimizza il punteggio appreso fra quelli ammessi. [hybrid_router:332-348 e 420-428](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/hybrid_router.py#L420-L428).

Mantenere OrcV2 accounting/ledger.py, accounting/team.py e budget_guard.py; il selettore eventuale non deve riscrivere la contabilità.

### 6.7 Evidenza sperimentale: cosa dimostra e cosa manca

### Test veri, ma prevalentemente verifica meccanica

test_feedback_loop_improves_routing dà a mano ai due modelli qualità uguale .95, costi .001/.10, latenze .5/.8. Dopo 40 domande di training chiede che almeno il 70% di 50 nuove scelte vada al modello economico. Usa LinUCB esplicito e abbassa alpha a .1. Gli embedding sono uguali per tutte le query nella fixture globale. Questo verifica che differenze nel feedback cambiano le scelte; NON dimostra qualità di risposte reali, generalizzazione semantica, risparmio su siti, cold-start del default Thompson o conservazione della qualità.
- [test:15-88](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/tests/integration/test_feedback_loop.py#L15-L88)
- [fixture:33-72](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/tests/conftest.py#L33-L72)

Il test hybrid abbassa soglia da 2000 a 20 per esercitare il cambio di algoritmo; non misura quante query vere servano a convergere. [test:110-174](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/tests/integration/test_feedback_loop.py#L110-L174).

Non è stato identificato nel tree a questo SHA un dataset di benchmark, un harness scientifico completo, split train/test pubblicato o risultati grezzi che provino una percentuale di risparmio su task reali. Il README attuale dice correttamente che i risparmi dipendono dal workload. La nota notes/2025-11-19_benchmark_strategy_analysis.md contiene numeri 64%, 35k query e $284, ma li presenta in un documento di pianificazione/posizionamento: NON è un rapporto di esperimenti eseguiti. Rimanda inoltre a docs/BENCHMARK_STRATEGY.md, docs/BANDIT_TRAINING.md e docs/COLD_START.md che non sono nel tree corrente. Non citare quei numeri come risultati misurati.

### Citazione scientifica non trasferibile

Aggiornamento di verifica: il [sito degli autori](https://ashita.ai/projects/conduit/) riporta risultati preliminari su MMLU e GSM8K e dichiara rapida convergenza. È una fonte esterna al tree corrente, da distinguere dalla nota commerciale. La pagina non pubblica configurazioni complete, split o risultati grezzi sufficienti a riprodurre quei numeri con questo snapshot; non costituisce una validazione su siti web.

Il README sostiene superiorità cold-start di Thompson citando [Reward Model Routing in Alignment, arXiv 2510.02850](https://arxiv.org/abs/2510.02850). Il paper studia la selezione dei reward model nell'allineamento RLHF/RLAIF, con apprendimento offline e priors Gaussiani contestuali, non questo Conduit con Beta(1,1) globali. Lavoro interessante come related work, ma NON valida direttamente il claim cold-start di questa implementazione.

### 6.8 Due problemi da correggere prima di usare Conduit come baseline

### Baseline always_cheapest/always_best non configurate correttamente nel wrapper

HybridRouter costruisce ogni ModelArm con costo input=0, output=0, expected_quality=.5: [hybrid_router:183-194](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/hybrid_router.py#L183-L194).
AlwaysCheapest seleziona minimo della media dei due campi costo; AlwaysBest massimo di expected_quality:
[baselines:265-278](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/baselines.py#L265-L278), [baselines:352-368](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/baselines.py#L352-L368).

Quindi nel percorso Router(algorithm=...) i modelli sono tutti pari: entrambe le baseline possono scegliere semplicemente il primo elemento della lista. Il commento “looked up dynamically” non effettua quel lookup dentro queste baseline. Le classi funzionano se ricevono direttamente bracci correttamente valorizzati. Per OrcV2 B e D vanno comunque selezionati esplicitamente dal registro, non tramite questi nomi.

### Oracle non è ancora il nostro limite costo-qualità

OracleBaseline.update memorizza quality_score, non reward composito o minimo costo sotto soglia. La chiave usa l'hash del vettore di caratteristiche e il modello; senza risultati di tutti i modelli sulla stessa richiesta il nome “oracle” non conferisce conoscenza perfetta. [baselines:114-195](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/engines/bandits/baselines.py#L114-L195).
Un limite teorico per la tesi andrebbe definito sui risultati effettivi di B/C/D per compito e dichiarato come selezione a posteriori, non un router implementabile.

### 6.9 Integrazione OrcV2: plugin, fork o piccola estrazione?

### Plugin integrale: sconsigliato ora

- Aggiunge una seconda via di esecuzione con PydanticAI/LiteLLM, potenzialmente diversa per strumenti, streaming, retry, contesto e misura.
- Dipendenze obbligatorie ampie: FastAPI, uvicorn, sklearn, numpy, Redis, asyncpg, SQLAlchemy, Alembic, Supabase, osservabilità e altro. Python >=3.11. LiteLLM è dichiarato extra ma importato direttamente da pricing.py: installazione minima da verificare. [pyproject:22-72](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/pyproject.toml#L22-L72).
- settings = Settings() all'import legge anche .env; questo collide con la convenzione esplicita OrcV2 di configurare solo dal punto d'ingresso. [Settings:16-18, 282-283](https://github.com/ashita-ai/conduit/blob/e93981c0d9304fc7fbff21b3771a77d81429ec2b/conduit/core/config/settings.py#L282-L283).
- README dichiara niente streaming nelle risposte. OrcV2 ha un gateway con streaming, watchdog e riconciliazione dei costi: sostituirlo aumenterebbe rischio e renderebbe meno equi i bracci.
- Repo archiviato, contratto alpha, incongruenze rilevate.

### Fork integrale: fattibile ma non proporzionato alla roadmap

Permesso dalla MIT, ma bisogna assumere mantenimento dell'intero sistema. Non serve a R1 e può allargare il lavoro senza produrre più evidenza sul claim centrale.

### Piccola estrazione/adattatore: la scelta sensata se R7 serve

Portare solo la politica decisionale e contratto di feedback, mantenendo:
- AgentFactory.make_gateway in agent_factory.py:313 per eseguire tramite gateway esistente;
- ModelRegistry.cost in accounting/registry.py:122 per i prezzi;
- RunLedger in accounting/ledger.py:21 e TeamAccountant in accounting/team.py:45 per i consumi;
- BudgetGuard in budget_guard.py:19 per la policy di spesa;
- giudizi R1 e protocollo per gli esiti.

Dato che il default Thompson ignora il contesto, potrebbe servire solo come controllo “scegli il migliore in media”; non deve diventare il confronto principale con il router grossolano per tipo di pagina. Un adattamento dell'algoritmo con pochi campi selezionati avrebbe meno superficie di rischio.

### 6.10 Mappa nella roadmap vigente

| Fase | Cosa prendere | Cosa non trasferire |
|---|---|---|
| R1 | Separazione fra evento di generazione e voto; registro dell'origine del feedback; prove della pipeline con voti sintetici | Euristiche di qualità testuale, Arbiter semantic/factuality, “confidence” come qualità |
| R4.0/R4 | Inventario comparativo e costo del selettore; eventuale analisi se il workload varia abbastanza da giustificare routing | Migrazione del gateway, nuove dipendenze come prerequisito; ottimizzazione sui voti del test |
| R6 | Baseline esplicite always-strong/always-cheap/random, curva costo-qualità e ablation del selettore; training cost separato | Le baseline Conduit preconfezionate nel wrapper; training online silenzioso sul test; percentuali README come evidenza |
| R7 | Thompson non contestuale come controllo; LinUCB contestuale come confronto esterno a parametri congelati, SOLO se dati e tempo giustificano | Promessa di apprendimento robusto con 5 compiti; soglia 2000 ridotta arbitrariamente e chiamata “validata” |

OrcV2 oggi ha 5 compiti di sviluppo, non migliaia di query indipendenti etichettate. Fare centinaia di chiamate interne a quei 5 siti non crea centinaia di siti indipendenti: condividono specifica e dipendenze. Train/test devono essere divisi per compito/pagina, non per chiamata.

R7 è facoltativa e segue R6 nella roadmap. Non porterei il router in R3 per giustificare la scoperta del repository. Il contributo oggi è il sistema e la scomposizione misurata del risparmio, più la valutazione (ROADMAP:45-47; R6:575-618; R7:622-625).

### 6.11 Esperimento consigliato, se si decide di provarlo in futuro

1. Prima misurare B/C/D con lo stesso harness e giudice R1. Non cambiare il protocollo principale per adattarlo al repository.
2. Definire l'unità di scelta: intera pagina o componente. Per R7 è naturale la pagina (“subito Opus o OrcV2”); Conduit nasce con bracci=modelli, ma una politica bandit astratta può scegliere strategie. Sarebbe un adattamento, non integrazione fedele del prodotto.
3. Cominciare dal confronto più economico offline: metodi statici per tipo, Thompson globale, eventualmente LinUCB con poche caratteristiche motivate; nessun embedding pagato senza preventivo. Il feedback deve provenire dallo stesso metro delle altre strategie.
4. Training e selezione iperparametri solo sullo sviluppo; politica congelata sul test. Se si vuole davvero studio online, ordine temporale prefissato, aggiornamento solo dopo ogni esito, costi di esplorazione inclusi e protocollo differente esplicito.
5. Non scegliere la soglia 0.85 o i pesi per far vincere il metodo. La tesi chiede non inferiorità su due metriche, non massimizzazione di una media arbitraria.
6. Distinguere costo di training/etichettatura/embedding/correzioni da costo finale d'uso; mostrare se e quando il risparmio ammortizza l'apprendimento.
7. Con dati piccoli presentarlo come esplorazione con incertezza; nessuna promessa di superiorità generalizzata.

Priorità: R1 e qualità del protocollo -> sistema R3/R4 e ablazioni R6 -> eventualmente confronto router R7. Conduit può aiutare a formulare quest'ultimo bene, ma non sposta da solo il baricentro scientifico della tesi.

<a id="sezione-7"></a>
## 7. NadirClaw: servizio standard, librerie e numeri di ricerca

### 7.1 Perimetro e giudizio

Analisi in sola lettura del commit `8a75cdb647dc392de4498c02e86ed90962c08214`, pubblicato il 21 ottobre 2026 come [v0.25.1](https://github.com/NadirRouter/NadirClaw/releases/tag/v0.25.1). Contesto OrcV2 riferito alla roadmap e al protocollo vigenti. Nessun codice OrcV2 modificato, nessuna installazione/esecuzione di codice esterno, nessuna chiamata LLM pagata. Le conclusioni sul comportamento derivano da lettura del sorgente; i test citati sono eseguiti dalla CI pubblica, non da questa analisi.

**Giudizio:** molto interessante come esempio industriale di proxy e come controesempio metodologico; non lo adotterei intero come nuovo fondamento di OrcV2. Le idee migliori sono l'esplicitazione dei motivi di instradamento, il percorso economico → verifica → escalation e gli esperimenti separati sulla compressione. Tuttavia, quel percorso di verifica esiste come libreria ma non risulta collegato al server standard, il percorso automatico con strumenti forza il modello forte, il contabile non soddisfa i requisiti sperimentali di OrcV2 e parte dei numeri pubblicizzati appartiene a configurazioni diverse dal servizio effettivamente avviato. Il contributo corrente di OrcV2, sistema e scomposizione del risparmio a qualità non inferiore, resta distinto; la sua utilità richiede il confronto sperimentale.

### 7.2 Cosa fa davvero il codice

È un proxy HTTP compatibile con OpenAI, con superficie Anthropic aggiuntiva, classificazione della richiesta, scelta di un modello, gestione errori e catena di modelli alternativi. Non è uno sciame che scompone e assegna sezioni di un sito. L'interfaccia `auto` significa selezione automatica; `eco`, `premium`, `free`, `reasoning` forzano categorie configurate. La superficie Anthropic conserva il corpo originale, instrada il nome del modello e inoltra al server Anthropic: [server.py:2850-2878](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L2850-L2878).

Il classificatore effettivamente selezionato è, di default, una media vettoriale per categoria: trasforma il testo in vettore con MiniLM e confronta la vicinanza ai centri `simple` e `complex`. `confidence` qui è la differenza assoluta fra due similarità, non una probabilità di correttezza della soluzione. I casi vicini al confine vengono mandati al modello forte. La trasformazione successiva in `complexity_score` è una regola manuale. [classifier.py:184-213](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/classifier.py#L184-L213), [classifier.py:284-316](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/classifier.py#L284-L316).

Sono presenti anche pesi di una rete wide-and-deep: un ramo analizza proprietà strutturali e lessicali, l'altro un vettore BGE; una piccola porta logistica decide quando mandare al livello complesso. La libreria è utilizzabile direttamente, ma il factory che il server chiama accetta solo `binary`, `distilbert`, `morph`; qualsiasi altro valore ricade su binary. **La presenza dei pesi non equivale alla loro attivazione nel proxy.** [classifier.py:334-371](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/classifier.py#L334-L371), [server.py:538-555](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L538-L555), [wide_deep_classifier.py:250-334](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/wide_deep_classifier.py#L250-L334).

#### Frammento 1: default reale e scelta del classificatore

```python
# settings.py:167-181
return os.getenv("NADIRCLAW_COMPLEXITY_ANALYZER", "binary").strip().lower()
# classifier.py:347-370, abbreviato
kind = settings.COMPLEXITY_ANALYZER_TYPE
if kind == "distilbert": ...
elif kind == "morph": ...
_active_classifier = get_binary_classifier()
```

La [MODEL_CARD:15-25](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/MODEL_CARD.md#L15-L25) chiama `v3+gate` default dalla 0.22: è corretto per il costruttore diretto della libreria wide/deep, non per il factory del servizio. Da qui un rischio concreto di riprodurre una configurazione diversa da quella creduta.

#### Frammento 2: con uno strumento il percorso automatico forza il modello forte

```python
if has_tools and tool_count >= 1:
    score += 0.35
if agentic["is_agentic"] and final_tier == "simple":
    final_model = complex_model
```

[Rilevamento](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/routing.py#L301-L347), [override](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/routing.py#L1093-L1115). Per un normale agente OrcV2 con strumenti, una classificazione `simple` viene sostituita con `complex`: l'opzione conservativa può essere sensata per un prodotto, ma toglie proprio molte occasioni di risparmio che interessa studiare. Non dimostra che il modello economico fallirebbe; impedisce di osservarlo. L'override non si applica ai profili forzati o al modello indicato direttamente, che però non costituiscono routing automatico.

### 7.3 Verifica della qualità: libreria presente, servizio standard diverso

`Cascade` e `NTierCascade` realizzano il tentativo economico, la verifica della risposta e il passaggio al successivo livello. Il verificatore di default usa regole: risposta vuota, formule di rifiuto, incertezza, lunghezza e JSON parsabile. Non esegue un sito, non verifica un endpoint e non controlla che una patch soddisfi il compito. Una risposta lunga e convincente ma falsa può ottenere 1.0. La libreria ignora l'eventuale risposta di riferimento nella variante euristica. [heuristic_verifier.py:135-214](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/heuristic_verifier.py#L135-L214).

Esiste una variante DeBERTa scaricata da Hugging Face, input massimo 512 token per coppia, che riceve prompt e blocco CHEAP/EXPENSIVE. La risposta di riferimento può essere vuota; questo non autorizza a trasferire le metriche ottenute con riferimento al caso senza riferimento. Inoltre 512 token sono inadatti a valutare un sito, un intero workspace o un lungo ciclo di strumenti. [trained_verifier.py:62-75](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/trained_verifier.py#L62-L75), [trained_verifier.py:216-285](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/trained_verifier.py#L216-L285).

Il motore di regole evita di fidarsi del verificatore nei domini deboli: basta `def ` o `function ` nel prompt per imporre escalation; il commento dichiara AUROC 0.65 su codice. Questo rafforza la scelta OrcV2 di controlli eseguibili sul prodotto. [default.yaml:21-71](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/cascade_rules/profiles/default.yaml#L21-L71).

**Punto d'integrazione mancante verificato:** nel server, sia il ramo normale sia quello in streaming chiamano dispatch/fallback per errori, senza istanziare `Cascade`, `NTierCascade` o chiamare un verificatore. Il solo profilo YAML `n2_trained` non viene letto da `get_classifier`/`_smart_route_analysis` e non trasforma questo endpoint nel percorso a cascata descritto dal README. Non significa che la libreria di cascata non funzioni; significa che per usarla in quel servizio occorrerebbe collegarla esplicitamente.

#### Frammento 3: la chiamata del servizio è fallback per errori

```python
# server.py:1682-1686
if not cache_hit:
    with trace_span("chat_completion", {"nadirclaw.tier": analysis_info.get("tier")}) as span:
        response_data, selected_model, analysis_info = await _call_with_fallback(
            selected_model, request, provider, analysis_info,
        )
```

[server.py:1677-1703](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L1677-L1703), [gestione errori:1245-1328](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L1245-L1328). La distinzione conta nella tesi: errore di rete ≠ output semanticamente insufficiente. Nella libreria `NTierCascade`, un guasto del verificatore fa accettare comunque la risposta e dopo errori ripetuti disabilita la verifica: una scelta di disponibilità del prodotto, non garanzia di qualità. [cascade.py:667-681](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/cascade.py#L667-L681).

### 7.4 Numeri pubblicati e riproducibilità

Il README attuale ammette chiaramente che i numeri RouterBench — 98.3% qualità preservata e circa 60% risparmio — sono un **limite di ricerca con risposta del modello costoso disponibile al verificatore**, non prestazioni della produzione. È una distinzione corretta e da mantenere citandoli. Un sistema online dovrebbe pagare anche quel riferimento se lo genera. [README:92-111](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/README.md#L92-L111).

La model card dichiara per il classificatore solo-prompt AUROC circa 0.62 fuori famiglia: in parole semplici, conoscere il tipo di domanda è molto meno informativo che conoscere la qualità della risposta. AUROC misura quanto il punteggio separa casi che richiedono escalation dagli altri; non è percentuale di siti corretti. Il corpus etichettato del classificatore è interno e non presente qui. La funzione per confrontare impronte dei prompt è pubblica, ma senza il corpus interno non si può verificare autonomamente il loro zero-overlap né riaddestrare gli stessi pesi. E un confronto con impronte identiche non esclude parafrasi o dati semanticamente sovrapposti. [MODEL_CARD:82-106](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/MODEL_CARD.md#L82-L106), [MODEL_CARD:124-127](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/MODEL_CARD.md#L124-L127), [audit:179-217](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/verifier/contamination_audit.py#L179-L217).

**Verifica esterna di RouterArena:** nella [PR112, risultato automatico](https://github.com/RouteWorks/RouterArena/pull/112#issuecomment-4584540505), il valutatore riporta su 8.400 richieste score 0.7333, accuratezza 74.87%, costo per mille $0.2932 e robustezza 0.2548. Sono quattro metriche diverse; robustezza qui riguarda stabilità del routing quando il prompt viene perturbato. Non è tasso di correttezza delle risposte.

Nella stessa PR, il [maintainer](https://github.com/RouteWorks/RouterArena/pull/112#issuecomment-4589739499) ha segnalato che il successivo commit, poi unito, differiva da quello valutato: circa il 45% delle scelte cambiava e il file di robustezza copiava esattamente le predizioni originali, mostrando un 100% non valido. Ha ripristinato i file del commit effettivamente valutato `bdfee64`. L'[autore ha ammesso e corretto l'errore](https://github.com/RouteWorks/RouterArena/pull/112#issuecomment-4592918751), confermando robustezza reale 25.48%, con 313 cambiamenti su 420 prompt perturbati. **È un episodio corretto e riconosciuto; non prova un intento doloso e non annulla tutto il progetto.** Impone però di citare l'esatto risultato valutato, non i numeri 0.7358/0.7518 ancora presenti in alcune schede o l'invalido 100%. Per OrcV2: fissare stesso commit di predizioni, modello, codice e verbale di valutazione, come già previsto dal protocollo.

La [scheda Hugging Face](https://huggingface.co/nadirclaw/cascade-verifier-v1) espone pesi e percorso d'inferenza, ma non il training; inoltre indica MIT mentre LICENSE GitHub attuale è PolyForm Noncommercial. Anche le latenze dichiarate differiscono fra paragrafi della scheda (10/60 ms) e model card GitHub (193 ms): non assumere un costo d'inferenza certo senza misura propria. Le prestazioni di question-answer in inglese non validano webapp multi-turno né non inferiorità su «funziona» e «piace».

La demo di risparmio non genera le risposte: assume 180 token d'uscita per ogni prompt e prezzi fissati nel file, diversi dal registro usato dal server. In particolare la demo Opus 4.6 usa 15/75 dollari per milione, il registro di routing usa 5/25 per la propria voce Opus 4.6. Questa è un'incoerenza interna verificabile, senza esprimere un giudizio sul listino odierno dei fornitori. Il risparmio visualizzato è un calcolo dimostrativo, non una misura qualità/costo. [demo:49-64](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/demo/cost_vs_opus.py#L49-L64), [routing:149-156](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/routing.py#L149-L156).

### 7.5 Costi, cache, budget e conversazioni

Il budget è un allarme successivo alla spesa, non una prenotazione e non un tetto vincolante. Il costo deriva da token input/output e registro statico; modello ignoto diventa 0.0. Non contabilizza in modo distinto letture/scritture di cache del fornitore, chiamate dei router remoti né tutti i tentativi falliti. Per la campagna OrcV2, dove il costo è la variabile principale, questo non sostituisce il ledger esistente.

#### Frammento 4: risposta riusata dalla cache conteggiata come nuova spesa

```python
# server.py:1704-1716, abbreviato
else:
    analysis_info["strategy"] += "+cache-hit"
budget_status = get_budget_tracker().record(
    selected_model,
    response_data["prompt_tokens"],
    response_data["completion_tokens"],
)
# budget.py:153
cost = estimate_cost(model, prompt_tokens, completion_tokens) or 0.0
```

[server:1704-1716](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L1704-L1716), [budget:148-185](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/budget.py#L148-L185). La cache locale evita la chiamata ma conserva usage originale e il tracciatore incrementa ancora i totali: è un difetto di contabilizzazione verificato dal flusso, non riprodotto con esecuzione. Il risultato può anche esporre al client usage non corrispondente a nuova fatturazione. Un esperimento con repliche identiche entro 300 secondi può quindi riusare la stessa risposta senza che il contabile lo rappresenti correttamente.

La cache delle risposte è in memoria, attiva per default sulle richieste senza streaming, conserva tutti i messaggi e i parametri che influenzano il contenuto; buona attenzione a immagini e tool metadata nella chiave. Ma non include un'identità sperimentale della run: in R6 andrebbe spenta o isolata fra repliche. Non confonderla con cache di prompt fatturata dal fornitore. [cache.py:22-83](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/cache.py#L22-L83).

La persistenza del routing mantiene il livello raggiunto per 300 secondi e permette solo promozioni. È utile per stabilità, ma la chiave usa solo i primi 200 caratteri del primo messaggio system/developer e del primo utente, senza identificativo esplicito della run o dell'utente. Due task con preamboli comuni possono condividere involontariamente la scelta: potenziale contaminazione fra compiti, particolarmente probabile in benchmark con cornice identica. È una collisione di contenuto troncato, non una debolezza del SHA-256. [routing.py:759-802](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/routing.py#L759-L802).

Tool calling supportato da LiteLLM: il codice conserva tool_calls, tool_call_id, nome e definizioni. I test relativi sostituiscono il fornitore con risposte simulate: segnale di cura del contratto, non prova su fornitori veri per ogni coppia di modelli. In streaming il modello alternativo viene tentato solo prima che sia stato inviato contenuto; se il flusso si interrompe a metà, il proxy aggiunge un avviso ma chiude con `finish_reason: stop`. Questo sarebbe un rischio per OrcV2, che deve distinguere esplicitamente risultato completo e troncato. [streaming:2301-2333](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/server.py#L2301-L2333), [test tool:104-120](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/tests/test_tool_calling.py#L104-L120).

### 7.6 Compressione: la leva più utile da studiare separatamente

Merito del progetto: un documento distingue i grandi numeri su payload sintetici dai risultati reali. Riporta 1.0% riduzione token su 195 conversazioni WildChat e 8.2% su 200 conversazioni di function-calling in modalità safe; 4.7%/9.6% nella variante aggressiva. Il banco è pubblico ma misura token stimati con un unico tokenizer, non qualità dei risultati dopo la trasformazione né costo end-to-end. Non fissa una revisione del dataset remoto e il ramo Pro può importare un pacchetto fratello non presente, altrimenti ricade sul native: riproducibilità parziale del confronto Pro. [benchmark](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/docs/optimizer-benchmark-2026-06.md), [script](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/benchmarks/optimize_real_data.py).

**Non adottare `safe` come garanzia semantica.** Comprende taglio della storia oltre 40 turni utente. Inoltre la normalizzazione preserva l'indentazione ma comprime spazi all'interno delle stringhe del codice non delimitato: per lettura statica, `label = "A  B"` diventa `label = "A B"`. Un programma può continuare a essere sintatticamente valido e cambiare risultato. La miniatura JSON è reversibile nel dato JSON, ma non equivale a invarianza del comportamento del modello che legge il contesto.

#### Frammento 5: normalizzazione applicata senza analizzare le stringhe

```python
# optimize.py:256-265, abbreviato
n_lead = len(line) - len(line.lstrip(" \t"))
out_lines.append(line[:n_lead] + _MULTI_SPACES.sub(" ", line[n_lead:]))
# optimize.py:804-807: anche in safe
msgs, did_trim = _trim_chat_history(msgs, max_turns=max_turns)
```

[normalize:238-266](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/optimize.py#L238-L266), [trim:273-311](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/optimize.py#L273-L311), [pipeline:793-807](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/optimize.py#L793-L807). In OrcV2 la prova corretta è un'ablazione in R4: compressore spento/acceso a modello fisso, costo totale misurato compresi token di cache, qualità finale del sito, errori di strumenti e latenza. Prima profilare quali messaggi costituiscono la spesa: se domina codice o prosa, non aspettarsi i numeri dei JSON ripetitivi.

### 7.7 Maturità, licenza e adozione concreta

CI attuale su Python 3.10, 3.11, 3.12 verde al commit analizzato. Il log pubblico del job 3.12 riporta: **966 passed, 1 skipped, 14 warnings in 54.10s**. Non sono stati eseguiti test locali del progetto esterno. La suite controlla molti casi, compresi protocollo degli strumenti e fallback, ma questi non eliminano i problemi di collegamento della cascata e contabilità sopra. Il workflow non esegue controllo statico di tipo. [CI](https://github.com/NadirRouter/NadirClaw/actions/runs/39602617650), [configurazione CI](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/.github/workflows/ci.yml).

Le dipendenze includono FastAPI, Uvicorn, LiteLLM, sentence-transformers, NumPy e SDK Google; molte hanno solo un minimo di versione. Non c'è lockfile nel tree analizzato. Il runtime degli embedding aggiunge una pila ML ampia e download iniziale. `settings.py` legge `.env` all'import: incompatibile con la regola OrcV2 di configurare solo al punto d'ingresso. Non importarlo direttamente nel core e aspettarsi test senza effetti sull'ambiente. [pyproject](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/pyproject.toml#L25-L46), [settings:11-18](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/nadirclaw/settings.py#L11-L18).

Il testo LICENSE corrente è **PolyForm Noncommercial 1.0.0**, non MIT e non licenza open-source permissiva. Il testo consente espressamente ricerca, sperimentazione e istruzione non commerciali; per copie distribuite richiede licenza/URL e Required Notice; per uso commerciale indica una licenza separata. Questo vale anche se si copiano parti del codice. Il testo Hugging Face MIT contraddice il riferimento al LICENSE attuale: per pesi/estratti non presumere condizioni permissive dal badge della scheda. [LICENSE](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/LICENSE#L1-L16), [obbligo notices](https://github.com/NadirRouter/NadirClaw/blob/8a75cdb647dc392de4498c02e86ed90962c08214/LICENSE#L50-L58). Qui si riportano le condizioni pubblicate, senza dedurre compatibilità con una futura licenza OrcV2.

| Fase OrcV2 | Riuso utile | Cosa evitare / condizione |
|---|---|---|
| R1 | Esempio per motivare qualità eseguibile invece di scorciatoie testuali | Nessun motivo per sostituire giudice validato e test web con DeBERTa QA |
| R2 | Contratti di tool calling, registrare motivo di fallback e modello effettivo | Non aggiungere proxy invisibile che cambia modello, usage o parametri; ogni tentativo nel ledger e stesso percorso per tutti i bracci |
| R3 | Struttura generale economico → verifica → escalation | La verifica deve riguardare artefatto/sezione e loop OrcV2, non lunghezza della risposta o rifiuti inglesi |
| R4/R4.0 | Profilazione delle sorgenti token e ablazione della compressione; pipeline a trasformazioni indipendenti | Prima misurare qualità/costo end-to-end; niente taglio storia o alterazione codice spacciati per lossless |
| R6 | Controesempio utile per legare score a commit esatto, file predizioni e ripetizioni indipendenti | Cache locale isolata/spenta, modello/fornitore/versione fissati; nessuna percentuale presa da RouterBench come risultato dei siti |
| R7 facoltativa | Baseline centroid o wide/deep da confrontare esternamente, dati e soglia congelati | Solo dopo una prova sul dominio OrcV2; factory reale da controllare, overhead misurato, classificatore non equiparato a verifica qualità |

**Opzioni pratiche:** (a) prodotto intero come laboratorio esterno facoltativo, mai nel mezzo della campagna prima di verifiche proprie; (b) librerie selezionate, con costo di licenza/dipendenze/collegamento e contabilità ancora da risolvere; (c) studiare i pattern e progettare un'integrazione originale minima dentro le interfacce esistenti OrcV2, citando il lavoro e misurando le leve. Raccomando (c) per R2-R4; eventuale (a) come comparatore separato solo in R7 se il tempo lo consente. Copiare il contabile, l'euristica di qualità o l'override strumenti non è una scorciatoia utile per l'attuale contributo della tesi.

<a id="sezione-8"></a>
## 8. Router preaddestrati e servizi API: catalogo approfondito

Stato delle fonti: 22 ottobre 2026. Questa sezione distingue cio' che e' documentato, cio' che si ricava dalla lettura del codice e le proposte da verificare sperimentalmente. Nessun servizio e' stato chiamato con credenziali, nessun router e' stato installato e nessuna prestazione e' stata misurata su OrcV2.

### 8.1 Risposta alla domanda pratica

Esistono sia router gia' addestrati con pesi scaricabili sia router ospitati accessibili tramite API, cioe' richieste programmatiche a un servizio. L'integrazione di uno di questi componenti non richiede necessariamente addestrare un router originale. Rimane necessario verificare che scelga bene sul dominio dei siti web, con i modelli effettivi del progetto e sui turni successivi alle chiamate agli strumenti.

La parola "pronto" indica almeno tre condizioni diverse:

1. **Pronto come algoritmo:** il software implementa gia' una politica; puo' non contenere alcun modello appreso.
2. **Pronto come pesi:** il risultato dell'addestramento e' scaricabile; servono comunque ambiente di esecuzione, configurazione e misure.
3. **Pronto come servizio:** un fornitore espone il componente; accesso, fatturazione, modelli ammessi e stabilita' della versione possono limitare la prova.

Queste condizioni non sono intercambiabili. Un server compatibile con OpenAI puo' eseguire modelli recenti pur basando la decisione su un classificatore allenato su modelli vecchi. Un classificatore che riconosce "generazione codice" puo' essere pronto senza saper prevedere se un certo modello economico completera' bene quel particolare sito.

#### Catalogo operativo

| Candidato | Componente gia' disponibile | Adattamento necessario per OrcV2 | Collocazione ragionevole |
|---|---|---|---|
| Not Diamond Chat | Selettore preaddestrato via API, con pool esplicito | Verificare disponibilita' degli identificativi esatti e contratto economico | Candidato commerciale da qualificare |
| Not Diamond Code | Servizio per agenti di codice presentato come accesso anticipato | Ottenere accesso e specifiche, inclusa possibilita' di congelare il comportamento | Interesse alto, disponibilita' non confermata |
| Nadir Pro / Decision API | Router commerciale distinto da NadirClaw, con decisione separabile dall'esecuzione | Confermare accesso, catalogo, verificatore e tariffa effettiva | Candidato commerciale con fonti economiche disallineate |
| RouteLLM | Router appresi pubblici, controller e server | Adattare ingresso, calibrare soglia, verificare trasferimento alla coppia nuova | Confronto scientifico riproducibile |
| Arch-Router-1.5B | Modello che abbina richieste a rotte descritte | Definire rotte e collegarle ai modelli; non confondere categorie e difficolta' | Routing grossolano di R7 |
| RouteFM | Router preaddestrati che usano osservazioni dei candidati | Raccogliere esiti, generare vettori delle richieste, definire regola di costo | Ricerca R7, con dati sufficienti |
| OpenRouter Auto | Router ospitato gia' documentato | Fissare impostazioni, pool e registrazione del modello effettivo | Prova operativa semplice, confronto meno stabile |
| OpenRouter Pareto Code | Selezione ospitata secondo fascia di benchmark e prezzo | Verificare catalogo reale e rendere osservabili le scelte | Riferimento commerciale, non previsione della riuscita |

La tabella riassume i dettagli e le fonti delle sezioni successive. Non costituisce una graduatoria di qualita' misurata.

### 8.2 Not Diamond: selettore esterno e possibilita' commerciale

#### 8.2.1 Chat: che cosa documenta davvero

La guida Chat presenta `client.model_router.select_model`: riceve i messaggi e una lista di candidati, restituisce modello e identificativo della raccomandazione. La generazione successiva puo' essere eseguita dal programma chiamante con il proprio client. E' documentata una preferenza opzionale per costo o latenza, mentre l'impostazione ordinaria privilegia la qualita'. Non occorre quindi delegare a Not Diamond il gateway che esegue i modelli. [Guida Chat](https://docs.notdiamond.ai/docs/quickstart-routing).

Questa separazione e' particolarmente adatta a OrcV2: il servizio puo' limitarsi a consigliare, mentre la chiamata continua a passare dalle regole locali di budget, dal fornitore fissato e dal contabile. La decisione va trattata come proposta da validare: se restituisce un modello fuori dalla rosa o non disponibile, la politica locale deve definire in anticipo il comportamento sostitutivo. La scelta del sostituto modifica costo e qualita', quindi deve essere registrata.

#### 8.2.2 Il pool del progetto non risulta confermato

La pagina dei modelli supportati riporta, tra gli altri, GPT-5.5, Opus 4.7, DeepSeek V4 Flash e V4 Pro. Nella lista consultata non compaiono gli identificativi della rosa attuale di OrcV2: `anthropic/claude-opus-5.5`, `openai/gpt-6.1-sol`, `deepseek/deepseek-v4.1-flash-1017`. L'assenza dalla pagina non prova un rifiuto dell'API, ma impedisce di dichiarare verificata la compatibilita'. La stessa pagina prevede nuovi modelli su richiesta e un percorso diverso per candidati personalizzati. [Catalogo statico](https://docs.notdiamond.ai/docs/llm-models).

Esiste inoltre `GET https://api.notdiamond.ai/v2/models`, documentato per restituire modelli attivi e deprecati, prezzi, lunghezza del contesto e corrispondenze OpenRouter; permette filtri per provider e disponibilita' OpenRouter. Questa ricerca ha verificato la documentazione, non la risposta autenticata dell'endpoint. [Riferimento del catalogo](https://docs.notdiamond.ai/reference/list_models_v2_models_get).

La risposta del catalogo live non è stata acquisita in questa verifica. Questo non stabilisce se l'endpoint richieda autenticazione o quale errore HTTP restituisca; la disponibilità dei tre modelli esatti rimane non verificata.

Per il progetto e' un controllo decisivo: sostituire la rosa pur di usare un router cambierebbe anche l'esperimento. Sarebbero da distinguere due domande: "il router aiuta con la rosa di OrcV2?" e "un servizio commerciale con la propria rosa offre un buon sistema complessivo?". La seconda e' legittima, ma non isola l'effetto del router.

#### 8.2.3 Code e prezzo pubblicato: non fondere prodotti diversi

La pagina specifica Code invita ancora a iscriversi per una **early preview**, cioe' accesso anticipato. Il risparmio dichiarato dal fornitore non e' una misura ottenuta sui siti di OrcV2. Non e' stato verificato un account ammesso ne' un endpoint Code utilizzabile dal progetto. [Presentazione Code](https://docs.notdiamond.ai/docs/pre-trained-router-code).

Il sito commerciale pubblica **$0,05 per milione di token instradati**, con richiesta di accesso. Presenta il prodotto come integrazione nel gateway esistente, capace di apprendere continuamente dai risultati delle sessioni; dichiara 100-150 ms medi di latenza aggiunta. Il sito descrive anche analisi di stato della cache, sequenza dei turni e segnali dell'ambiente di lavoro. Sono caratteristiche e numeri del fornitore, da verificare per il contratto effettivamente ottenuto. [Listino e FAQ commerciali](https://www.notdiamond.ai/pricing).

Non e' corretto prendere questo prezzo e applicarlo automaticamente al vecchio endpoint Chat, a ogni versione del client o a un piano gratuito storico. Le fonti consultate non stabiliscono quella equivalenza. Per una prova vanno ottenute le condizioni dell'endpoint specifico, comprese unita' fatturate, minimi, crediti e accesso.

Esempio esclusivamente aritmetico: se la tariffa applicabile fosse davvero $0,05/M e fossero fatturati 20 milioni di token instradati, la sola commissione del router sarebbe $1. Il costo dei modelli scelti, degli eventuali tentativi ripetuti e della valutazione si aggiungerebbe. Non e' un preventivo della campagna, perche' i 20 milioni sono ipotetici e l'unita' fatturata del servizio scelto resta da confermare.

#### 8.2.4 Condizioni per un uso scientifico

Il valore commerciale dell'apprendimento continuo diventa un problema sperimentale se il comportamento cambia mentre si confrontano i bracci. Sarebbe necessario chiarire:

- se si puo' fissare una versione del router;
- se e come disabilitare aggiornamenti da feedback durante il test;
- se l'apprendimento si estende ad altri utenti o sessioni;
- quale informazione riceve il servizio prima della decisione;
- se esiste un'esportazione delle raccomandazioni ripetibile a posteriori;
- come gestire un cambiamento del catalogo o della disponibilita'.

Questi sono requisiti proposti per la prova, non caratteristiche confermate. Senza congelamento, il risultato sarebbe riferito a quel servizio in quelle date: utile come dato operativo, meno adatto a isolare un algoritmo.

**Valutazione:** candidato commerciale serio per selezione senza sostituire il gateway. Il primo passo e' qualificare accesso, rosa e fatturazione. Non e' ancora un componente di cui si possa promettere l'inserimento immediato nella campagna.

#### 8.2.5 Nadir commerciale: non coincide con il codice locale NadirClaw

Anche Nadir offre un servizio: la documentazione distingue una **Decision API**, che restituisce raccomandazioni su modello, ragionamento, cache e contesto senza chiamare il fornitore, e un proxy ospitato compatibile con OpenAI. L'indice documenta endpoint come `/v1/recommend` e `/v1/route`. Nel percorso proxy il verificatore successivo alla risposta e' facoltativo e limitato a risposte complete non in streaming. Non e' stata verificata un'abilitazione per OrcV2, un catalogo autenticato o una chiamata reale. [Documentazione commerciale](https://getnadir.com/docs/).

Il README del 22 ottobre, al commit `5f60ffe753e30499daa3738bf89f21e884bc9df9`, presenta Pro con classificatore addestrato e verificatore distinto dalle euristiche locali di Claw. La stessa revisione dichiara nessuna commissione Nadir con chiavi proprie e commissione del 5,5% sui crediti con chiavi gestite. Sono condizioni del README datato, non una fattura verificata. [README fissato](https://github.com/NadirRouter/NadirClaw/blob/5f60ffe753e30499daa3738bf89f21e884bc9df9/README.md).

Le fonti economiche non sono allineate: la pagina prezzi consultata descrive ancora una commissione sui risparmi misurati per l'esecuzione ospitata e condizioni pilota, fisse o a consumo per Decision API; il riepilogo macchina del sito conserva un modello economico precedente. Non e' corretto presentare una tariffa unica come confermata per tutti i percorsi. Prima di spendere serve una risposta sul servizio e piano effettivamente utilizzabili. [Prezzi pubblici](https://getnadir.com/pricing/), [riepilogo del sito](https://getnadir.com/llms.txt).

Per OrcV2 la Decision API e' interessante per la stessa ragione del selettore Not Diamond: potrebbe lasciare l'esecuzione nel gateway esistente. Bisogna pero' verificare che il classificatore commerciale sia disponibile sul pool richiesto, che il verificatore non sia necessario per ottenere i risultati dichiarati e che il costo totale sia ricostruibile. I risultati di ricerca con una risposta forte di riferimento non dimostrano la qualita' del servizio che lavora senza quella risposta.

### 8.3 RouteLLM: pesi pronti, ma trasferimento e conversazioni da verificare

#### 8.3.1 Cosa e' disponibile

RouteLLM e' un lavoro di ricerca sul routing fra un modello forte e uno economico tramite dati di preferenza: confronti in cui una risposta viene preferita all'altra. Il paper, pubblicato inizialmente il 26 giugno 2024 e rivisto il 23 febbraio 2025, studia anche il trasferimento a coppie di modelli diverse da quelle originarie. Questo rende il riuso plausibile, ma non dimostra la validita' sulla rosa del 2026 ne' sui siti del progetto. [Paper, versione 4](https://arxiv.org/abs/2406.18665v4).

Il codice consultato e' fissato al commit `0b64fdafe049e596a3f5657c219329f24af24198`, ultimo commit di `main` restituito dall'API durante la ricerca, del 10 agosto 2024. Il repository offre controller Python e server compatibile con OpenAI, con una soglia che decide quanto spesso ricorrere al forte. La libreria supporta endpoint vari attraverso LiteLLM e il codice del progetto ha licenza Apache-2.0. La compatibilita' dell'esecuzione e' distinta dalla validita' della decisione. [README fissato](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/README.md), [licenza](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/LICENSE).

#### 8.3.2 Varianti e costi nascosti

Il controller include configurazioni pubbliche per `mf`, `bert`, `causal_llm` e `sw_ranking`. Le prime tre indicano checkpoint gia' addestrati; la quarta usa dati di confronti e rappresentazioni delle richieste. [Configurazione reale](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/controller.py#L12-L26).

| Variante | Interpretazione operativa | Vincolo da considerare |
|---|---|---|
| `mf` | Incrocia una rappresentazione della richiesta con rappresentazioni apprese dei modelli | Nel percorso standard chiama l'API per produrre il vettore della richiesta |
| `bert` | Classificatore testuale locale | Possibile taglio dei testi lunghi; non e' addestrato alla storia completa dell'agente |
| `sw_ranking` | Ripesa confronti storici in base alla somiglianza della richiesta | Richiede dati e vettori, con calcolo di classifiche alla richiesta |
| `causal_llm` | Modello generativo utilizzato come classificatore | Runtime piu' impegnativo e licenza del modello di base da controllare separatamente |

Nel codice `mf` il vettore viene ottenuto con `text-embedding-3-small`: un **embedding** e' una lista di numeri che rappresenta il contenuto del testo per confrontarlo e usarlo come ingresso matematico. I pesi del router possono essere locali mentre questa parte rimane una chiamata esterna. Cambiare l'encoder, cioe' il modello che produce quei numeri, non e' una sostituzione automaticamente equivalente. [Percorso MF](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/matrix_factorization/model.py#L85-L119).

La scheda pubblica MF riporta circa 205 mila parametri e nessun servizio d'inferenza gia' collegato; quella BERT circa 0,3 miliardi. Un parametro e' un coefficiente appreso: queste dimensioni descrivono i classificatori, non il costo completo dell'infrastruttura. Entrambe le schede risultano prive di una vera model card esplicativa. La licenza del repository non sostituisce una verifica delle condizioni di ogni peso e dei dati. [Pesi MF](https://huggingface.co/routellm/mf_gpt4_augmented), [pesi BERT](https://huggingface.co/routellm/bert_gpt4_augmented).

#### 8.3.3 Il punto piu' delicato: modello chiamato e modello usato nel punteggio

In `mf`, la coppia usata per produrre il punteggio puo' essere distinta dalla coppia che riceve davvero le chiamate. Il default per il punteggio e' GPT-4-1106-preview contro Mixtral-8x7B-Instruct. Non basta cambiare il nome dei destinatari per trasformare i pesi in una stima calibrata di Opus 5.5 contro DeepSeek V4.1. La tabella interna degli identificativi e' legata ai modelli presenti nei dati originali. [Router MF e commento sulla distinzione](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/routers.py#L202-L240).

Per OrcV2, un risultato positivo con la rosa attuale sarebbe quindi una **prova di trasferimento**, da presentare come tale. Un risultato negativo potrebbe dipendere dal dominio, dalla coppia o dalla rappresentazione dei turni: non dimostrerebbe che tutto il routing appreso e' inutile.

#### 8.3.4 Un limite direttamente leggibile nel controller

Il percorso standard legge `messages[-1]["content"]`: usa il contenuto dell'ultimo messaggio. Un commento spiega che i router sono stati addestrati su dati di primo turno. Il codice non costruisce da solo una rappresentazione dell'intero stato dello sciame. [Controller, punto di estrazione](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/controller.py#L96-L106).

Questo e' molto rilevante: dopo un comando l'ultimo messaggio puo' essere un errore di compilazione, una porzione di file o un elenco di righe. Un router che legge solo quel testo potrebbe non sapere il requisito del sito, il ruolo del worker, i tentativi gia' falliti o il budget residuo. Concatenare un riassunto strutturato e' una possibile integrazione, ma cambia l'ingresso su cui il classificatore e' stato studiato; va trattata come scelta sperimentale propria.

#### 8.3.5 La soglia non garantisce qualita'

La soglia confronta un punteggio del router con un valore stabilito. Calibrarla per ottenere una certa quota di chiamate al forte non significa garantire il superamento dei controlli del sito o la non inferiorita' estetica. Per il progetto avrebbe senso scegliere la soglia solo sui compiti di sviluppo, poi mantenerla fissa. Un confronto casuale con la stessa quota di chiamate forti aiuterebbe a verificare se il classificatore sa scegliere *quali* turni meritano il forte, oltre a ridurre semplicemente la sua frequenza.

**Valutazione:** e' la risposta piu' chiara a "esistono pesi gia' addestrati da integrare?". Si', ma il costo dell'embedding, il carattere binario e il primo turno sono limiti concreti. Buon confronto riproducibile se affrontati esplicitamente; nessuna garanzia di vantaggio in OrcV2.

### 8.4 Arch-Router-1.5B: riconoscere la rotta non equivale a prevedere la riuscita

Arch-Router usa un modello da 1,5 miliardi di parametri per abbinare la conversazione a descrizioni di domini e azioni definite dall'utilizzatore. Il prompt di esempio elenca rotte come generazione di codice, correzione di errori e aiuto con API; l'uscita identifica una rotta. Sono disponibili pesi e istruzioni Transformers. Il documento raccomanda il proprio formato d'ingresso. [Scheda ufficiale](https://huggingface.co/katanemo/Arch-Router-1.5B).

Il paper del 19 giugno 2025 presenta il metodo come allineamento alle preferenze espresse tramite domini e azioni, consentendo di aggiungere candidati senza riaddestrare il classificatore. I risultati riguardano l'abbinamento a quelle preferenze, non una misura diretta della non inferiorita' dei siti prodotti. [Paper](https://arxiv.org/abs/2506.16655).

Applicazione plausibile per R7: descrivere una rotta per modifiche isolate del server e una per integrazione complessa dell'interfaccia, collegandole a modelli ammessi. Il valore dipenderebbe dalla validita' della mappa stabilita. Se si assegna "correzione bug" all'economico, il classificatore impara a riconoscere quella categoria; non segue che ogni bug sia abbastanza semplice per l'economico. La difficolta' puo' variare enormemente dentro la stessa categoria.

**Licenza da non semplificare.** L'etichetta della scheda dice `katanemo-research`, mentre il file LICENSE letto è un Katanemo Community License Agreement datato 2 aprile 2026, basato sul contratto Llama e riferito a DigitalOcean. Prevede condizioni per ridistribuzione e attribuzione, e richiede una licenza separata per usi commerciali. Non va presentato come Apache-2.0. La revisione della licenza è `5b156890a91b1035a86f82faf1a651debf309009`. [LICENSE fissato](https://huggingface.co/katanemo/Arch-Router-1.5B/blob/5b156890a91b1035a86f82faf1a651debf309009/LICENSE), [revisione](https://huggingface.co/katanemo/Arch-Router-1.5B/commit/5b156890a91b1035a86f82faf1a651debf309009).

**Valutazione:** candidato per categorie di lavoro gia' comprese, con mappa esplicita e verificabile; meno diretto per rispondere alla domanda "bastera' il modello economico su questo turno?". Occorre conservare la licenza della revisione effettivamente usata.

### 8.5 RouteFM: alternativa recente con pesi pubblici e candidati nuovi

RouteFM e' pertinente perche' distingue l'identita' del candidato dalle sue prestazioni osservate. Il modello preaddestrato riceve esempi precedenti di qualita' e costo dei candidati e una nuova richiesta; non necessita di aggiornare i propri parametri per ogni nuova rosa. Sono pubblicati due router: BGE, testuale, di circa 11,1 milioni di parametri, e Qwen, per testo e immagini, di circa 12,8 milioni. Gli encoder esterni non sono inclusi nei pesi. [Modello e pesi](https://huggingface.co/AIGNLAI/RouteFM), [paper](https://arxiv.org/abs/2609.37362).

Per una fonte fissata si puo' usare RouteFM 1.0.1, commit `e7e650610850eee055016ed1dab06f08e833663b`, tag del 29 settembre 2026. Codice e pesi del router sono Apache-2.0; dati ed encoder mantengono condizioni proprie. Il rilascio scarica artefatti a revisione fissata e ne controlla l'impronta, cioe' un valore calcolato sui byte per riconoscere esattamente il file. [Rilascio fissato](https://github.com/LAMDA-Model-Reuse/RouteFM/blob/e7e650610850eee055016ed1dab06f08e833663b/README.md).

#### 8.5.1 "Senza riaddestramento" non significa "senza dati"

Il contratto per dati personalizzati richiede almeno un esito osservato per ogni candidato. Occorrono vettori delle richieste, punteggi confrontabili su scala 0-1 e costi non negativi in un'unita' coerente. Il default sceglie il candidato con massima qualita' prevista; il costo previsto e' relativo, non calibrato in dollari, e non entra nella scelta ordinaria. Il router non chiama i modelli per raccogliere questi esiti. [Contratto dei dati, versione fissata](https://github.com/LAMDA-Model-Reuse/RouteFM/blob/e7e650610850eee055016ed1dab06f08e833663b/docs/CUSTOM_DATA.md).

Per OrcV2 il dato minimo di una riga per candidato sarebbe un requisito software, non una numerosita' sperimentale adeguata. Inoltre il progetto misura due qualita', "funziona" e "piace"; comprimere entrambe in uno scalare per alimentare il router sarebbe una scelta nuova. Si potrebbe studiare un solo aspetto inizialmente, ma andrebbe dichiarato e non sostituirebbe i due esiti della valutazione finale.

E' importante anche l'unita' della decisione. Un esito sull'intero sito non e' automaticamente un'etichetta della qualita' del singolo turno del worker. Se il router sceglie per sottocompito, servono osservazioni riferite a sottocompiti confrontabili; altrimenti si rischia di attribuire al modello locale l'esito del resto dello sciame.

#### 8.5.2 Riproducibilita' e risultati da non mescolare

La documentazione del rilascio distingue un benchmark multimodale e le sue partizioni di contesto e obiettivi. Il README fissato avverte che lo split con seme 31010 e' stato scelto dopo averne esaminati diversi: va descritto come dimostrazione selezionata a posteriori. La model card corrente separa quei risultati dal protocollo del paper. Non vanno unite in una sola tabella come se fossero misure identiche. [Protocollo degli artefatti](https://github.com/LAMDA-Model-Reuse/RouteFM/blob/e7e650610850eee055016ed1dab06f08e833663b/docs/MMRBENCH_V1.md).

**Valutazione:** alternativa promettente per una R7 con evidenza sui candidati nuovi. Il lavoro necessario si sposta dall'addestramento del router alla raccolta di osservazioni valide, all'encoder e alla politica che concilia costo e due metriche. Non e' la via piu' breve per completare R1-R3.

### 8.6 Router ospitati OpenRouter: disponibilita' pratica e limiti di metodo

#### 8.6.1 Auto Router

`openrouter/auto` e' documentato come servizio che usa il tipo di compito e la spesa aggregata degli utenti negli ultimi sette giorni. Consente liste di modelli ammessi/esclusi e fasce `low`, `medium`, `high`, `xhigh`, `max`: sono fasce, non tetti di costo. Restituisce il modello effettivo e supporta continuita' di sessione. Si paga il modello scelto senza commissione aggiuntiva di Auto. La documentazione non identifica il metodo con un predittore calibrato della qualita' dei siti. [Guida ufficiale Auto](https://openrouter.ai/docs/guides/routing/routers/auto-router).

Per OrcV2 la facilita' operativa e' reale, ma il criterio basato sul mercato introduce variabilita' nel tempo. Anche fissando il pool, un esperimento in due settimane diverse potrebbe avere politiche diverse. Una prova del servizio dovrebbe pertanto registrare data, impostazioni e scelte, evitando di descriverla come algoritmo congelato. L'elenco ammesso restringe i candidati, ma non garantisce che tutti siano eleggibili per ogni richiesta o fascia; un filtro puo' svuotare l'insieme.

Il tetto locale della run resta necessario: limitare il prezzo unitario o scegliere una fascia non limita automaticamente token, tentativi e numero di turni. Il servizio e' candidato a una prova commerciale, non una prova preventiva del rispetto del budget di squadra.

#### 8.6.2 Pareto Code

`openrouter/pareto-code` sceglie da una lista curata di modelli di codice in base a fasce del percentile Artificial Analysis. `min_coding_score` viene tradotto in tre fasce; la scelta ordinaria prende il meno caro disponibile, la variante `:nitro` privilegia la velocita'. Sono documentati fallback tecnici e risposta con modello effettivo. La lista e le fasce evolvono. Quel numero e' posizione in una classifica, non probabilita' di risolvere la richiesta. [Guida ufficiale Pareto](https://openrouter.ai/docs/guides/routing/routers/pareto-router).

Il nome puo' suggerire un'ottimizzazione specifica per richiesta, ma il meccanismo documentato e' piu' semplice: fissare una fascia di capacita' generale e risolvere per prezzo/disponibilita'. Non sostituisce la verifica del risultato e non garantisce la soglia di non inferiorita' del protocollo OrcV2. Può essere utile come confronto "modello economico fra quelli in una certa fascia", dichiarando l'aggiornamento esterno del catalogo.

#### 8.6.3 Differenza rispetto a Switchyard

Auto e Pareto rispondono soprattutto a quali modelli scegliere da un catalogo. Le politiche sequenziali di Switchyard consentono anche di studiare quando cambiare modello durante il lavoro. Non bisogna confondere disponibilita' sullo stesso fornitore con identita' degli algoritmi, dei costi interni o del trattamento delle sessioni. La sezione specifica Switchyard deve fissare esattamente quali strategie esistono nel servizio ospitato e quali solo nella libreria.

### 8.7 Integrazione: selettore soltanto oppure proxy

#### 8.7.1 Selettore soltanto

Flusso proposto: il componente riceve le informazioni ammesse, restituisce un candidato; OrcV2 valida che sia nella rosa e nel budget, poi usa il proprio gateway. Questo separa l'algoritmo di decisione dal meccanismo di esecuzione. E' il percorso naturale per Not Diamond Chat e per adattamenti locali di classificatori.

Il contratto minimo da progettare, non ancora implementato, dovrebbe riportare: candidato scelto, versione o configurazione, motivo/punteggio quando disponibile, costo e durata della decisione, eventuale comportamento sostitutivo. Il punteggio va etichettato per cio' che significa: somiglianza, preferenza stimata e probabilita' calibrata sono cose diverse.

#### 8.7.2 Proxy che esegue anche le chiamate

Il gateway locale invia una richiesta a un nome virtuale e il servizio esegue il modello scelto, eventualmente altri passaggi. E' pratico per i servizi OpenRouter, ma la contabilita' deve ricostruire tutti gli addebiti. Se un nome come `auto` sostituisce la voce del modello senza conservare l'identita' effettiva, il listino locale non sa piu' applicare il prezzo giusto. Se sono coinvolti giudici, consiglieri o risposte scartate, il costo della sola risposta finale puo' essere incompleto.

Per entrambe le modalita' occorre misurare **costo totale per sito**, includendo decisioni, modelli, errori fatturati e recuperi, oltre al tempo. La verifica del sito resta esterna al router.

### 8.8 Una selezione concreta, senza promettere una scorciatoia

La raccomandazione e' mantenere un numero limitato di candidati con domande diverse:

1. **Switchyard ospitato:** prima via per provare politiche sequenziali gia' disponibili, dopo aver verificato rosa, strategia, costi e sessioni.
2. **Not Diamond:** qualificazione dell'offerta commerciale prima di pianificare spesa o integrazione; interessante per evitare un nuovo proxy.
3. **RouteLLM MF o BERT:** riferimento pubblico con pesi congelabili; prova esplicita di trasferimento, non garanzia di prestazioni.
4. **RouteFM:** candidato successivo se la raccolta degli esiti produce contesto sufficiente e comparabile.
5. **Arch-Router, Auto, Pareto:** utili per domande circoscritte, rispettivamente categorie, selezione guidata dal mercato e selezione entro fascia di benchmark.

L'ordine non aggiunge automaticamente bracci alla campagna. Prima conviene risolvere R1 e disporre di strumenti comuni: senza una valutazione credibile, non si distingue un risparmio valido da un sito peggiore. Le prove di sviluppo devono selezionare una politica; il test finale misura la scelta gia' fissata. Provare molte politiche sugli stessi compiti di test e scegliere dopo la migliore renderebbe ottimistico il risultato.

La conclusione utilizzabile nella tesi e': **il componente di routing puo' essere riusato o acquistato; il contributo di OrcV2 resta la sua integrazione controllata nel sistema e la misura di quali leve riducono il costo conservando le due qualita'.** Non sarebbe corretto presentare come router originale un classificatore esterno, ne' trasferire al proprio dominio i risparmi pubblicizzati dai fornitori.

### 8.9 Verifiche ancora aperte prima di integrare

| Verifica | Stato al 22 ottobre 2026 | Perche' cambia la decisione |
|---|---|---|
| Not Diamond ammette la rosa esatta OrcV2? | Non confermato; catalogo statico non la elenca | Potrebbe richiedere accesso o cambiare i candidati |
| Tariffa applicabile al selettore Chat specifico | Non confermata | Il prezzo commerciale non basta a identificare l'endpoint |
| Accesso Code e possibilita' di bloccare l'apprendimento | Non confermati | Necessari per disponibilita' e confronto stabile |
| RouteLLM su storie di strumenti e modello 2026 | Non eseguito | Primo turno e coppia storica possono non trasferire |
| RouteLLM: licenze dei pesi e basi scelte | Da verificare per artefatto | Apache del codice non copre automaticamente ogni asset |
| Arch-Router: licenza e prestazioni sul sottodominio | Licenza letta, runtime non provato | Classificazione per categoria potrebbe non dare risparmio |
| RouteFM: osservazioni valide per ogni candidato | Non raccolte in questa analisi | I pesi pronti non eliminano il bisogno di esiti |
| Servizi OpenRouter: filtro della rosa, errori, contabilita' | Solo documentazione | La compatibilita' non prova rispetto del budget |
| Miglioramento di costo e qualita' su OrcV2 | Nessuna misura nuova | E' la domanda sperimentale, non una premessa |

<a id="sezione-9"></a>
## 9. Integrazione in OrcV2: tre strade concrete e i loro contratti

Le sezioni sui prodotti stabiliscono ciò che esiste. Questa sezione descrive come potrebbe entrare nel progetto senza assumere che l'integrazione sia già stata approvata o implementata.

### 9.1 Strada A: selettore esterno, esecuzione interna

```text
Compito e stato del lavoro
    → candidati ammessi dal registro
    → selettore, locale oppure via API
    → modello scelto e motivazione
    → gateway OrcV2 del modello effettivo
    → consumi nel ledger e risultato all'agente
```

Il selettore restituisce una scelta, non necessariamente la risposta al compito. È il caso documentato dalla selezione Not Diamond e una possibile modalità di riuso di router locali. Il vantaggio è mantenere la via esistente per strumenti, interruzioni, contabilità e vincoli dei fornitori. Il costo della raccomandazione va registrato a sua volta; se il servizio non lo espone per decisione, la riconciliazione e il costo totale del lotto diventano un requisito.

È necessario verificare la compatibilità fra i nomi dei candidati ammessi e quelli accettati dal selettore. Non basta che un nome appartenga alla stessa famiglia: versioni, provider e impostazioni possono cambiare le prestazioni. Un catalogo statico che non elenca un modello attuale richiede una verifica del catalogo live o una procedura documentata di registrazione del modello; non autorizza a inventare un alias.

### 9.2 Strada B: libreria di routing incorporata

```text
Agente OrcV2 → adattatore della politica
                   ↘ richieste intermedie del router
                   ↘ chiamata finale al modello
             ogni chiamata passa dal contabile
```

Il contratto della libreria deve rendere visibili anche le richieste intermedie. Una decisione può richiedere zero chiamate, una classificazione, più consulti o una nuova generazione. Il principio di separare decisione ed esecuzione presente in Switchyard è utile, ma il collegamento effettivo tra rappresentazioni dei messaggi e callback va provato.

L'integrazione completa della libreria può essere opportuna per riprodurre un prodotto preciso. L'adattamento di una politica piccola può essere più proporzionato alla roadmap. Nel secondo caso il risultato deve essere descritto come adattamento ispirato alla politica, non come prestazione della libreria originale.

### 9.3 Strada C: proxy ospitato o locale

```text
Agente → richiesta a un nome di router
       → decisioni e chiamate nel servizio
       → risposta e metadati al chiamante
```

È la strada con meno infrastruttura locale quando si usa un servizio già ospitato. La prova scientifica richiede però che la configurazione del router, la rosa di modelli e la misura delle chiamate interne siano identificabili. Non bisogna chiamare il servizio genericamente e poi attribuire tutto l'uso a un solo prezzo del registro.

Per Switchyard su OpenRouter il modello servito è riportato nella risposta, mentre le chiamate del giudice sono generazioni distinte. Ne consegue un requisito di riconciliazione: stabilire come attribuirle al compito e se il costo restituito dalla risposta finale le comprende oppure no. Non si deve presumere tale inclusione. [Guida del servizio](https://openrouter.ai/docs/guides/routing/routers/switchyard-router).

### 9.4 I punti effettivi nel codice

**Modello scelto alla costruzione.** In [agent_factory.py:399](/Users/vincenzomattioli/Documents/OrcV2/agent_factory.py:399):

```python
model = self.registry.model_for(role)
```

Il metodo [accounting/registry.py:201](/Users/vincenzomattioli/Documents/OrcV2/accounting/registry.py:201) legge l'assegnazione del ruolo:

```python
return self.roles[role]["model"]
```

L'attuale costruzione seleziona quindi un modello per l'agente. Un router per turno richiede una nuova responsabilità esplicita: selezionare il gateway del modello scelto mantenendo sessione, stato dell'agente e contabilità. Scegliere invece il modello una volta per pezzo è una modifica di granularità diversa. La distinzione va fatta nella specifica, prima di progettare l'interfaccia.

**Modello usato per prezzare.** In [llm_gateway.py:196](/Users/vincenzomattioli/Documents/OrcV2/llm_gateway.py:196):

```python
record = self.mapper.to_record(
    response, model=self.model, latency_s=latency_s, attempt=attempt,
    api_provider=self.api_provider, billing_provider=self.billing_provider,
)
```

In [accounting/mappers/openai.py:33](/Users/vincenzomattioli/Documents/OrcV2/accounting/mappers/openai.py:33):

```python
return {
    "model": model,
    "api_provider": api_provider,
    "billing_provider": billing_provider,
```

Il nome passato dal gateway resta quindi una chiave della misura. Se diventa `nvidia/switchyard` o un altro alias variabile, occorre risolvere il modello effettivo e il prezzo pertinente, oppure separare in modo esplicito costo riportato e costo non calcolabile. Il nome del router e il nome del modello servito sono entrambi utili ma non intercambiabili.

**Il fornitore effettivo non è il modello effettivo.** In [accounting/record.py:124](/Users/vincenzomattioli/Documents/OrcV2/accounting/record.py:124):

```python
reported_cost: float | None = None
served_by: str | None = None
```

`reported_cost` conserva il costo dichiarato dal servizio. `served_by` descrive il fornitore che ha risposto. Non costituisce già un campo universale che risolve il modello scelto da un proxy. La rappresentazione streaming ha un campo `model`, in [stream_assembler.py:113](/Users/vincenzomattioli/Documents/OrcV2/stream_assembler.py:113):

```python
id: str | None
model: str | None
provider: str | None
```

La presenza del dato nella risposta ricomposta non dimostra che sia già usato come chiave del listino. È un buon punto da cui partire per la futura specifica, non una compatibilità già completa.

**Vincolo sul fornitore.** In [agent_factory.py:344](/Users/vincenzomattioli/Documents/OrcV2/agent_factory.py:344):

```python
corpo: dict[str, Any] = {}
if ordine:
    corpo["provider"] = {"order": list(ordine), "allow_fallbacks": False}
```

Il progetto controlla già quale endpoint serve il modello. Un vincolo valido per un modello può escluderne un altro nella richiesta a un router; inoltre può escludere il giudice interno. Per una rosa di famiglie diverse bisogna definire la semantica dei vincoli per candidato e verificare i motivi di esclusione. Il router deve scegliere fra candidati realmente disponibili, non fra etichette astratte.

**Tetto osservato e tetto preventivo.** In [budget_guard.py:70](/Users/vincenzomattioli/Documents/OrcV2/budget_guard.py:70):

```python
if total_cost_usd >= tetto:
    return BudgetVerdict.HARD_LIMIT_REACHED
```

Il guardiano attuale controlla la spesa già osservata prima della chiamata successiva. Non è una prenotazione monetaria del caso peggiore della nuova richiesta e non copre automaticamente chiamate invisibili del proxy. Anche il sistema esistente ha questo limite: l'integrazione deve renderlo misurabile, non attribuirgli una garanzia non implementata.

### 9.5 Contratto minimo della decisione

È una proposta di dati da discutere, non una nuova interfaccia pubblica già approvata:

| Campo concettuale | Perché serve |
|---|---|
| Identità di compito, run, agente e pezzo | Non mescolare sessioni e attribuire i consumi |
| Versione di politica, pesi, prompt e soglie | Riprodurre la decisione e distinguere cambiamenti |
| Candidati prima e dopo i filtri | Riconoscere esclusioni per capacità, provider, contesto e budget |
| Modello raccomandato e modello effettivamente servito | Riconoscere ripieghi e prezzare la risposta reale |
| Ragione della scelta | Capire se pesa il compito, l'errore, il costo, il caso o una configurazione |
| Tipo di punteggio | Non scambiare similarità, fiducia euristica e probabilità calibrata |
| Generazioni intermedie collegate | Contare giudice, advisor, tentativi e output scartati |
| Uso e costo per fonte | Distinguere valore riportato, calcolo e dato mancante |
| Stato della sessione | Evitare persistenze fra run o modifiche della decisione non registrate |

Se alcuni di questi campi non sono esposti, il limite va dichiarato. Non tutti devono diventare subito nuove classi: prima serve sapere quali dati sono realmente disponibili dal candidato scelto.

### 9.6 Capacità prima del prezzo

La rosa ammissibile deve rispettare le capacità necessarie: strumenti, immagini, schema strutturato, contesto e parametri. Un modello economico che non vede lo screenshot non è una scelta valida per il critico visivo. Una richiesta può essere compatibile al primo turno e superare il contesto dell'economico dopo molti risultati degli strumenti.

Il confronto deve inoltre conservare la semantica del ragionamento e dei messaggi. Non si deve assumere che un blocco proprietario di ragionamento, una firma o un identificativo di continuazione siano trasferibili fra modelli o fornitori. Eliminare un blocco può essere necessario per la compatibilità, ma cambia le informazioni disponibili al successore. Questo effetto fa parte del sistema misurato.

### 9.7 Prove necessarie prima di una campagna

Questa è una lista di criteri di accettazione per una futura integrazione:

1. La selezione è esercitata con candidati controllati e tutte le ragioni sono osservabili.
2. Un ciclo reale di strumento conserva chiamata, risultato e riferimenti agli identificativi dopo un cambio di modello.
3. Due esecuzioni con lo stesso preambolo e compiti differenti non condividono involontariamente sessione o risposta memorizzata.
4. Un modello escluso dai vincoli non può essere scelto silenziosamente; i ripieghi sono riportati.
5. Il totale comprende generazioni intermedie e risposte poi scartate, con riconciliazione al costo del servizio.
6. Un flusso interrotto resta distinguibile da una conclusione completa.
7. Il cambio di modello conserva o ricostruisce il contesto nel modo dichiarato e ne misura il costo.
8. Il tetto riguarda il compito intero; i casi di costo mancante o servizio non prezzabile sono visibili.
9. Nessun componente operativo accede alle domande e agli script riservati al giudizio finale.

Le prove locali con risposte simulate verificano il contratto. Le verifiche con un fornitore vero richiedono preventivo e limite di spesa: non sono state eseguite per questo dossier.

<a id="sezione-10"></a>
## 10. Economia: quali costi possono annullare il risparmio

### 10.1 Un modello di costo completo

```text
Costo del compito = esecutori + planner + verifiche operative
                  + escalation + decisioni di routing
                  + tentativi e lavoro scartato
```

Le categorie sono una scomposizione per responsabilità. Input, output e cache sono le quantità fatturate dentro ciascuna categoria: non si sommano una seconda volta come se fossero chiamate aggiuntive. Il costo del giudice scientifico esterno è una voce del costo della ricerca, da tenere separata dal costo operativo del sistema che genera un sito.

Resta utile registrare anche latenza e picco di concorrenza. Un sistema può spendere meno e impiegare più tempo; oppure accelerare grazie al parallelismo consumando più token. Il risultato deve permettere di vedere la differenza.

### 10.2 Condizione D37 e limiti dell'approssimazione

Il progetto dichiara la condizione in [docs/TESI_master.md:38](/Users/vincenzomattioli/Documents/OrcV2/docs/TESI_master.md:38):

```text
C_C / C_B = m / r + q
Risparmio se m / r + q < 1
```

`C_C` è il costo dello sciame, `C_B` quello del forte singolo. `m` rappresenta i consumi economici relativi, `r` il rapporto di prezzo effettivo e `q` il costo della parte forte rispetto a B. Quando si aggiungono giudici, router o servizi, tutte le nuove voci devono essere assegnate coerentemente ai termini oppure mostrate separatamente.

**Notazione:** nelle formulazioni astratte del routing, τ può indicare una soglia minima di qualità assoluta. Nel protocollo OrcV2, `τ_funziona` e `τ_piace` sono margini ammessi nella differenza rispetto alla baseline. Sono quantità differenti: una soglia di probabilità del router non è automaticamente né una soglia di qualità del sito né il margine di non inferiorità.

Un unico `r` ha senso solo se è ricavato dalla miscela effettiva di input, output e cache. Un rapporto fra soli prezzi di listino non rappresenta necessariamente la miscela di due sistemi con storie diverse. Se lo scopo è isolare il prezzo dai consumi, conviene conservare le quantità e fare un ricalcolo comune esplicito.

### 10.3 Pareggio di un selettore prima della risposta

In un esempio semplificato con stesso numero e struttura delle richieste, costo forte `C_f`, economico `C_e`, quota economica `u` e costo del selettore `C_r`:

```text
C_r + (1-u) C_f + u C_e < C_f
quindi u (C_f - C_e) > C_r
```

È una condizione economica sotto quelle ipotesi. Non garantisce che il router scelga bene e non include automaticamente il cambiamento del numero di turni, la cache persa o il lavoro di correzione. Per un agente completo sono proprio quelle differenze a richiedere una prova reale.

### 10.4 Pareggio di una cascata

Se prima si genera con l'economico, si paga un controllo e si accetta la sua risposta con frequenza `a`, sotto costi medi costanti:

```text
C_e + C_v + (1-a) C_f + C_extra < C_f
quindi a > (C_e + C_v + C_extra) / C_f
```

`C_v` è il costo della verifica, `C_extra` la spesa ulteriore media imputata al percorso, come ripristini o passaggi di contesto. La formula è illustrativa: costo e probabilità di escalation spesso dipendono dalla difficoltà del caso, e il forte può ricevere più storia rispetto alla baseline. Va usata per leggere la misura, non per sostituirla.

### 10.5 Addestramento e ammortamento

Un router preaddestrato evita il costo di addestramento da zero, ma può richiedere valutazione, taratura, esecuzione locale o abbonamento. Un router personalizzato richiede esempi per i candidati, giudizi, eventuali risposte multiple e tempo di preparazione.

Se un adattamento costa `F` dollari una tantum e fa risparmiare `s` dollari medi per compito, un pareggio puramente monetario richiede circa `F/s` compiti, purché `s` sia positivo e stabile. Non è una stima del progetto: evidenzia perché una riduzione marginale su una campagna piccola può non ammortizzare la preparazione.

Per l'esperimento vanno mostrati sia i costi di ricerca e taratura sia quelli dell'uso finale. Un confronto può risultare conveniente in produzione e poco conveniente per una tesi con poche decine di siti, senza contraddizione.

### 10.6 Cache: tre fenomeni diversi

| Fenomeno | Cosa viene riusato | Implicazione |
|---|---|---|
| Cache del prompt del fornitore | Parte dell'input già elaborato | Si applica una tariffa specifica e talvolta una durata |
| Cache della risposta nel proxy | Risposta completa a una richiesta precedente | Può evitare una generazione e rendere non indipendenti le repliche |
| Memoria della scelta di routing | Modello o livello scelto per una conversazione | Può stabilizzare il lavoro o contaminare un compito diverso se l'identità è sbagliata |

Cambiare modello può richiedere ripagare l'input che prima era in cache. Comprimere il contesto può ridurre token ma perdere il prefisso stabile. Il criterio è il costo end-to-end, cioè di tutto il processo fino alla pagina finale, non il solo numero di caratteri eliminati.

<a id="sezione-11"></a>
## 11. Esperimenti che distinguono le spiegazioni del risparmio

### 11.1 Il singolo agente ibrido come proposta secondaria

La prova principale resta C contro B. Come proposta, si può aggiungere **H**, etichetta provvisoria per un singolo agente con gli stessi modelli disponibili a C e una politica di alternanza fissata.

| Confronto | Cosa permette di discutere | Cosa non isola da solo |
|---|---|---|
| C contro B | Costo e qualità della configurazione OrcV2 contro il forte singolo | La causa unica di un eventuale vantaggio |
| D contro B | Quanto basta già l'economico singolo | Se un router lo selezionerebbe correttamente in anticipo |
| H contro B | Effetto di quella politica ibrida nel singolo agente | Tutte le possibili politiche di routing |
| C contro H | Vantaggio aggiuntivo della configurazione dello sciame rispetto a quell'alternativa | La sola scomposizione, separata da contesti, prompt, critico e integrazione |

Non sarebbe corretto rinominare H come B mantenendo invariata la descrizione della baseline: B è definito come mono-modello nel protocollo. Il nuovo confronto va nominato e motivato apertamente.

### 11.2 Scelta della politica e rischio di confronto debole

Plan/Execute è semplice da interpretare e non richiede un classificatore aggiuntivo, ma può trasferire troppo presto il lavoro all'economico. Stage osserva più informazioni sullo svolgimento, ma richiede una buona corrispondenza fra strumenti, risultati e segnali riconosciuti. Un selettore appreso porta dati e ipotesi diverse.

La scelta va motivata sui compiti di sviluppo. Non basta scegliere una politica fragile che lo sciame supera facilmente; H deve ricevere un prompt adeguato, strumenti reali e opportunità comparabili di vedere e correggere il sito. Neppure la politica più favorevole scelta dopo numerosi tentativi sul test sarebbe un confronto valido.

### 11.3 Pilota progressivo

1. **Compatibilità senza nuova generazione:** leggere formati, catalogo dei modelli, licenze, dati disponibili e limiti del percorso preciso.
2. **Verifica del contratto con risposte simulate:** scelta, sessioni, tool calling, modelli serviti e registrazione di tutte le chiamate.
3. **Pilota reale sui compiti di sviluppo:** con preventivo e tetti approvati, misurare costo, qualità, errori e motivo degli arresti.
4. **Scelta motivata di una configurazione:** annotare quante varianti sono state provate e perché una viene mantenuta.
5. **Congelamento:** fissare versione, prompt, modelli, fornitori, soglie, modalità di verifica e gestione dei guasti prima del test.
6. **Eventuale campagna secondaria:** se il budget la sostiene, confrontare H con i bracci previsti senza spostare silenziosamente la prova principale.

Questo non è un nuovo piano di spesa. La generazione e il giudizio dei siti aggiuntivi richiedono un preventivo misurato; il prezzo del solo router non basta a stimarlo.

### 11.4 Unità indipendente e suddivisione dei dati

I turni dello stesso sito condividono specifica, storia e artefatti. Se si mettono turni dello stesso sito in addestramento e test, il secondo può risultare artificialmente facile. La divisione deve essere almeno per compito; se i compiti sono varianti strette, va considerata anche la famiglia.

Il principio è già presente nella cascata di giudizio in [quality/cascade.py:183](/Users/vincenzomattioli/Documents/OrcV2/quality/cascade.py:183):

```python
train = [c for c in cases if blocco[c.task_id] != k]
test = [c for c in cases if blocco[c.task_id] == k]
```

Questa suddivisione riguarda il modulo già esistente. Non prova che un nuovo router agentico sia stato valutato così; è un criterio da mantenere nella sua prova.

### 11.5 Apprendimento continuo e feedback del test

Se il servizio modifica il router durante la campagna usando gli esiti dei compiti, il sistema non resta congelato. Per un confronto statico bisogna sapere se si può bloccare l'apprendimento o quale versione viene usata. Se non è possibile, va dichiarato come limite del servizio oppure progettato un esperimento specifico online con ordine temporale e costo di esplorazione.

Usare i risultati finali R6 per progettare il router R7 è legittimo come esplorazione, ma quei medesimi risultati non diventano poi una verifica indipendente di R7. Serve un insieme nuovo o una separazione definita prima dell'adattamento.

### 11.6 Perché il replay non basta

Il replay rigioca decisioni o costi su tracce già esistenti. Può essere utile per confrontare ipotesi e scartare una politica palesemente cara. Ma un modello diverso avrebbe potuto chiamare strumenti diversi, produrre file diversi e cambiare ogni richiesta successiva.

Il controfattuale è ciò che sarebbe accaduto con una scelta non eseguita. I log del modello scelto di solito non contengono quel risultato. Una diminuzione del costo ricalcolato sulla traccia del forte non dimostra che l'economico avrebbe completato il sito. La prova finale deve eseguire il sistema dichiarato oppure riportare esplicitamente che si tratta di una simulazione parziale.

### 11.7 Separazione dei giudici

| Controllore | Vede cosa | Influenza il lavoro | Costo attribuito |
|---|---|---|---|
| Classificatore di routing | Richiesta e segnali disponibili | Sceglie il modello | Generazione del sito |
| Critico o consigliere | Lavoro intermedio e controlli consentiti | Può richiedere correzioni | Generazione del sito |
| Giudice scientifico | Artefatti finali e criteri congelati | Non modifica la soluzione | Valutazione della ricerca |
| Votante umano | Coppie in condizioni dichiarate | Verifica il metro di giudizio | Validazione della ricerca |

Un riscontro positivo del critico interno non è già un risultato indipendente sul quale dimostrare la tesi. Le domande riservate del giudice e gli script di valutazione non devono diventare informazioni operative del router o degli agenti.

### 11.8 Ablazioni e scenari di esito

Un'ablazione modifica o rimuove una leva per misurarne l'effetto. Esempi: modello fisso con compressione accesa/spenta; sciame con consigliere limitato/senza consigliere; stessa politica con segnale di stallo rimosso; diverso numero di pezzi con le altre regole fissate.

- **D basta:** il contributo mostra i casi in cui l'economico singolo raggiunge il risultato; lo sciame potrebbe essere superfluo su quel campione.
- **H basta:** l'alternanza nel singolo agente spiega buona parte del risparmio; il vantaggio della scomposizione resta da dimostrare.
- **C migliora il compromesso:** la configurazione dello sciame permette risparmio o qualità che l'alternativa non raggiunge nelle condizioni osservate.
- **Dipende dal tipo di sito:** la domanda si sposta verso una scelta tra strategie, con sviluppo e verifica separati.
- **Nessuno dimostra non inferiorità:** si riportano stime e intervalli e si discute se il limite è qualità, numerosità o variabilità. Non si conclude uguaglianza dall'assenza di significatività.

Tutti questi esiti possono informare la tesi. La formulazione scientifica deve permettere anche che il sistema proposto non vinca.

<a id="sezione-12"></a>
## 12. Conseguenze per la revisione della tesi

### 12.1 Cosa rafforzare nel posizionamento

Una formulazione prudente e informativa della domanda di ricerca è:

> In quali condizioni la scomposizione e il coordinamento di agenti con modelli eterogenei riducono il costo della generazione di siti web entro margini di qualità dichiarati, e quanto del risultato è spiegato da alternanza dei modelli, verifica e gestione del contesto?

È una formulazione candidata, non testo approvato. Distingue il sistema dalla sola disponibilità di un router e rende esplicite le spiegazioni alternative del risparmio.

Non va affermato come nuovo ciò che i lavori esistenti già implementano: assegnazione forte/economico, escalation, revisore, selezione per compito e compressione sono meccanismi noti. Un contributo empirico sul dominio web può consistere nel confronto equo, nella misura con qualità validata e nella disaggregazione delle leve, se effettivamente eseguiti.

### 12.2 Dove potrebbero cambiare i documenti

| Documento o capitolo | Materiale che questo dossier fornisce | Decisione ancora necessaria |
|---|---|---|
| Stato dell'arte | Tassonomia, Switchyard, router pronti e limiti delle evidenze | Quali riferimenti entrano nel perimetro finale |
| Architettura | Selettore, runtime, gateway, controllo e giudizio separati | Dove effettuare la scelta e con quale granularità |
| Metodologia | Possibile confronto H e criteri di parità | Se aggiungerlo, quale politica e con quale budget |
| Misura del costo | Giudici operativi, cache, modelli effettivi e tentativi | Schema minimo dei metadati e riconciliazione |
| Qualità | Classificazione non equivalente a verifica del prodotto | Validazione del giudice e margini del protocollo |
| Risultati | Costo e qualità per compito, distribuzioni e casi di guasto | Nessun risultato nuovo è disponibile da questo dossier |
| Limiti | Dati piccoli, servizi mobili, pool non identico, feedback non indipendente | Quali limiti sono evitati e quali dichiarati |
| Lavori futuri | Personalizzazione o scelta tra strategie con dati sufficienti | Se R7 resta futura o diventa esperimento separato |

Il dossier non autorizza a modificare le decisioni D35–D47 o a rimuovere un braccio. Le alternative vanno prima comprese e scelte, poi tradotte nel protocollo e nell'implementazione.

### 12.3 Affermazioni sostenibili e non sostenibili

| Sostenibile ora | Da non affermare senza nuova prova |
|---|---|
| Esistono router preaddestrati e servizi di routing pronti | Nessun router può essere integrato senza addestramento nostro |
| Switchyard ha politiche di routing agentico già implementate | Forte pianifica/economico esegue è di per sé un meccanismo originale OrcV2 |
| Certi profili pubblicati riducono costo in specifici benchmark | Stessa percentuale di risparmio su siti OrcV2 |
| Alcune prestazioni medie sono vicine | Non inferiorità dimostrata senza margine e intervallo pertinente |
| Un router riconosce o classifica un tipo di richiesta | Sa quale modello costruirà un sito accettabile con probabilità calibrata |
| Un servizio espone un'API documentata | Il nostro account ha già accesso a tutti i modelli e alle stesse versioni |
| La CI pubblica passa test di contratto e unitari | Tutti i flussi con fornitori reali sono stati verificati |
| Un compressore riduce token su certi payload | Conserva significato, qualità e costo finale nel nostro agente |
| Il confronto C–H misura due configurazioni definite | Isola automaticamente la sola scomposizione o tutti gli sciami contro tutti i router |

### 12.4 Riuso, citazione e originalità

Riutilizzare una libreria non impedisce una tesi sperimentale. Occorre dichiarare quale componente è esterno, quale è adattato e quale è originale. I risultati della libreria originale non devono essere attribuiti all'adattamento senza riprodurli.

La citazione scientifica e gli obblighi di licenza sono due cose diverse: citare un paper non sostituisce l'inclusione delle condizioni necessarie quando si distribuisce codice o pesi. Anche un frammento sostanziale può avere obblighi. Per gli artefatti con termini discordanti fra scheda e file LICENSE, bisogna risolvere quale testo si applica alla versione concreta prima di distribuirli.

<a id="sezione-13"></a>
## 13. Priorità proposte, dipendenze e questioni aperte

Le priorità indicano una valutazione di utilità per il progetto attuale, non risultati già acquisiti.

| Priorità | Azione candidata | Perché | Prerequisito | Criterio per continuare |
|---|---|---|---|---|
| Alta | Completare R1 e misurare B/D | Serve un metro comune prima di confrontare i router | Giudizio e controlli coerenti col protocollo | Costo e qualità interpretabili |
| Alta | Specificare tracciamento del modello effettivo e delle chiamate intermedie | Il costo è una variabile centrale | Capacità del candidato di esporre dati | Totale riconciliabile e anomalie visibili |
| Alta | Valutare Switchyard ospitato o incorporato, scegliendo quale | È una base già operativa e un confronto pertinente | Coppia effettiva e politica accessibile | Scelta osservabile e flusso degli strumenti preservato |
| Alta | Valutare H sullo sviluppo | Chiarisce una spiegazione alternativa al vantaggio dello sciame | Specifica equa e tetto del pilota | Informazione aggiuntiva proporzionata al costo |
| Media | Valutare consigliere e stallo | Può ridurre uso continuo del forte | Critico operativo distinto dal valutatore | Migliora il risultato completo o riduce costo a qualità comparabile |
| Media | Misurare compressione o contesto selettivo | Può diminuire il costo di input | Profilazione delle quantità e della cache | Nessun danno nascosto al sito finale |
| Successiva | Integrare un router con pesi controllabili | Offre un confronto più riproducibile | Dati e formati adatti, condizioni dei pesi | Evidenza sufficiente fuori dallo sviluppo |
| Successiva | Personalizzare un router con feedback OrcV2 | Può sfruttare differenze fra compiti | Etichette affidabili e numero adeguato di compiti | Vantaggio che copra costo e complessità della preparazione |

### 13.1 Decisioni da discutere prima di cambiare il progetto

1. **Granularità:** scegliere fra modelli per sito, per worker, per turno oppure fra strategie complete.
2. **Modalità d'uso:** selettore separato, libreria incorporata o servizio ospitato.
3. **Rosa:** modelli e versioni realmente usati da C e condivisi con i confronti pertinenti.
4. **Confronto aggiuntivo:** mantenere H solo esplorativo o inserirlo come secondario prima del congelamento.
5. **Politica:** quale algoritmo, quale stato e quali segnali, con parametri scelti sullo sviluppo.
6. **Budget:** preventivo che comprenda generazione, controlli operativi, decisioni e giudizio finale.
7. **Riproducibilità:** come bloccare o descrivere cambiamenti dei servizi e dell'apprendimento.
8. **Riuso:** codice originale del prodotto, adattamento dichiarato o sola ispirazione del meccanismo.

Non serve risolvere tutto insieme. La prima scelta dipendente è cosa si vuole misurare: sostituire una parte tecnica dello sciame oppure confrontarlo con una strategia già pronta. Le due attività possono richiedere integrazioni diverse.

### 13.2 Questioni non chiuse dalle fonti

- Accesso effettivo alle API commerciali e prezzi applicabili al percorso specifico.
- Presenza della rosa OrcV2 nel catalogo aggiornato del selettore e supporto dei parametri necessari.
- Generalizzazione dei router appresi alle versioni attuali e al dominio web.
- Mappatura reale dei segnali degli strumenti e delle uscite di shell.
- Completezza dei costi intermedi e possibilità di correlare generazioni al compito.
- Effetto del cambio di modello su cache, ragionamento e numero di turni.
- Capacità del servizio di restare congelato durante la prova finale.
- Qualità dei verificatori senza risposta di riferimento del modello forte.
- Condizioni applicabili ai singoli pesi, agli estratti copiati e alla redistribuzione del progetto.

Queste incognite richiedono verifica mirata; non giustificano una conclusione preventiva che i router esistenti siano inutilizzabili. Allo stesso modo, non autorizzano a promettere un risparmio.

<a id="sezione-14"></a>
## 14. Glossario essenziale per la rilettura

| Termine | Significato nel dossier |
|---|---|
| API | Interfaccia con cui un programma richiede un servizio remoto |
| Artefatto | Il risultato prodotto, qui sito, file o risorsa generata |
| Baseline | Configurazione di riferimento contro cui si confronta il sistema |
| Bandit | Selettore che impara dai risultati delle alternative scelte |
| Calibrazione | Verifica della corrispondenza fra punteggio/probabilità dichiarata ed esiti reali |
| Cascata | Tentativo economico, controllo, eventuale tentativo più forte |
| Checkpoint | Secondo il contesto: file dei parametri appresi di un modello, oppure momento operativo in cui si controlla l'avanzamento dell'agente |
| CI | Test e controlli automatici eseguiti nel progetto esterno |
| Cold start | Fase iniziale con poche osservazioni specifiche del carico di lavoro |
| Confidence | Punteggio di fiducia del sistema, la cui interpretazione dipende dalla formula |
| Contestuale | Usa informazioni della richiesta per scegliere l'alternativa |
| Controfattuale | Risultato che si sarebbe ottenuto eseguendo una scelta differente |
| Embedding | Rappresentazione numerica del testo usata come caratteristica o per similarità |
| Endpoint | Indirizzo concreto del servizio che elabora la richiesta |
| Escalation | Passaggio a un modello o controllo più forte dopo un segnale |
| Fallback | Ripiego su un'alternativa; spesso riguarda errori di disponibilità, non qualità |
| Fine-tuning | Ulteriore addestramento su dati selezionati |
| Gateway | Componente che esegue il dialogo con il servizio e ne adatta il formato |
| Harness | Ambiente completo in cui l'agente opera: istruzioni, strumenti, ciclo e limiti |
| Held-out | Dati esclusi dall'addestramento o dalla messa a punto pertinente |
| Ledger | Registro strutturato delle chiamate, dei consumi e degli eventi di una run |
| LLM judge | Modello usato per assegnare un giudizio o guidare una decisione |
| Non inferiorità | Dimostrazione che la perdita rispetto alla baseline resta entro un margine dichiarato |
| Oracle | Selettore teorico che dispone di esiti non normalmente noti prima della scelta |
| Pool o rosa | Insieme di candidati fra cui il router può scegliere |
| Prefill | Elaborazione dell'input prima della produzione dei token di risposta |
| Proxy | Servizio intermedio che riceve una richiesta e la inoltra o la trasforma |
| Replay | Analisi o riproduzione parziale su tracce già registrate |
| Reward | Premio numerico che un algoritmo cerca di aumentare |
| Run | Una singola esecuzione identificabile e separata dalle altre |
| Runtime | Componente che esegue concretamente le richieste e lo stato operativo |
| Shadow | Modalità che calcola una scelta alternativa senza usarla per servire il risultato |
| Streaming | Arrivo progressivo della risposta in frammenti |
| Tool calling | Richiesta del modello di eseguire uno strumento con argomenti strutturati |
| Trace | Traccia ordinata delle decisioni, richieste ed eventi |
| Transfer | Uso di un modello addestrato in condizioni diverse da quelle nuove |
| AUROC | Misura di quanto un punteggio ordina bene positivi e negativi; non è percentuale di siti corretti |
| Brier score | Errore quadratico delle probabilità rispetto agli esiti osservati |
| ECE | Riassunto della differenza fra probabilità dichiarate e frequenze osservate, dipendente dai raggruppamenti |
| BYOK | Uso delle proprie chiavi del fornitore dentro un servizio intermedio |

<a id="sezione-15"></a>
## 15. Indicazioni per una successiva revisione del progetto

Prima di trasformare il dossier in modifiche alla tesi o alla roadmap:

1. Rileggere il protocollo vigente e distinguere decisioni già prese da proposte in questo documento.
2. Scegliere la domanda sperimentale prioritaria e il ruolo del router nel sistema.
3. Verificare nuovamente disponibilità, cataloghi e condizioni delle API al momento della prova.
4. Citare una versione concreta del codice e delle impostazioni, mantenendo separate le configurazioni dei benchmark pubblicati.
5. Trasformare soltanto le alternative scelte in specifiche, criteri di accettazione e preventivi.
6. Riferire eventuali risultati negativi e incongruenze senza attribuire intenzioni agli autori.
7. Non trasformare i numeri esterni in risultati di OrcV2 e non dichiarare un'integrazione completata prima delle verifiche.

Le fonti sono collegate vicino alle affermazioni. Non servono gli altri documenti di questa analisi per interpretare le conclusioni: descrizioni, evidenze, limiti e implicazioni principali sono raccolti qui. I documenti interni di progetto e le fonti esterne rimangono necessari per controllare o aggiornare le singole affermazioni.

<a id="sezione-16"></a>
## 16. Fonti principali e verifica del documento

### 16.1 Gruppi di fonti per aggiornare l'analisi

| Area | Fonti di partenza | Cosa controllare quando cambiano |
|---|---|---|
| Switchyard | [Sorgente fissato](https://github.com/NVIDIA-NeMo/Switchyard/tree/7558a1d8a5f21824c6fd81ddbf73a041e1a317c9), [release](https://github.com/NVIDIA-NeMo/Switchyard/releases), [API ospitata](https://openrouter.ai/docs/guides/routing/routers/switchyard-router) | Algoritmi, percorsi, supporto delle integrazioni, gestione errori e costi interni |
| Conduit | [Archivio fissato](https://github.com/ashita-ai/conduit/tree/e93981c0d9304fc7fbff21b3771a77d81429ec2b), [pagina degli autori](https://ashita.ai/projects/conduit/) | Distinzione fra codice disponibile, risultati preliminari e materiale di pianificazione |
| NadirClaw e Pro | [Codice verificato](https://github.com/NadirRouter/NadirClaw/tree/8a75cdb647dc392de4498c02e86ed90962c08214), [README aggiornato](https://github.com/NadirRouter/NadirClaw/blob/5f60ffe753e30499daa3738bf89f21e884bc9df9/README.md), [prezzi](https://getnadir.com/pricing/) | Classificatore realmente attivo, servizio commerciale e allineamento delle condizioni |
| Not Diamond | [Chat](https://docs.notdiamond.ai/docs/quickstart-routing), [Code](https://docs.notdiamond.ai/docs/pre-trained-router-code), [catalogo](https://docs.notdiamond.ai/docs/llm-models), [listino](https://www.notdiamond.ai/pricing) | Accesso, rosa, versione del prodotto e tariffa dell'endpoint concreto |
| RouteLLM | [Sorgente fissato](https://github.com/lm-sys/RouteLLM/tree/0b64fdafe049e596a3f5657c219329f24af24198), [paper](https://arxiv.org/abs/2406.18665v4) | Trasferimento, ingresso del controller, dipendenze, pesi e soglie |
| Arch-Router | [Scheda](https://huggingface.co/katanemo/Arch-Router-1.5B), [licenza fissata](https://huggingface.co/katanemo/Arch-Router-1.5B/blob/5b156890a91b1035a86f82faf1a651debf309009/LICENSE), [paper](https://arxiv.org/abs/2506.16655) | Mappa delle preferenze, revisione dei pesi e condizioni di redistribuzione |
| RouteFM | [Rilascio fissato](https://github.com/LAMDA-Model-Reuse/RouteFM/tree/e7e650610850eee055016ed1dab06f08e833663b), [pesi](https://huggingface.co/AIGNLAI/RouteFM), [paper](https://arxiv.org/abs/2609.37362) | Osservazioni minime, encoder, scala degli esiti, selezione costo/qualità e partizioni del benchmark |
| OpenRouter Auto e Pareto | [Auto](https://openrouter.ai/docs/guides/routing/routers/auto-router), [Pareto](https://openrouter.ai/docs/guides/routing/routers/pareto-router) | Selezione, cataloghi mobili, impostazioni, identità e prezzi dei modelli serviti |
| Verifica delle citazioni | [Reward Model Routing in Alignment](https://arxiv.org/abs/2510.02850), [esperimento LangChain](https://www.langchain.com/blog/switchyard-agent-routing-benchmark) | Oggetto scientifico realmente studiato e limiti dichiarati dell'esperimento |

Questa tabella è un indice delle fonti, non sostituisce i riferimenti puntuali nelle sezioni tecniche. Le eventuali revisioni successive vanno trattate come nuovi oggetti: la stabilità di un collegamento a main non congela il contenuto.

### 16.2 Controlli completati e limiti residui

- Verificata l'esistenza dei file locali collegati al documento.
- Verificati gli alberi Git completi di sei combinazioni repository/versione: tutti i 94 percorsi esterni di file/versione citati risultano presenti nelle revisioni indicate. Questa verifica riguarda l'esistenza del file, non certifica da sola ogni frase o ancora di riga.
- Controllati indice, ancore interne, gerarchia principale, chiusura dei blocchi di codice, assenza di segnaposto e autonomia rispetto alle note preparatorie.
- Ricontrollati i calcoli economici esposti e la distinzione fra medie, variabilità, non inferiorità e semplice mancata significatività.
- Sottoposte a rilettura critica le conclusioni di integrazione, il perimetro del confronto C–H e la distinzione fra libreria, servizio e pesi.

**Limiti della verifica:** non sono stati eseguiti i router, la suite di OrcV2 o nuove chiamate ai fornitori. Il documento non aggiunge codice di integrazione. Non certifica accesso alle offerte commerciali, addebiti effettivi, prestazioni sui siti o comportamento dei percorsi soltanto documentati. Nessuno di quei risultati è richiesto per qualificare il dossier come analisi; tutti diventano necessari se si decide di realizzare e misurare un'integrazione.
