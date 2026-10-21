# Protocollo sperimentale (R0)

> **Cos'e'.** Le regole dell'esperimento, scritte prima delle misure. Si completano una voce alla
> volta durante R0-R1; prima della campagna finale (R6) il file si fissa con un commit pubblicato e
> da quel momento non cambia. Una modifica dopo quel commit va dichiarata e la campagna rifatta.
>
> Legenda: ✅ deciso · 🔲 da decidere. Le sigle D35-D44 rimandano al registro in `PIANO_completo.md`.

## 1. Ipotesi ✅

OrcV2 (braccio C) costa significativamente meno di Opus 5.5 con gli stessi strumenti (braccio B), con una
qualita' non inferiore di piu' di τ, nella generazione di siti web (D36). Condizione di convenienza dichiarata
prima delle misure: `m / r + q < 1` (D37).

## 2. Compiti

- ✅ **Tipo (21 ott 2026):** meta' **siti di contenuto** con interattivita' leggera (landing, portfolio, evento;
  menu, galleria, form senza server) e meta' **applicazioni che girano solo nel browser** (dati nel browser,
  per esempio `localStorage`). Esclusi i compiti che richiedono un server, un'API a pagamento o un servizio di AI.
- ✅ **Fonti (D40):** WebGen-Bench (arXiv 2505.03733, dati con licenza MIT) e ArtifactsBench (arXiv 2507.04952,
  licenza CC BY 4.0, va citato), piu' alcuni compiti scritti per questa tesi.
- ✅ **Numero e divisione (D45, 21 ott 2026):** 8 compiti di **sviluppo** (si usano per ottimizzare, R4) e 20 di
  **test** (non si guardano fino a R6). In ciascuna divisione meta' siti e meta' applicazioni.
- ✅ **Scelta:** prima si filtrano i compiti che rispettano le regole qui sopra, poi si estraggono a sorte con un
  seme scritto in questo file, separatamente per siti e applicazioni.
- ✅ **Seme del sorteggio:** 20261021.
- 🔲 L'elenco dei compiti filtrati e il numero di compiti scritti per la tesi (R1).

## 3. Bracci ✅ (D39, modificata da D45)

| Braccio | Cosa |
|---|---|
| B | Opus 5.5 da solo con gli stessi strumenti e lo stesso ciclo di verifica di OrcV2 |
| C | OrcV2 |
| D | Il modello economico dei worker di OrcV2, da solo, con gli stessi strumenti |

Il braccio A (Opus senza strumenti) e' stato tolto per costo (D45). Ogni strumento dato a C si da' anche a B e D
(D42).

## 4. Modelli ✅ (D38)

Versioni, fornitori e listini in `models.toml` (letti il 19-21 ott 2026). Modello economico: DeepSeek V4.1 Flash
`-1017` sull'endpoint DeepSeek (D47), usato dai worker di C e dal braccio D. Le run a pagamento si lanciano fuori
dalla fascia oraria in cui DeepSeek raddoppia il prezzo (giorni feriali, 01-04 e 06-10 UTC).

## 5. Ambiente ✅ (21 ott 2026)

Sandbox Docker con rete `bridge` e il firewall del progetto (blocca la macchina e la rete locale), uguale per
tutti i bracci.

## 6. Qualita' (D41)

- ✅ Tre livelli: controlli automatici, giudice a coppie in entrambi gli ordini con famiglie non in gara, voti
  umani alla cieca (4-6 persone) per verificare il giudice. Giudice scelto in R1 fra Gemini 4 Argon e Gemini 3.8
  Flash per accordo con i voti umani.
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
- ✅ **Punteggio «funziona» (21 ott 2026):** quota di passi dello script di interazione superati, da 0 a 100; 0 se
  la pagina non si apre. Sbordo alle tre larghezze e problemi di accessibilita' si riportano a parte, per braccio,
  e non entrano nel punteggio.
- Revisione: le domande si possono rivedere sui compiti di sviluppo (R1, R4); si congelano prima di R6.

## 7. Metrica principale e margine τ

- ✅ **Due metriche affiancate, nessun voto unico (21 ott 2026):** (1) **funziona**: differenza media fra C e B nel
  punteggio del livello 1 (0-100), sugli stessi compiti; (2) **piace**: voto medio del giudice nel confronto a
  coppie C contro B, su una scala graduata da −2 (B molto meglio) a +2 (C molto meglio), 0 = pari. Ogni coppia si
  giudica in entrambi gli ordini e si fa la media dei due voti, col segno riportato dalla parte di C. C e' «non
  inferiore» solo se lo e' su entrambe.
- ✅ **τ_funziona = 10 punti** (21 ott 2026): in media i siti di C possono superare fino a un passo su dieci in meno.
- ✅ **τ_piace: regola (21 ott 2026).** Il valore, sulla scala −2..+2, si fissa dopo il pilota di R2 (quando si
  conosce la variabilita' dei voti) e prima di qualunque confronto fra C e B; si scrive qui con la motivazione e si
  committa prima della campagna.

## 8. Costo ✅

Dollari per pagina, misurati dal ledger; i token solo come dato ausiliario.

## 9. Ripetizioni ✅ (D45)

Una esecuzione per compito e per braccio.

## 10. Analisi ✅ (21 ott 2026)

- Per ogni metrica di §7: differenza C − B per compito, media sui 20 compiti di test, intervallo con **bootstrap**
  sui compiti (10.000 ricampionamenti). **C e' non inferiore** se il limite basso al 2,5% e' sopra −τ, su entrambe
  le metriche.
- Controllo: si riporta anche il test t appaiato. Se i due metodi danno conclusioni diverse, il risultato e' «non
  dimostrato».
- Costo: rapporto C/B con il suo intervallo bootstrap; «costa meno» e' dimostrato se tutto l'intervallo sta sotto 1.
- Il braccio D e le ablazioni si riportano e si commentano, senza dichiarazioni di significativita': la prova
  principale e' una sola, C contro B.

## 11. Spesa ✅ (D44)

Preventivo prima di ogni fase (misurato per le campagne), tetto deciso fase per fase, `--budget-usd` su ogni
esecuzione.
