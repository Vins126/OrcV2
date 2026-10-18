"""Mutanti di una soluzione: piccoli guasti tipici, introdotti nell'albero sintattico."""

import ast
import copy
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Mutant:
    """Una soluzione con un solo guasto introdotto.

    Attributes:
        operator: il tipo di guasto (`compare`, `arithmetic`, `constant`, `boolean`, `return`).
        line: riga del codice originale in cui e' stato introdotto.
        source: il codice del mutante, in forma normalizzata.
    """

    operator: str
    line: int
    source: str


def normalize(source: str) -> str:
    """Il codice riscritto in forma canonica (commenti e spaziature uniformati).

    Serve a presentare allo stimatore **tutti** gli esempi, giusti e mutanti, nella
    stessa forma: altrimenti la sola formattazione tradirebbe i mutanti.

    Raises:
        ValueError: se il codice non e' Python valido.
    """
    return ast.unparse(_analizza(source))


def _analizza(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as errore:
        raise ValueError(f"il codice non e' Python valido: {errore}") from errore


#: Come si scambia un confronto: l'errore tipico e' `<` al posto di `<=` e simili.
_CONFRONTI: dict[type, type] = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
#: Come si scambia un operatore aritmetico.
_ARITMETICA: dict[type, type] = {
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.FloorDiv: ast.Mult,
}


class _Mutatore(ast.NodeTransformer):
    """Introduce **un solo** guasto: quello della posizione `target` nella lista dei siti.

    Si esegue due volte per ogni guasto possibile: una per contare i siti
    (`target=-1`, non cambia niente), una per applicare il guasto numero `target`.
    I siti si numerano nell'ordine di visita dell'albero, quindi in modo stabile.
    """

    def __init__(self, target: int):
        self.target = target
        self.siti: list[tuple[str, int]] = []      # (operatore, riga) di ogni sito visto
        self.applicato: tuple[str, int] | None = None

    def _sito(self, operatore: str, riga: int) -> bool:
        """Registra un sito e dice se e' quello da mutare."""
        self.siti.append((operatore, riga))
        if len(self.siti) - 1 == self.target:
            self.applicato = (operatore, riga)
            return True
        return False

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) == 1 and type(node.ops[0]) in _CONFRONTI:
            if self._sito("compare", node.lineno):
                node.ops = [_CONFRONTI[type(node.ops[0])]()]
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if type(node.op) in _ARITMETICA and self._sito("arithmetic", node.lineno):
            node.op = _ARITMETICA[type(node.op)]()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # Solo i numeri interi: stringhe e docstring non si toccano, i booleani nemmeno.
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            for delta in (+1, -1):
                if self._sito("constant", node.lineno):
                    return ast.copy_location(ast.Constant(node.value + delta), node)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if self._sito("boolean", node.lineno):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def _nega_test(self, node: ast.If | ast.While | ast.IfExp) -> ast.AST:
        self.generic_visit(node)
        if self._sito("boolean", node.lineno):
            node.test = ast.copy_location(ast.UnaryOp(ast.Not(), node.test), node.test)
        return node

    visit_If = visit_While = visit_IfExp = _nega_test

    def visit_Return(self, node: ast.Return) -> ast.AST:
        self.generic_visit(node)
        if node.value is not None and self._sito("return", node.lineno):
            node.value = ast.copy_location(ast.Constant(None), node.value)
        return node


def generate_mutants(source: str, *, seed: int = 0, max_mutants: int | None = None) -> list[Mutant]:
    """Tutti i mutanti a un solo guasto di `source`, senza doppioni e diversi dall'originale.

    Se `max_mutants` e' dato se ne tiene un campione, scelto con il seme e restituito
    nell'ordine originale.

    Raises:
        ValueError: se `source` non e' Python valido.
    """
    albero = _analizza(source)
    originale = ast.unparse(albero)
    conteggio = _Mutatore(target=-1)
    conteggio.visit(copy.deepcopy(albero))
    mutanti: list[Mutant] = []
    visti = {originale}
    for k in range(len(conteggio.siti)):
        mutatore = _Mutatore(target=k)
        mutato = ast.fix_missing_locations(mutatore.visit(copy.deepcopy(albero)))
        codice = ast.unparse(mutato)
        if codice in visti or mutatore.applicato is None:
            continue
        visti.add(codice)
        operatore, riga = mutatore.applicato
        mutanti.append(Mutant(operator=operatore, line=riga, source=codice))
    if max_mutants is not None and len(mutanti) > max_mutants:
        scelti = sorted(random.Random(seed).sample(range(len(mutanti)), max_mutants))
        mutanti = [mutanti[i] for i in scelti]
    return mutanti
