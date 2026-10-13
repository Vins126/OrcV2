# Infrastrutture scollegate (12 ottobre 2026)

Dal 12 ottobre 2026 ORC raggiunge **tutti** i modelli attraverso **una sola infrastruttura: OpenRouter**,
con una sola chiave (`ORC2_OPENROUTER_KEY`). Questo file elenca ogni infrastruttura che e' stata
scollegata, **dove stava**, **perche'** e **come si ricollega**.

**Perche' in generale.** Gestire piu' fornitori significa piu' chiavi, piu' crediti da caricare, piu' gateway da
provare e piu' strade da tenere coerenti nel registro dei prezzi. Per la fase di misura serve un percorso solo e
riproducibile; in piu', al momento della decisione non c'era credito presso Anthropic.

**Cosa si perde in generale.** La «tassa dell'aggregatore» (stesso modello chiamato diretto e via OpenRouter)
non e' piu' misurabile, perche' non c'e' piu una strada diretta di confronto. Restano il confronto fra costo
**riportato** da OpenRouter (`usage.cost`, campo `reported_cost` del record) e costo **calcolato** sul listino, e la
commissione sull'acquisto dei crediti (5,5%, minimo 0,80 dollari, secondo le FAQ di OpenRouter).

Convenzione: «scollegato» = tolto dal percorso attivo (configurazione, mappa dei fornitori, chiavi). Dove il
codice e' rimasto nel repository lo si dice; dove e' stato rimosso si dice anche da dove recuperarlo.

---

## 1. Anthropic (diretto)

- **Che cos'era.** Il fornitore del pianificatore `opus-5-5`, raggiunto con la chiave `ORC2_ANTHROPIC_KEY` e il
  gateway nativo dell'API Messages.
- **Scollegato da:**
  - `models.toml`: la sezione `[providers.anthropic]`; il modello `opus-5-5` ora ha `provider = "openrouter"`.
  - `agent_factory.py`: `import anthropic`, la funzione `_client_anthropic`, l'import di `AnthropicChatGateway`,
    la voce `"anthropic"` di `BACKEND_PER_PROVIDER`.
  - `.env` e `.env.example`: la variabile `ORC2_ANTHROPIC_KEY`.
- **Resta nel repository, non collegato:** `AnthropicChatGateway` in `llm_gateway.py` (con `import anthropic`),
  `accounting/mappers/anthropic.py`, `tests/test_anthropic.py`, e `anthropic==1.2.0` in `requirements.txt`.
  I loro test continuano a girare.
- **Perche'.** Nessun credito presso Anthropic, e una chiave in meno da gestire.
- **Cosa si perde.** Il gateway di Opus passa al formato OpenAI di OpenRouter, che **non invia `cache_control` ne'
  `effort`**: la cache esplicita di Anthropic non e' usata, e il costo di Opus nelle conversazioni lunghe sara'
  piu' alto di quello con la cache. **Misurato il 12 ottobre 2026:** una run con Opus via OpenRouter ha letto 0 token dalla
  cache (contro 512-640 di Kimi e M3 nello stesso compito), con costo riportato = calcolato ($0,014064). Quanto pesi
  sul costo di conversazioni lunghe non e' ancora misurato.
- **Come ricollegare.**
  1. In `models.toml` rimettere la sezione e puntare il modello al fornitore diretto:
     ```toml
     [providers.anthropic]
     monthly_fee = 0.0
     base_url    = "https://api.anthropic.com"
     api_key_env = "ORC2_ANTHROPIC_KEY"
     ```
     poi in `[models.opus-5-5]`: `provider = "anthropic"`, `api_model = "claude-opus-5-5"`, e togliere `provider_order`.
  2. In `agent_factory.py`: `import anthropic`; importare `AnthropicChatGateway` da `llm_gateway`; riaggiungere
     ```python
     def _client_anthropic(credenziali: config.ProviderCredentials) -> Any:
         return anthropic.Anthropic(
             api_key=credenziali.api_key, base_url=credenziali.base_url)
     ```
     e in `BACKEND_PER_PROVIDER` la voce `"anthropic": Backend(AnthropicChatGateway, _client_anthropic)`.
  3. Mettere `ORC2_ANTHROPIC_KEY` nel `.env`. Per la cache di Opus: il listino diretto di Opus 5.5 e' 4 / 20 dollari
     per milione, scrittura cache (5 minuti) 5, lettura 0,20 (platform.claude.com, 10 ottobre 2026).

## 2. Moonshot (diretto)

- **Che cos'era.** Il fornitore di `kimi-k3`, con la chiave `ORC2_MOONSHOT_KEY` e indirizzo
  `https://api.moonshot.ai/v1` (formato OpenAI).
- **Scollegato da:** `models.toml` (`[providers.moonshot]`), `BACKEND_PER_PROVIDER["moonshot"]`, `.env.example`.
  `kimi-k3` ora ha `provider = "openrouter"`, `api_model = "moonshotai/kimi-k3"` e il fornitore fissato
  `provider_order = ["moonshotai/mxfp4"]`.
