"""Configurazione centralizzata: costanti di comportamento e segreti di connessione.

Nessun altro modulo contiene valori "magici" o legge direttamente l'ambiente:
tutti importano da qui. Oltre alla pulizia, il motivo è sperimentale — queste
costanti sono le variabili degli esperimenti della tesi, e averle in un solo
punto rende le esecuzioni riproducibili e confrontabili.

I segreti vivono nel file `.env` (non versionato), caricato all'import.
"""

import os
from dotenv import load_dotenv

load_dotenv()

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

# --CONNESSIONE LLM --
# Puntano a un proxy compatibile con l'API OpenAI (es. LiteLLM): è il punto di
# indirezione che in M2 permetterà di cambiare o aggiungere modelli senza
# toccare il codice dell'agente.
ORC2_BASE_URL = richiedi_env("ORC2_BASE_URL")
ORC2_API_KEY = richiedi_env("ORC2_API_KEY")
ORC2_MODEL = richiedi_env("ORC2_MODEL")


# --- COMPORTAMENTO AGENTE --
MAX_ITERAZIONI = 30   # Tetto ai passi ReAct: garantisce la terminazione e limita il costo
RETRY_MAX = 3         # Tentativi prima di dichiarare l'LLM irraggiungibile
RETRY_DELAY = 2       # Base del backoff esponenziale: attese di 2^0, 2^1, 2^2 = 1s, 2s, 4s

# -- LOOP DETECTION --
# Due soglie per una escalation graduale "prima avvisa, poi ferma": alla 4ª
# ripetizione identica il modello riceve un richiamo e può ancora correggersi,
# alla 7ª il task viene interrotto.
LOOP_THRESHOLD = 7    # Ripetizioni identiche che causano l'arresto (FERMA)
ALERT_THRESHOLD = 4   # Ripetizioni identiche che causano l'avviso (AVVISA)

# -- SANDBOX DOCKER --
# Limiti del container in cui gira il tool `bash`, per contenere i danni di un
# comando sbagliato o malevolo.
DOCKER_IMAGE = "debian:bookworm-slim"
DOCKER_MEMORY = "512m"
DOCKER_PIDS_LIMIT = "256"   # Anti fork-bomb
EXEC_TIMEOUT = 60           # Secondi oltre i quali un comando è considerato bloccato

# -- LOGGING --
# Unica costante con default: il livello di log è comodità di sviluppo, non
# configurazione critica, quindi la sua assenza non deve bloccare l'avvio.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
