"""Policy di spesa opzionale per una singola run dell'agente."""

from enum import Enum
from math import isfinite


class BudgetVerdict(Enum):
    """Esito del controllo pre-chiamata del budget."""

    OK = "ok"
    SOFT_LIMIT_REACHED = "soft_limit_reached"
    HARD_LIMIT_REACHED = "hard_limit_reached"


class BudgetExceeded(Exception):
    """Il costo gia' osservato non consente ulteriori chiamate remote."""


class BudgetGuard:
    """Applica un tetto in USD al costo gia' registrato di una singola run.

    Il guardiano non stima il costo futuro: prima di una chiamata puo' sapere
    soltanto quanto e' gia' stato speso. Per questo puo' impedire la chiamata
    *successiva* al superamento del tetto, non quella che lo ha superato.
    """

    DEFAULT_SOFT_RATIO = 0.8

    def __init__(self, hard_limit_usd: float | None, *, soft_ratio: float = DEFAULT_SOFT_RATIO):
        if hard_limit_usd is not None and (
            not isfinite(hard_limit_usd) or hard_limit_usd <= 0
        ):
            raise ValueError("hard_limit_usd deve essere un numero finito maggiore di zero")
        if not 0 < soft_ratio < 1:
            raise ValueError("soft_ratio deve essere strettamente compreso tra zero e uno")

        self.hard_limit_usd = hard_limit_usd
        self.soft_ratio = soft_ratio
        self.soft_limit_usd = (
            hard_limit_usd * soft_ratio if hard_limit_usd is not None else None
        )
        self._soft_warning_emitted = False

    @property
    def enabled(self) -> bool:
        """Indica se la run ha un limite di spesa attivo."""
        return self.hard_limit_usd is not None

    @property
    def policy_details(self) -> dict[str, float | bool | None]:
        """Policy serializzabile da registrare nel ledger all'avvio."""
        return {
            "enabled": self.enabled,
            "hard_limit_usd": self.hard_limit_usd,
            "soft_limit_usd": self.soft_limit_usd,
            "soft_ratio": self.soft_ratio,
        }

    def check(self, total_cost_usd: float) -> BudgetVerdict:
        """Restituisce il verdetto per la prossima chiamata, senza effetti esterni."""
        if not self.enabled:
            return BudgetVerdict.OK
        if total_cost_usd >= self.hard_limit_usd:
            return BudgetVerdict.HARD_LIMIT_REACHED
        if total_cost_usd >= self.soft_limit_usd and not self._soft_warning_emitted:
            self._soft_warning_emitted = True
            return BudgetVerdict.SOFT_LIMIT_REACHED
        return BudgetVerdict.OK