- **Perche'.** Una chiave e un credito in meno.
- **Cosa si perde.** Il listino ufficiale Moonshot e' 3,00 / 15,00 dollari, lettura cache 0,30, **scrittura cache 3,00**
  (platform.kimi.ai, 10 ottobre 2026). Sull'endpoint `moonshotai/mxfp4` di OpenRouter il prezzo di scrittura in cache
  **non e' elencato** e quindi non e' nel registro: un consumo di quel tipo risultera' non prezzato. Quell'endpoint
  serve i pesi **MXFP4**, che sono la precisione nativa di Kimi K3 (scheda ufficiale): non e' una versione peggiorata.
- **Come ricollegare.**
  ```toml
  [providers.moonshot]
  monthly_fee = 0.0
  base_url    = "https://api.moonshot.ai/v1"
  api_key_env = "ORC2_MOONSHOT_KEY"
  ```
  In `[models.kimi-k3]`: `provider = "moonshot"`, togliere `api_model` e `provider_order`, aggiungere
  `cache_write_tokens = 3.00` ai prezzi. In `BACKEND_PER_PROVIDER`: `"moonshot": Backend(OpenAIChatGateway, _client_openai)`.
  Nel `.env`: `ORC2_MOONSHOT_KEY`.

## 3. MiniMax (diretto)

- **Che cos'era.** Il fornitore del modello economico (nel tempo `minimax-m2-7`, poi `minimax-m3`), con la chiave
  `ORC2_MINIMAX_KEY` e indirizzo `https://api.minimax.io/v1`.
- **Scollegato da:** `models.toml` (`[providers.minimax]`), `BACKEND_PER_PROVIDER["minimax"]`, `.env.example`.
  `minimax-m3` e' ora raggiunto solo tramite OpenRouter, con il fornitore fissato su `minimax/fp8` (l'endpoint di MiniMax; il 12 ottobre, dopo una run in cui senza fissarlo OpenRouter lo aveva instradato a un fornitore quantizzato piu' economico).
- **Perche'.** Una chiave in meno; M3 non e' mai stato chiamato direttamente nel progetto.
- **Cosa si perde.** Il listino MiniMax ufficiale e' 0,30 / 1,20 dollari fino a 512k token di input (oltre, 0,60 / 2,40),
  lettura cache 0,06 (platform.minimax.io). La scrittura in cache di M2.7 era a 0,375: per M3 non e' elencata.
- **Come ricollegare.**
  ```toml
  [providers.minimax]
  monthly_fee = 0.0
  base_url    = "https://api.minimax.io/v1"   # rotta OpenAI-compatible, verificata
  api_key_env = "ORC2_MINIMAX_KEY"
  ```
  poi `provider = "minimax"` e il nome API ufficiale in `[models.minimax-m3]`; in `BACKEND_PER_PROVIDER`:
  `"minimax": Backend(OpenAIChatGateway, _client_openai)`. Nel `.env`: `ORC2_MINIMAX_KEY`.

## 4. OpenAI (diretto)

- **Che cos'era.** Il fornitore dell'unico modello di embedding, `text-embedding-3-small` (per RAG e per il router
  appreso), con la chiave `ORC2_OPENAI_KEY` e indirizzo `https://api.openai.com/v1`.
