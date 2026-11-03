"""Lettura e controlli del piano prima di avviare i pezzi dello sciame."""

import json
import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass


class PlanError(Exception):
    """Il piano non rispetta il contratto richiesto."""


def normalize_route(text: str) -> str:
    """Uniforma metodo e percorso, eliminando backtick e query."""
    parts = text.replace("`", "").strip().split(maxsplit=1)
    if len(parts) != 2:
        raise PlanError(f"rotta non valida: {text}")
    method, path = parts
    return f"{method.upper()} {''.join(path.split()).split('?', 1)[0]}"


def contract_routes(prompt: str) -> tuple[str, ...]:
    """Legge solo la tabella della sezione Routes contract."""
    active = False
    routes: list[str] = []
    for line in prompt.splitlines():
        if line.startswith("## "):
            if active:
                break
            active = line.strip() == "## Routes contract"
        elif active and line.strip().startswith("|"):
            cells = [cell.strip().replace("`", "") for cell in line.strip().split("|")[1:-1]]
            if len(cells) >= 2 and cells[0].upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                route = normalize_route(f"{cells[0]} {cells[1]}")
                if route not in routes:
                    routes.append(route)
    return tuple(routes)


@dataclass(frozen=True)
class Piece:
    """Un incarico con file propri e dipendenze esplicite."""

    id: str
    files: tuple[str, ...]
    depends_on: tuple[str, ...]
    description: str
    routes: tuple[str, ...]
    worker: str


@dataclass(frozen=True)
class Plan:
    """Stile comune e pezzi nell'ordine scelto dal planner."""

    style: str
    pieces: tuple[Piece, ...]


def parse_plan(text: str, *, routes: Sequence[str], workers: Sequence[str]) -> Plan:
    """Estrae il JSON e controlla campi, file, dipendenze e copertura delle rotte."""
    block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    source = block.group(1) if block else text[text.find("{"):text.rfind("}") + 1]
    try:
        data = json.loads(source)
    except (ValueError, TypeError) as error:
        raise PlanError(f"JSON non valido: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("style"), str):
        raise PlanError("style deve essere una stringa")
    raw_pieces = data.get("pieces")
    if not isinstance(raw_pieces, list) or not raw_pieces:
        raise PlanError("pieces deve essere una lista non vuota")

    pieces: list[Piece] = []
    ids: set[str] = set()
    owners: dict[str, str] = {}
    for raw in raw_pieces:
        if not isinstance(raw, dict):
            raise PlanError("pezzo non valido")
        piece_id = raw.get("id")
        if not isinstance(piece_id, str) or not piece_id.strip() or piece_id in ids:
            raise PlanError(f"id vuoto o duplicato: {piece_id}")
        ids.add(piece_id)
        for field in ("files", "depends_on", "routes"):
            value = raw.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise PlanError(f"{piece_id}: {field} deve essere una lista di stringhe")
        if not raw["files"]:
            raise PlanError(f"{piece_id}: files deve essere non vuota")
        if not isinstance(raw.get("description"), str):
            raise PlanError(f"{piece_id}: description deve essere una stringa")
        if raw.get("worker") not in workers:
            raise PlanError(f"{piece_id}: worker non ammesso")
        files: list[str] = []
        for filename in raw["files"]:
            normalized = posixpath.normpath(filename)
            if not filename.strip() or posixpath.isabs(filename) or normalized.startswith(".."):
                raise PlanError(f"{piece_id}: file fuori dal workspace: {filename}")
            if normalized in owners and owners[normalized] != piece_id:
                raise PlanError(f"file condiviso: {normalized}")
            owners[normalized] = piece_id
            files.append(normalized)
        pieces.append(Piece(piece_id, tuple(files), tuple(raw["depends_on"]), raw["description"],
                            tuple(normalize_route(route) for route in raw["routes"]), raw["worker"]))
    for piece in pieces:
        for dependency in piece.depends_on:
            if dependency not in ids:
                raise PlanError(f"{piece.id}: dipendenza inesistente {dependency}")
    plan = Plan(data["style"], tuple(pieces))
    _levels(plan)
    for route in routes:
        normalized = normalize_route(route)
        if sum(piece.routes.count(normalized) for piece in pieces) != 1:
            raise PlanError(f"rotta senza responsabile unico: {normalized}")
    return plan


def _levels(plan: Plan) -> dict[str, int]:
    by_id = {piece.id: piece for piece in plan.pieces}
    levels: dict[str, int] = {}
    visiting: set[str] = set()

    def visit(piece_id: str) -> int:
        if piece_id in visiting:
            raise PlanError(f"ciclo nelle dipendenze: {piece_id}")
        if piece_id not in levels:
            visiting.add(piece_id)
            levels[piece_id] = max((visit(dep) + 1 for dep in by_id[piece_id].depends_on), default=0)
            visiting.remove(piece_id)
        return levels[piece_id]

    for piece in plan.pieces:
        visit(piece.id)
    return levels


def waves(plan: Plan) -> list[list[Piece]]:
    """Raggruppa per distanza dalle radici, mantenendo l'ordine del piano."""
    levels = _levels(plan)
    return [[piece for piece in plan.pieces if levels[piece.id] == level]
            for level in range(max(levels.values(), default=-1) + 1)]
