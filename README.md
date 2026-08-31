# ORC V2

ORC V2 e' un agente ReAct con tool sandboxati e accounting per singola run.
L'obiettivo attuale non e' ancora il routing automatico: e' produrre esecuzioni
riproducibili, misurabili e confrontabili prima di introdurre piu' agenti o piu'
modelli.

## Avvio rapido

```bash
cd OrcV2
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Compila .env con il proxy e la sua API key
python agent.py "crea un file hello.txt con scritto ciao"
```

Il progetto usa un endpoint compatibile OpenAI. Con LiteLLM come proxy, il valore
di `ORC2_MODEL` deve essere sia un alias esposto dal proxy sia una chiave presente
in `models.toml`: il primo decide dove inoltrare la richiesta, il secondo permette
di calcolarne il costo.

## Comandi utili

```bash
# Vedi tutte le opzioni senza contattare il provider
python agent.py --help

# Scegli un modello registrato e applica un tetto in USD alla sola run corrente
python agent.py --model minimax-m2-7 --budget-usd 0.01 "analizza il workspace"

# Isola i file prodotti e i ledger di un esperimento
python agent.py --workspace /tmp/orc-work --runs-dir /tmp/orc-runs "..."

# Test deterministici, senza rete e senza costi
pytest -q
```

Il budget e' controllato prima di ogni nuova chiamata. Poiche' un costo si conosce
solo dopo una risposta, puo' superare il tetto del costo di una singola chiamata;
lo sforamento viene registrato nel ledger.

## Mappa dell'architettura

```text
main.py
  ├─ config.load_llm_settings()     segreti e configurazione runtime
  ├─ tools.build_default_tools()    workspace + sandbox Docker
  ├─ OpenAIChatGateway              API, retry, mapper, accounting, budget
  │    ├─ InMemoryAccountant        calcolo del costo
  │    └─ LedgerAccountant          persistenza dell'usage
  └─ RunSession
       ├─ Agent                     ciclo ReAct e tool call
       ├─ RunLedger                 JSONL append-only + summary
       └─ RunReporter               output umano di fine run
```

| Se devi cambiare... | Punto da modificare |
|---|---|
| Prezzo, capacita' o modello | `models.toml` |
| Proxy/API key/modello di default | `.env` |
| Formato usage di un endpoint | `accounting/mappers/` |
| Politica di retry/API | `llm_gateway.py` |
| Limite di spesa | flag `--budget-usd` / `budget_guard.py` |
| Tool disponibili o sandbox | `tools/` ed `executors/` |
| Flusso ReAct | `agent.py` |
| CLI e cablaggio delle dipendenze | `main.py` |

## Dati prodotti da una run

Ogni run crea `runs/<run_id>/`:

- `usage.jsonl`: una riga append-only per ogni consumo prezzato;
- `events.jsonl`: budget, errori provider, usage non prezzabile e terminazioni;
- `summary.json`: riepilogo derivato dai file precedenti.

I log non contengono prompt completi o API key. Le run vecchie non vengono mai
riscritte: `schema_version` permette di distinguerne il formato.

## Principi di manutenzione

- `Agent` non deve dipendere da SDK, prezzi, file o proxy.
- I mapper trasformano payload esterni in `UsageRecord`; non calcolano costi.
- Il ledger conserva fatti, non prende decisioni.
- Le policy (budget, retry) fermano o regolano il gateway prima della rete.
- Ogni bug corretto va accompagnato da un test senza rete.
