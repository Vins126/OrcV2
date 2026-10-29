"""Test di R2.1: lo strumento «guarda il sito» e le immagini nella conversazione.

Cosa si verifica (criteri della spec di R2.1):
    C1  `view_site` restituisce testo e screenshot delle larghezze richieste e non
        passa mai lo script di valutazione al renderer;
    C2  nella conversazione restano solo le immagini dell'ultima vista;
    C3  il gateway OpenAI-compatibile (OpenRouter) manda il messaggio `tool` con
        le immagini cosi' com'e' (P6-D1: immagini dentro il messaggio `tool`);
    C4  con Docker vero arriva uno screenshot PNG (`ORC_INTEGRATION=1`).
C5 (un modello vero legge lo screenshot) costa e non sta nella suite.

Nota di design (tesi):
    Il renderer si inietta nel costruttore dello strumento: qui e' un finto che
    scrive PNG su disco, cosi' la suite non lancia Docker e non spende.
"""

import base64
import json
import os
import shutil
from pathlib import Path

import pytest

from agent import NOTA_IMMAGINI_RIMOSSE, Agent
from llm_contracts import AssistantTurn, ToolCall
from llm_gateway import OpenAIChatGateway
from renderer import WIDTHS, RenderResult, WidthResult
from tools import build_default_tools
from tools.base import ToolResult
from accounting.errors import NoActiveRun
from renderer import RenderError
from tools.view_site import ViewSiteError, ViewSiteTool

PNG = b"\x89PNG\r\n\x1a\n finto"


# ── Finti ─────────────────────────────────────────────────────────────────

class _Ledger:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir


class _Corrente:
    """Imita `CurrentRun`: `require_active()` restituisce il registro della run."""

    def __init__(self, run_dir: Path):
        self._ledger = _Ledger(run_dir)
        self.eventi: list = []

    def require_active(self):
        return self._ledger

    def append_event(self, event_type, details):
        self.eventi.append((event_type, details))


class _RenderFinto:
    """Fa la parte di `render_site`: registra gli argomenti e scrive un PNG per larghezza."""

    def __init__(self, *, started=True, start_error=None):
        self.chiamate: list = []
        self.started, self.start_error = started, start_error

    def __call__(self, workspace, out_dir, **kwargs):
        self.chiamate.append({"workspace": Path(workspace), "out_dir": Path(out_dir), **kwargs})
        if not self.started:
            return RenderResult(started=False, start_error=self.start_error)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        larghezze = {}
        for w in WIDTHS:
            shot = out / f"shot-{w}.png"
            shot.write_bytes(PNG + str(w).encode())
            larghezze[w] = WidthResult(width=w, errors=[f"errore a {w}"], overflow=(w == 375),
                                       screenshot=shot, a11y=[{"id": "color-contrast", "impact": "serious",
                                                               "nodes": 2}])
        return RenderResult(started=True, widths=larghezze, versions={"chromium": "x"})


def _strumento(tmp_path, render=None):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    (ws / "start.sh").write_text("python3 -m http.server 8080\n")
    corrente = _Corrente(tmp_path / "run")
    render = render or _RenderFinto()
    return ViewSiteTool(ws, corrente, render=render), render, corrente


# ── C1: lo strumento ──────────────────────────────────────────────────────

def test_v1_nome_e_schema_dichiarano_widths_facoltativo(tmp_path):
    tool, _, _ = _strumento(tmp_path)
    assert tool.name == "view_site"
    props = tool.parameters["properties"]
    assert "widths" in props
    assert "widths" not in tool.parameters.get("required", [])


