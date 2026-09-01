"""Configurazione centralizzata: costanti di comportamento e segreti di connessione.

Nessun altro modulo contiene valori "magici" o legge direttamente l'ambiente:
tutti importano da qui. Oltre alla pulizia, il motivo è sperimentale — queste
costanti sono le variabili degli esperimenti della tesi, e averle in un solo
punto rende le esecuzioni riproducibili e confrontabili.

I segreti vivono nel file `.env` (non versionato), caricato solo dal punto di
ingresso. Da M2s.2 ce n'e' uno per fornitore: `load_llm_settings` serve il
percorso mono-agente, `credenziali_fornitore` quello per ruolo.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

def richiedi_env(nome: str) -> str:
    """Legge una variabile d'ambiente obbligatoria, fallendo subito se manca.

    A differenza di `os.getenv`, che restituisce silenziosamente `None`, applica
    il principio *fail-fast*: meglio un errore chiaro all'avvio che un errore
    incomprensibile a metà di un task già costato token.

    Args:
        nome: nome della variabile da leggere.

    Returns:
        Il valore della variabile.

    Raises:
        RuntimeError: se la variabile non è definita né nell'ambiente né nel `.env`.
    """
    valore = os.getenv(nome)
    if valore is None:
        raise RuntimeError(f"Variabile d'ambiente mancante: {nome}")
    return valore

@dataclass(frozen=True)
class LLMSettings:
    """Dati di connessione caricati solo dal punto d'ingresso dell'applicazione."""

    base_url: str
    api_key: str
    model: str
    api_provider: str
    billing_provider: str


def load_llm_settings(
    *, model_override: str | None = None, dotenv_path: str | Path | None = None
) -> LLMSettings:
    """Carica i segreti al runtime, non durante l'import dei moduli.

    Separare il caricamento dall'import rende possibile usare `Agent`, i test e
    gli strumenti di sviluppo senza avere un `.env` locale o una API key.
    """
    load_dotenv(dotenv_path=dotenv_path)
    return LLMSettings(
        base_url=richiedi_env("ORC2_BASE_URL"),
        api_key=richiedi_env("ORC2_API_KEY"),
        model=model_override or richiedi_env("ORC2_MODEL"),
        api_provider=os.getenv("ORC2_API_PROVIDER", "litellm"),
        billing_provider=os.getenv("ORC2_BILLING_PROVIDER", "openrouter"),
    )


@dataclass(frozen=True)
class ProviderCredentials:
    """Come raggiungere un fornitore specifico.

    Attributes:
        provider: nome del fornitore, come compare in `[providers.*]`.
        base_url: endpoint dichiarato nel registro, oppure `None` per usare
            quello di default dell'SDK.
        api_key: il segreto, letto dall'ambiente. Non compare mai nel registro.
    """

    provider: str
    base_url: str | None
    api_key: str


def credenziali_fornitore(provider: str, dati_provider: dict) -> ProviderCredentials:
    """Risolve le credenziali di un fornitore a partire dai suoi dati a registro.

    Nota di design (tesi):
        La separazione fra *nome* e *valore* del segreto non e' formalismo. Il
        registro viene letto dai test, stampato nei messaggi d'errore e in
        prospettiva serializzato nei log: una chiave dichiarata li' dentro
        uscirebbe da qualche parte. Il registro conosce il nome della
        variabile, l'ambiente conosce il valore, e i due si incontrano solo
        qui.

        `base_url` e `api_key_env` sono facoltativi nel registro perche' un
        `models.toml` di soli prezzi deve restare valido — e' cio' che usano i
        test. Il costo di quella scelta e' che l'assenza va gestita al momento
        dell'uso: e' questa funzione a pretenderli, non il caricamento.

    Args:
        provider: nome del fornitore.
        dati_provider: la sua voce in `[providers.*]`, come la restituisce
            `ModelRegistry.providers`.

    Returns:
        Le credenziali pronte per costruire un client.

    Raises:
        RuntimeError: se il fornitore non dichiara `api_key_env`, oppure se la
            variabile dichiarata non e' definita nell'ambiente. Il messaggio
            nomina **sia il fornitore sia la variabile**: con cinque fornitori
            un "manca una chiave" non basta a capire quale.
    """
    nome_variabile = dati_provider.get("api_key_env")
    if not nome_variabile:
        raise RuntimeError(
            f"il fornitore '{provider}' non dichiara 'api_key_env' in models.toml: "
            f"non si puo' costruire un client senza sapere dove sta la sua chiave"
        )

    valore = os.getenv(nome_variabile)
    if valore is None:
        raise RuntimeError(
            f"il fornitore '{provider}' richiede la variabile d'ambiente "
            f"'{nome_variabile}', che non e' definita. Vedi .env.example"
        )

    return ProviderCredentials(
        provider=provider,
        base_url=dati_provider.get("base_url"),
        api_key=valore,
    )


# --- COMPORTAMENTO AGENTE ---
MAX_ITERAZIONI = 30
RETRY_MAX = 3
RETRY_DELAY = 2

# -- LOOP DETECTION --
# Due soglie per una escalation graduale "prima avvisa, poi ferma": alla 4ª
# ripetizione identica il modello riceve un richiamo e può ancora correggersi,
# alla 7ª il task viene interrotto.
LOOP_THRESHOLD = 7
ALERT_THRESHOLD = 4

# -- SANDBOX DOCKER --
# Limiti del container in cui gira il tool `bash`, per contenere i danni di un
# comando sbagliato o malevolo.
DOCKER_IMAGE = "debian:bookworm-slim"
DOCKER_MEMORY = "512m"
DOCKER_PIDS_LIMIT = "256"
EXEC_TIMEOUT = 60

# -- LOGGING --
# Unica costante con default: il livello di log è comodità di sviluppo, non
# configurazione critica, quindi la sua assenza non deve bloccare l'avvio.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
