"""Costruzione degli stimatori a partire dal protocollo."""

from collections.abc import Callable, Sequence
from typing import Any

from accounting import InMemoryAccountant
from budget_guard import BudgetGuard
from quality.estimators import D1Estimator, Estimator, FrontierJudge, HeuristicEstimator
from quality.protocol import ESTIMATORS, Protocol

HOSTED_URL = "https://api.liquid.ai/decisions/v1/systemone"
LOCAL_URL = "http://127.0.0.1:8089/v1/systemone"

#: Ordine di esecuzione: dal piu' economico al piu' caro, cosi' il tetto non affama i gratuiti.
ORDINE = ("heuristic", "d1_local_plain", "d1_local_criteria", "d1_hosted_plain",
          "d1_hosted_criteria", "frontier")


def build_estimators(protocol: Protocol, names: Sequence[str], *,
                     liquid_key: str | None = None,
                     hosted_url: str = HOSTED_URL, local_url: str = LOCAL_URL,
                     make_frontier_gateway: Callable[[], Any] | None = None) -> dict[str, Estimator]:
    """Gli stimatori richiesti, nell'ordine di esecuzione.

    Args:
        protocol: il protocollo (testi, domanda, criteri).
        names: quali stimatori; vedi `quality.protocol.ESTIMATORS`.
        liquid_key: la chiave dell'API ospitata di d1; serve solo se ne chiedi uno ospitato.
        hosted_url: indirizzo dell'API ospitata.
        local_url: indirizzo di `llama-server` con d1-3B.
        make_frontier_gateway: costruisce (gateway, contabile) per il giudice; serve solo per `frontier`.

    Raises:
        ValueError: nome sconosciuto, chiave mancante per un d1 ospitato o costruttore del
            gateway mancante per il frontier.
    """
    sconosciuti = [n for n in names if n not in ESTIMATORS]
    if sconosciuti:
        raise ValueError(f"stimatori sconosciuti: {', '.join(sconosciuti)}; ammessi: {', '.join(ESTIMATORS)}")
    risultato: dict[str, Estimator] = {}
    for nome in ORDINE:
        if nome not in names:
            continue
        if nome == "heuristic":
            risultato[nome] = HeuristicEstimator()
        elif nome.startswith("d1_"):
            ospitato = nome.startswith("d1_hosted")
            if ospitato and not liquid_key:
                raise ValueError("manca LIQUID_API_KEY: serve per gli stimatori d1 ospitati")
            risultato[nome] = D1Estimator(
                nome, url=hosted_url if ospitato else local_url,
                state_template=protocol.state_template, question=protocol.question,
                api_key=liquid_key if ospitato else None, model="d1" if ospitato else None,
                criteria=protocol.criteria if nome.endswith("criteria") else None)
        else:
            if make_frontier_gateway is None:
                raise ValueError("per il giudice frontier serve un costruttore del gateway")
            risultato[nome] = FrontierJudge(
                nome, make_gateway=make_frontier_gateway,
                system_prompt=protocol.frontier_system, user_template=protocol.frontier_user_template)
    return risultato


def frontier_gateway_maker(factory: Any, model: str) -> Callable[[], Any]:
    """Un costruttore di (gateway, contabile) per il giudice, dalla fabbrica degli agenti.

    Ogni thread ne chiama uno e ha il suo contabile: il costo di un giudizio si legge
    senza mescolarsi con quello degli altri. Il tetto di spesa lo governa l'esecutore.
    """
    def costruisci() -> tuple[Any, Any]:
        contabile = InMemoryAccountant(factory.registry)
        return factory.make_gateway(model, contabile, BudgetGuard(None)), contabile
    return costruisci
