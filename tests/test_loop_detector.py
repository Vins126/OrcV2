"""Test del rilevatore di cicli improduttivi.

Verificano le due proprietà che definiscono il componente: l'escalation
progressiva al ripetersi della stessa azione, e l'azzeramento del contatore
quando l'agente cambia comportamento.

Le soglie sono passate esplicitamente e ridotte (2 e 3) invece di usare quelle di
`config`: il test descrive così il *comportamento* del rilevatore, restando valido
anche se le soglie di produzione vengono ritarate.
"""

from types import SimpleNamespace

from loop_detector import RilevatoreLoop
from alerts import Alerts


def _finta_chiamata(nome, argomenti):
    # Ricrea la forma di una vera tool_call: serve .function.name e .function.arguments
    """Costruisce una tool call minima con la struttura attesa dal rilevatore.

    Args:
        nome: nome del tool invocato.
        argomenti: argomenti come stringa grezza, così come arriverebbero dall'API.

    Returns:
        Un oggetto con gli attributi `.function.name` e `.function.arguments`.
    """
    return SimpleNamespace(function=SimpleNamespace(name=nome, arguments=argomenti))


def test_escalation_loop():
    """Ripetere la stessa azione porta a OK, poi AVVISA, poi FERMA.

    Verifica che la reazione sia proporzionata e non binaria: la prima
    ripetizione è tollerata, la seconda merita un richiamo, la terza
    l'interruzione.
    """
    rilevatore = RilevatoreLoop(soglia_avviso=2, soglia_stop=3)
    chiamata = [_finta_chiamata("bash", "{}")]

    assert rilevatore.in_loop_verdict(chiamata) == Alerts.OK       # 1ª volta
    assert rilevatore.in_loop_verdict(chiamata) == Alerts.AVVISA   # 2ª -> soglia avviso
    assert rilevatore.in_loop_verdict(chiamata) == Alerts.FERMA    # 3ª -> soglia stop


def test_chiamata_diversa_azzera():
    """Un'azione diversa è considerata progresso e riporta il contatore a uno.

    È la garanzia contro i falsi positivi: un agente che sta effettivamente
    avanzando non deve essere fermato solo perché ha ripetuto qualcosa in
    precedenza.
    """
    rilevatore = RilevatoreLoop(soglia_avviso=2, soglia_stop=3)
    bash = [_finta_chiamata("bash", "{}")]
    read = [_finta_chiamata("read_file", '{"path": "x"}')]

    rilevatore.in_loop_verdict(bash)                       # ripetizioni = 1
    rilevatore.in_loop_verdict(bash)                       # ripetizioni = 2 (AVVISA)
    verdetto = rilevatore.in_loop_verdict(read)            # chiamata DIVERSA -> azzera
    assert verdetto == Alerts.OK                           # riparte da capo
