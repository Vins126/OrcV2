"""Gli stati con cui puo' chiudersi una run.

Nota di design (tesi):
    Fino a M3.0b gli stati erano stringhe sparse in `agent.py`, `run_session.py`,
    `run_reporter.py`, `campaign.py` e `main.py`: un errore di battitura in uno di
    questi posti non produceva nessun errore, solo una causa di fallimento
    sbagliata nel report. Un'enumerazione li raccoglie in un posto solo.

    `StrEnum` e' voluto: i valori restano le stringhe di prima, quindi i
    `summary.json` gia' scritti in `runs/` (il dataset della tesi) e i confronti
    con `"completed"` continuano a funzionare senza migrazioni.
"""

from enum import StrEnum


class RunStatus(StrEnum):
    """Come e' finita una run."""

    # Esiti dell'agente
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    LOOP_DETECTED = "loop_detected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNEXPECTED_ERROR = "unexpected_error"

    # Esiti del turno finale che prima passavano per "completato"
    EMPTY_RESPONSE = "empty_response"        # il modello ha chiuso senza dire nulla
    OUTPUT_TRUNCATED = "output_truncated"    # fermato dal limite di token
    REFUSED = "refused"                      # rifiuto o filtro dei contenuti
    PROVIDER_ERROR = "provider_error"        # il fornitore ha dichiarato un errore