def test_v2_senza_argomenti_guarda_tutte_le_larghezze(tmp_path):
    tool, render, _ = _strumento(tmp_path)

    esito = tool.execute({})

    assert isinstance(esito, ToolResult)
    assert esito.data["started"] is True
    assert sorted(int(w) for w in esito.data["widths"]) == sorted(WIDTHS)
    assert [p.read_bytes() for p in esito.images] == [PNG + str(w).encode() for w in sorted(WIDTHS)]
    voce = esito.data["widths"]["375"]
    assert voce["errors"] == ["errore a 375"]
    assert voce["overflow"] is True
    assert voce["a11y"] == [{"id": "color-contrast", "impact": "serious", "nodes": 2}]
    assert len(render.chiamate) == 1


def test_v3_lo_script_di_valutazione_non_entra_mai(tmp_path):
    """L'agente guarda il proprio sito senza vedere gli script di valutazione."""
    tool, render, _ = _strumento(tmp_path)

    tool.execute({})

    assert render.chiamate[0].get("script") is None


def test_v4_widths_restringe_testo_e_immagini(tmp_path):
    tool, _, _ = _strumento(tmp_path)

    esito = tool.execute({"widths": [1440]})

    assert list(esito.data["widths"]) == ["1440"]
    assert len(esito.images) == 1 and esito.images[0].read_bytes() == PNG + b"1440"


def test_v5_una_larghezza_non_ammessa_e_un_errore_e_non_avvia_nulla(tmp_path):
    tool, render, _ = _strumento(tmp_path)

    with pytest.raises(ViewSiteError, match="1024"):
        tool.execute({"widths": [1024]})
    assert render.chiamate == []


@pytest.mark.parametrize("widths", [[], 375, "375", [True]])
def test_v5b_widths_vuoto_o_malformato_e_un_errore_e_non_avvia_nulla(tmp_path, widths):
    """Una lista vuota avvierebbe un container per non restituire nulla."""
    tool, render, _ = _strumento(tmp_path)

    with pytest.raises(ViewSiteError):
        tool.execute({"widths": widths})
    assert render.chiamate == []


def test_v6_un_sito_che_non_parte_da_testo_senza_immagini(tmp_path):
    tool, _, _ = _strumento(tmp_path, render=_RenderFinto(started=False, start_error="porta chiusa"))

    esito = tool.execute({})

    assert esito.data["started"] is False
    assert esito.data["start_error"] == "porta chiusa"
    assert esito.images == ()


def test_v7_gli_screenshot_stanno_nella_run_non_nel_workspace(tmp_path):
    """Ogni vista ha la sua cartella numerata in `run_dir/viste`; il sito consegnato resta pulito."""
    tool, render, _ = _strumento(tmp_path)

    prima = tool.execute({})
    seconda = tool.execute({})

    viste = tmp_path / "run" / "viste"
    assert render.chiamate[0]["out_dir"].parent == viste
    assert render.chiamate[0]["out_dir"] != render.chiamate[1]["out_dir"]
    for p in prima.images + seconda.images:
        assert viste in p.parents
    assert not list((tmp_path / "ws").rglob("*.png"))