- **Scollegato da:** `models.toml` (`[providers.openai]`), `BACKEND_PER_PROVIDER["openai"]`, `.env.example`.
  Il modello ora ha `provider = "openrouter"` e `api_model = "openai/text-embedding-3-small"` (0,02 dollari per milione,
  letto dall'elenco di OpenRouter il 12 ottobre 2026).
- **Perche'.** Una chiave in meno. Oggi nessun codice del progetto chiama gli embedding: la voce e' solo di listino.
- **Cosa si perde.** Nulla finche' non esiste un gateway per gli embedding; quando verra' scritto andra' provato su
  OpenRouter (endpoint `/embeddings`).
- **Come ricollegare.**
  ```toml
  [providers.openai]
  monthly_fee = 0.0
  base_url    = "https://api.openai.com/v1"
  api_key_env = "ORC2_OPENAI_KEY"
  ```
  poi `provider = "openai"` e togliere `api_model` in `[models.text-embedding-3-small]`.

## 5. Tripo (generazione 3D)

- **Che cos'era.** `[providers.tripo]` (`monthly_fee = 0.0`, pay-as-you-go, chiave `ORC2_TRIPO_KEY`), usato solo da un
  esempio **commentato** di modello 3D per la demo multi-capacita' (M4).
- **Scollegato da:** `models.toml` (la sezione del fornitore) e `.env.example`. L'esempio commentato `[models.tripo]`
  resta in fondo a `models.toml`, ora senza un fornitore a cui riferirsi.
- **Perche'.** Non e' raggiungibile via OpenRouter e nessun codice lo usa; non c'e' mai stato un gateway per il 3D.
- **Come ricollegare.** Rimettere
  ```toml
  [providers.tripo]
  monthly_fee = 0.0   # pay-as-you-go: nessun abbonamento richiesto
  api_key_env = "ORC2_TRIPO_KEY"
  ```
  e decommentare l'esempio, dopo aver scritto un gateway per i crediti 3D.

## 6. LiteLLM (proxy locale)

- **Che cos'era.** Un proxy in locale (`http://localhost:4000`) davanti a OpenRouter, usato come endpoint unico
  (`--via-proxy`). Un sistema personale fuori dal repository.
- **Scollegato da (tolto dal codice, non lasciato dormiente):**
  - `config.py`: `LLMSettings` e `load_llm_settings`;
  - `main.py`: `--via-proxy`, `--model`, `_run_via_proxy`;
  - `agent_factory.py`: i parametri `proxy` e `proxy_cache`, `PROXY_CACHE_AMMESSE`, `CORPO_RISPOSTA_FRESCA`;
  - `campaign.py`: `--via-proxy`, `--proxy-cache`;
  - `.env`: `ORC2_BASE_URL`, `ORC2_API_KEY`, `ORC2_MODEL`; `.env.example`: anche `ORC2_API_PROVIDER` e `ORC2_BILLING_PROVIDER`;
  - `tests/`: tutti i test del percorso via proxy.
  Resta `extra_body` in `OpenAIChatGateway`, che ora serve a OpenRouter per fissare il fornitore.
- **Perche'.** La sua cache locale di risposte replicava le richieste identiche (stesso `request_id`, 0,02 s contro
  1,4-6,2 s), falsando ripetizioni e costi. Era un sistema personale, non parte del progetto.
- **Come recuperare.** Il ramo `--via-proxy`, `LLMSettings` e `_run_via_proxy` stanno nell'ultimo commit (`fa29d3f`):
  `git show fa29d3f:main.py` e `git show fa29d3f:config.py`. `proxy_cache` e la richiesta fresca erano lavoro non
  committato e **non sono recuperabili**. Non si consiglia di ricollegarlo.

## 7. Strade per modello (non un'infrastruttura, ma una conseguenza)

- **Che cos'era.** Per confrontare due fornitori dello stesso modello (la «tassa») si era scritto, il 12 ottobre,
  il supporto a piu' strade per modello: `[models.X.routes.<fornitore>]` con listino, `api_model` e `provider_order`
  propri, `route` nel ruolo, `--route` in `main.py` e `campaign.py`, il listino scelto dal `billing_provider` del
  record (`routes_of`, `route_for`, `RouteNotFound` in `accounting/`).
- **Rimosso da:** `accounting/registry.py`, `accounting/errors.py`, `accounting/memory.py`, `campaign.py` (report),
  `agent_factory.py`, `main.py`.
- **Perche'.** Con un solo fornitore non servono, e complicavano registro, contabile e CLI.
- **Come recuperare.** **Non e' recuperabile da git**: era lavoro mai committato. Se tornassero due fornitori,
  il disegno e': strada identificata dal nome del fornitore (coincide con `billing_provider`), listino completo per
  strada (nessun prezzo ereditato), `provider_order` per strada. Va riscritto.
- **Resta, perche' serve anche con un fornitore solo:** `provider_order` per modello, `reported_cost`, `served_by`,
  lo scorporo di `cache_write_tokens`, lo schema del ledger alla versione 3.

## 8. Modelli tolti dal registro

`opus-5` (sostituito da `opus-5-5`) e `minimax-m2-7` (sostituito da `minimax-m3`) non sono piu' in `models.toml`.
Conseguenza: `python campaign.py report` sulle campagne gia' in `runs/` che usano quei modelli non ne ricalcola il
costo e li conta fra i record **senza prezzo**; i dati grezzi (`usage.jsonl`) restano intatti. I vecchi record portano
`billing_provider` di infrastrutture scollegate (`litellm`, `anthropic`, `minimax`, `moonshot`): il listino si sceglie ora
solo dal modello, quindi quel campo non influisce sul calcolo.

---

## Riferimenti rimasti di proposito

- `llm_gateway.py` (`AnthropicChatGateway`, `import anthropic`), `accounting/mappers/anthropic.py`,
  `tests/test_anthropic.py`, `requirements.txt` (`anthropic==1.2.0`): codice scollegato ma funzionante, vedi sezione 1.
- I nomi `anthropic/...`, `moonshotai/...`, `minimax/...`, `openai/...` in `models.toml`: sono i nomi con cui
  **OpenRouter** conosce i modelli e i fornitori fissati, non un collegamento diretto.
- `docs/ROADMAP.md` e `docs/PIANO_completo.md`: la storia delle decisioni, che non si riscrive.
- Citazioni di Claude, Kimi, MiniMax e simili come modelli oggetto di studio (pool, lavori correlati).
