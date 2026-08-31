"""Configurazione centralizzata: costanti di comportamento e segreti di connessione.

Nessun altro modulo contiene valori "magici" o legge direttamente l'ambiente:
tutti importano da qui. Oltre alla pulizia, il motivo è sperimentale — queste
costanti sono le variabili degli esperimenti della tesi, e averle in un solo
punto rende le esecuzioni riproducibili e confrontabili.

I segreti vivono nel file `.env` (non versionato), caricato solo dal punto di
ingresso tramite `load_llm_settings`.
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