def test_v9_senza_run_attiva_e_un_errore_chiaro(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    render = _RenderFinto()

    with pytest.raises(NoActiveRun):
        ViewSiteTool(ws, None, render=render).execute({})
    assert render.chiamate == []


def test_v8_lavora_sul_workspace_dell_agente(tmp_path):
    tool, render, _ = _strumento(tmp_path)
    tool.execute({})
    assert render.chiamate[0]["workspace"] == tmp_path / "ws"


# ── Agente: il messaggio di esito porta le immagini ───────────────────────

class _ToolImmagini:
    """Tool che restituisce un `ToolResult` con immagini scritte su disco."""
    schema: dict = {}

    def __init__(self, cartella: Path, nome="view_site"):
        self.name, self.cartella, self.n = nome, cartella, 0

    def execute(self, args):
        self.n += 1
        shot = self.cartella / f"vista-{self.n}.png"
        shot.write_bytes(PNG + str(self.n).encode())
        return ToolResult(data={"vista": self.n}, images=(shot,))


class _ToolTesto:
    schema: dict = {}
    name = "bash"

    def execute(self, args):
        return {"stdout": "ok"}


class _GatewaySequenza:
    """Restituisce i turni in ordine e conserva una copia profonda di ogni conversazione ricevuta."""

    def __init__(self, turni):
        self.turni, self.viste = list(turni), []

    def complete(self, messages, tools):
        self.viste.append(json.loads(json.dumps(
            [m for m in messages if isinstance(m, dict)])))
        return self.turni.pop(0)


def _chiede(*nomi):
    return AssistantTurn(tool_calls=tuple(ToolCall(id=f"c{i}-{n}", name=n, arguments="{}")
                                          for i, n in enumerate(nomi)))


def _messaggi_tool(messaggi):
    return [m for m in messaggi if isinstance(m, dict) and m.get("role") == "tool"]


def _immagini(messaggio):
    contenuto = messaggio["content"]
    if isinstance(contenuto, str):
        return []
    return [p for p in contenuto if p.get("type") == "image_url"]


def test_a1_un_tool_result_diventa_testo_piu_immagini_nel_messaggio_tool(tmp_path):
    gateway = _GatewaySequenza([_chiede("view_site"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolImmagini(tmp_path)])

    agent.run("guarda", max_iterations=3)

    [tool_msg] = _messaggi_tool(gateway.viste[1])
    testo = [p for p in tool_msg["content"] if p.get("type") == "text"]
    assert json.loads(testo[0]["text"]) == {"vista": 1}
    [img] = _immagini(tool_msg)
    url = img["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG + b"1"


def test_a2_i_tool_che_restituiscono_un_dict_restano_testo_semplice(tmp_path):
    gateway = _GatewaySequenza([_chiede("bash"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolTesto()])

    agent.run("lavora", max_iterations=3)

    [tool_msg] = _messaggi_tool(gateway.viste[1])
    assert tool_msg["content"] == json.dumps({"stdout": "ok"})


class _ToolImmagineMancante:
    schema: dict = {}
    name = "view_site"

    def __init__(self, cartella: Path):
        self.cartella = cartella

    def execute(self, args):
        return ToolResult(data={"started": True}, images=(self.cartella / "sparito.png",))


def test_a3_uno_screenshot_illeggibile_diventa_un_errore_non_un_guasto(tmp_path):
    """Due tool nello stesso turno: anche se il primo screenshot manca, entrambi hanno risposta."""
    gateway = _GatewaySequenza([_chiede("view_site", "bash"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolImmagineMancante(tmp_path), _ToolTesto()])

    esito = agent.run("guarda", max_iterations=3)

    assert esito.status == "completed"
    vista, testo = _messaggi_tool(gateway.viste[1])
    assert "error" in json.loads(vista["content"])
    assert json.loads(vista["content"])["started"] is True
    assert json.loads(testo["content"]) == {"stdout": "ok"}


class _RenderGuasto:
    def __call__(self, workspace, out_dir, **kwargs):
        raise RenderError("tempo scaduto dopo 240 s")


def test_a4_un_guasto_del_renderer_arriva_al_modello_come_errore(tmp_path):
    tool, _, _ = _strumento(tmp_path, render=_RenderGuasto())
    gateway = _GatewaySequenza([_chiede("view_site"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [tool])

    agent.run("guarda", max_iterations=3)

    [vista] = _messaggi_tool(gateway.viste[1])
    assert "tempo scaduto" in json.loads(vista["content"])["error"]


# ── C2: restano solo le immagini dell'ultima vista ────────────────────────

def test_c2_dopo_due_viste_restano_solo_le_immagini_della_seconda(tmp_path):
    gateway = _GatewaySequenza([_chiede("view_site"), _chiede("view_site"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolImmagini(tmp_path)])

    agent.run("guarda due volte", max_iterations=5)

    prima, seconda = _messaggi_tool(gateway.viste[2])
    assert _immagini(prima) == []
    assert NOTA_IMMAGINI_RIMOSSE in json.dumps(prima["content"])
    testo = prima["content"] if isinstance(prima["content"], str) else " ".join(
        p["text"] for p in prima["content"] if p.get("type") == "text")
    assert '"vista": 1' in testo                              # il testo dell'esito resta
    assert len(_immagini(seconda)) == 1
    url = _immagini(seconda)[0]["image_url"]["url"]
    assert base64.b64decode(url.split(",", 1)[1]) == PNG + b"2"


def test_c2b_due_viste_nello_stesso_turno_restano_entrambe(tmp_path):
    """La politica toglie le viste dei turni precedenti, non quelle chieste insieme."""
    gateway = _GatewaySequenza([_chiede("view_site", "view_site"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolImmagini(tmp_path)])

    agent.run("guarda", max_iterations=3)

    assert [len(_immagini(m)) for m in _messaggi_tool(gateway.viste[1])] == [1, 1]


def test_c2c_un_tool_di_solo_testo_non_toglie_le_immagini(tmp_path):
    gateway = _GatewaySequenza([_chiede("view_site"), _chiede("bash"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolImmagini(tmp_path), _ToolTesto()])

    agent.run("guarda e lavora", max_iterations=5)

    vista, _ = _messaggi_tool(gateway.viste[2])
    assert len(_immagini(vista)) == 1


def test_c2d_una_vista_senza_immagini_non_toglie_quelle_della_precedente(tmp_path):
    """Un sito che non parte non ha screenshot: resta visibile l'ultimo aspetto noto."""
    class _ToolAlterno(_ToolImmagini):
        def execute(self, args):
            esito = super().execute(args)
            return esito if self.n == 1 else ToolResult(data={"started": False})

    gateway = _GatewaySequenza([_chiede("view_site"), _chiede("view_site"), AssistantTurn(content="fatto")])
    agent = Agent(gateway, [_ToolAlterno(tmp_path)])

    agent.run("guarda due volte", max_iterations=5)

    prima, seconda = _messaggi_tool(gateway.viste[2])
    assert len(_immagini(prima)) == 1
    assert json.loads(seconda["content"]) == {"started": False}


# ── C3: il gateway OpenRouter manda le immagini dentro il messaggio tool ──

def test_c3_il_formato_openai_lascia_intatto_il_messaggio_tool_con_immagini():
    """Verde anche prima del codice: documenta che il gateway non va toccato (P6-D1)."""
    msg = {"role": "tool", "tool_call_id": "c1", "content": [
        {"type": "text", "text": "{}"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}
    assert OpenAIChatGateway._to_wire([msg]) == [msg]


# ── Aggancio negli strumenti comuni ───────────────────────────────────────

def test_f1_view_site_e_fra_gli_strumenti_comuni(tmp_path):
    corrente = _Corrente(tmp_path / "run")
    tools = build_default_tools(str(tmp_path / "ws"), event_sink=corrente)
    assert [t.name for t in tools] == ["bash", "read_file", "write_file", "view_site"]


# ── C4: Docker vero ───────────────────────────────────────────────────────

_INTEGRAZIONE = pytest.mark.skipif(
    not os.environ.get("ORC_INTEGRATION") or shutil.which("docker") is None,
    reason="serve Docker con l'immagine orc-renderer:r1: ORC_INTEGRATION=1")


@_INTEGRAZIONE
def test_i1_con_docker_vero_arriva_uno_screenshot_png(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "index.html").write_text("<!doctype html><title>t</title><h1>Ciao</h1>")
    (ws / "start.sh").write_text("python3 -m http.server 8080\n")
    tool = ViewSiteTool(ws, _Corrente(tmp_path / "run"))

    esito = tool.execute({"widths": [375]})

    assert esito.data["started"] is True
    [img] = esito.images
    assert img.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
