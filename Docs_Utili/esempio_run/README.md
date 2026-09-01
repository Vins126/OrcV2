# Due esecuzioni reali

Copie non modificate di due run archiviate il 24 agosto 2026. Non sono esempi
costruiti: sono i file che il sistema ha prodotto da solo, riportati qui perche'
la directory `runs/` non e' versionata (sono dati sperimentali, non codice).

Il task e' lo stesso in entrambe — lo si vede dal `task_hash` identico — ma il
tetto di spesa e' diverso. Del testo del task si conserva soltanto l'hash: nei
log non finiscono mai prompt completi ne' chiavi API.

---

## `completata/` — il caso normale

Sei iterazioni ReAct, sei chiamate prezzate, **$0.00116802** in totale.

```json
"status": "completed",
"iterations": 6,
"usage_count": 6,
"event_count": 0,
"cost_by_model":     { "minimax-m2-7": 0.00116802 },
"cost_by_operation": { "chat_completion": 0.00116802 },
"quantities_by_unit": {
  "input_tokens": 1857.0, "output_tokens": 530.0, "cached_input_tokens": 3559.0
}
```

Tre cose da notare.

**`event_count: 0`, e infatti non esiste alcun `events.jsonl`.** Nulla di
anomalo e' accaduto: niente errori del provider, niente soglie di budget,
nessun consumo non prezzabile. L'assenza del file *e'* l'informazione.

**Le quantita' sono tenute separate per unita'.** I 3559 token serviti dalla
cache non sono sommati ai 1857 di input: hanno una tariffa propria e vengono
moltiplicati per quella. Confonderli e' l'errore che gonfierebbe silenziosamente
ogni misura della campagna.

**I costi sono decomposti per modello e per operazione.** Con un modello solo la
decomposizione e' banale; e' la struttura che servira' a M4, quando gli agenti
saranno molti e la domanda diventera' *quale ruolo ha speso cosa*.

Nella prima riga di `usage.jsonl` si vede anche il resto di cio' che ogni
chiamata registra: `latency_s`, `attempt`, `finish_reason`, `n_tool_calls`,
`reasoning_tokens` — e i due campi `api_provider` / `billing_provider`, che
distinguono *chi e' stato chiamato* da *chi fattura*.

---

## `budget-esaurito/` — il caso limite, osservato

Stesso task, tetto fissato a **$0.0006**. La run si e' fermata da sola.

```json
"status": "budget_exhausted",
"iterations": 4,
"usage_count": 3,
"total_cost": 0.0006138
```

E nei tre eventi registrati:

| Evento | Cosa dice |
|---|---|
| `budget_policy` | la policy con cui la run e' partita: tetto $0.0006, soglia morbida derivata all'80% |
| `budget_exhausted` | il tetto e' stato raggiunto: speso $0.0006138, **sforamento $0.0000138** |
| `run_terminated` | la run si e' chiusa con esito `budget_exhausted` alla quarta iterazione |

### Perche' questa run e' il documento piu' interessante del repository

Il costo di una chiamata si conosce **solo dopo averla fatta**. Un controllo che
precede la chiamata non puo' quindi impedire all'ultima di sforare: puo' solo
impedire che ne parta un'altra. Ne segue che **lo sforamento massimo possibile e'
il costo di una singola chiamata**.

Questo e' scritto nella tesi come limite teorico del modello di fatturazione a
consumo (`TESI_master.md` §9.6). Qui lo si vede accadere: il tetto era $0.0006,
la spesa e' arrivata a $0.0006138, lo sforamento e' stato di **$0.0000138** —
cioe' meno del costo dell'ultima chiamata, e la quarta iterazione si e'
interrotta prima di toccare la rete.

Non e' un difetto corretto: e' una **previsione verificata**, e il sistema la
riporta da solo nei propri log invece di lasciarla dedurre.
