"""Vista del sito nel workspace, con diagnostica e screenshot per il modello."""

from pathlib import Path
from typing import Any, Callable

from accounting.errors import NoActiveRun
from renderer import WIDTHS, RenderResult, render_site
from tools.base import Tool, ToolResult


class ViewSiteError(Exception):
    """Gli argomenti non permettono di guardare il sito."""


class ViewSiteTool(Tool):
    """Mostra il sito usando un renderer iniettato e la cartella della run."""

    def __init__(self, workspace: Path | str, event_sink: Any | None, *,
                 render: Callable[..., RenderResult] = render_site) -> None:
        self.workspace = Path(workspace)
        self.event_sink = event_sink
        self.render = render
        self._view_count = 0

    @property
    def name(self) -> str:
        """Nome esposto al modello."""
        return "view_site"

    @property
    def description(self) -> str:
        """Descrizione mostrata al modello."""
        return (
            "Avvia il sito del workspace con start.sh sulla porta 8080 nel renderer. "
            "Restituisce errori di console, sbordo orizzontale, violazioni di "
            "accessibilita' gravi e uno screenshot a pagina intera per larghezza. "
            "Il sito si rende sempre a tutte le larghezze: widths (facoltativo) sceglie "
            "solo quali risultati e screenshot ricevi; senza, li ricevi tutti."
        )

    @property
    def parameters(self) -> dict:
        """Larghezze facoltative, scelte fra quelle previste dal renderer."""
        return {
            "type": "object",
            "properties": {
                "widths": {"type": "array", "items": {"type": "integer", "enum": list(WIDTHS)}},
            },
        }

    def execute(self, args: dict) -> ToolResult:
        """Valida le larghezze prima di avviare il sito e conserva la vista nella run."""
        widths = args.get("widths", list(WIDTHS))
        if not isinstance(widths, list) or not widths:
            raise ViewSiteError(f"widths deve essere una lista non vuota di larghezze: {widths!r}")
        for width in widths:
            if type(width) is not int or width not in WIDTHS:
                raise ViewSiteError(f"larghezza non ammessa: {width!r}; disponibili: {WIDTHS}")
        if self.event_sink is None:
            raise NoActiveRun("view_site richiede un event_sink con una run attiva")
        ledger = self.event_sink.require_active()
        self._view_count += 1
        out_dir = ledger.run_dir / "viste" / f"{self._view_count:03d}"
        result = self.render(self.workspace, out_dir, script=None)
        data = {"started": result.started, "start_error": result.start_error, "widths": {}}
        images = []
        if result.started:
            for width in sorted(set(widths)):
                view = result.widths[width]
                data["widths"][str(width)] = {
                    "errors": view.errors, "overflow": view.overflow, "a11y": view.a11y,
                }
                if view.screenshot is not None:
                    images.append(view.screenshot)
        return ToolResult(data=data, images=tuple(images))
