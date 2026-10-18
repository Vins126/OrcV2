"""Rilevamento degli stalli: tre livelli, ciascuno con la sua prova.

Nota di design (tesi):
    1. **Rete**: timeout di lettura del client (`STREAM_READ_TIMEOUT_S`). Scopre una
       connessione morta. Non basta: OpenRouter manda commenti `: OPENROUTER
       PROCESSING` nelle pause (sonda del 14 ott 2026: compaiono ~0,4 s dopo l'ultimo
       chunk), e ogni commento azzera il timeout.
    2. **Misura**: l'intervallo massimo fra chunk di ogni chiamata finisce nel
       record di consumo (`max_chunk_gap_s`), per tarare la soglia con i dati.
    3. **Contenuto**: un controllo su un thread (`StallWatchdog`) che scatta se per
       `stall_timeout_s` non arriva un chunk interpretato, e interrompe la
       connessione.

    Una prova locale (14 ott 2026) ha mostrato che chiudere lo stream da un altro
    thread (`close()`) **non** sblocca la lettura: il thread resta fermo fino al
    timeout di rete. Sblocca invece `shutdown` del socket sottostante, anche su TLS
    (verificato con un certificato autofirmato): per questo `test_il_guardiano_sblocca…`
    usa un server vero.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import openai
import pytest
from openai.types.chat import ChatCompletionChunk

import config
from accounting import MalformedRegistry
from llm_gateway import OpenAIChatGateway
from stall_watchdog import StallWatchdog
from tests.test_llm_gateway import ContabileFinto, EventSink
from tests.test_registry import CONFIG, _registro

FIXTURES = Path(__file__).parent / "fixtures" / "streaming"

# Il fixture `senza_attese` sostituisce `time.sleep` per tutto il modulo `time`: le pause
# che fanno parte della prova (flusso lento, server muto) usano la sleep vera, catturata qui.
dormi = time.sleep


def _chunks(nome):
    risultato = []
    for riga in (FIXTURES / f"{nome}.jsonl").read_text().splitlines():
        linea = json.loads(riga)["line"]
        if linea.startswith("data:") and "[DONE]" not in linea:
            risultato.append(ChatCompletionChunk.model_validate(json.loads(linea[5:])))
    return risultato


# -- Configurazione -----------------------------------------------------------

def test_le_tre_soglie_sono_in_ordine():
    """Rete < contenuto < richiesta intera: ognuna scatta prima della successiva."""
    assert 0 < config.STREAM_READ_TIMEOUT_S < config.STALL_TIMEOUT_S < config.REQUEST_TIMEOUT_S


def _registro_con_soglia(valore):
    modelli = {**CONFIG["models"], "grosso": {**CONFIG["models"]["grosso"], "stall_timeout_s": valore}}
    return _registro(models=modelli)


def test_un_modello_puo_dichiarare_la_sua_soglia_di_stallo():
    registro = _registro_con_soglia(45)

    assert registro.stall_timeout_for("grosso") == 45
    assert registro.stall_timeout_for("piccolo") is None


@pytest.mark.parametrize("valore", [0, -5, "30", True, float("inf"), float("nan")])
def test_una_soglia_di_stallo_non_valida_si_scopre_al_caricamento(valore):
    with pytest.raises(MalformedRegistry, match="stall_timeout_s"):
        _registro_con_soglia(valore)


# -- Il guardiano da solo -----------------------------------------------------

def test_il_guardiano_scatta_se_non_arrivano_chunk():
    scattato = threading.Event()
    guardiano = StallWatchdog(0.2, scattato.set)

    guardiano.start()
    try:
        assert scattato.wait(2.0)
        assert guardiano.fired
    finally:
        guardiano.stop()


def test_ogni_chunk_riazzera_l_attesa():
    guardiano = StallWatchdog(0.3, lambda: None)
    guardiano.start()
    try:
        for _ in range(8):
            dormi(0.1)
            guardiano.touch()
        assert not guardiano.fired        # 0,8 s in tutto, ma mai 0,3 s di fila senza chunk
    finally:
        guardiano.stop()


def test_dopo_stop_il_guardiano_non_scatta_piu():
    scattato = threading.Event()
    guardiano = StallWatchdog(0.2, scattato.set)
    guardiano.start()
    guardiano.stop()

    assert not scattato.wait(0.5)
    assert not guardiano.fired


# -- Il gateway con un flusso che si blocca -------------------------------------

class FlussoBloccato:
    """Manda i primi chunk e poi resta fermo, come una lettura di rete, finche' non lo si chiude."""

    def __init__(self, chunks):
        self.chunks, self._chiuso = chunks, threading.Event()

    def __iter__(self):
        yield from self.chunks
        self._chiuso.wait(10)

    def close(self):
        self._chiuso.set()


class FlussoLento:
    """Un flusso che procede, con una pausa piccola fra un chunk e l'altro."""

    def __init__(self, chunks, pausa):
        self.chunks, self.pausa = chunks, pausa

    def __iter__(self):
        for chunk in self.chunks:
            dormi(self.pausa)
            yield chunk

    def close(self):
        pass


class ClientInStreaming:
    def __init__(self, *flussi):
        self.flussi = list(flussi)
        self.chat = NS(completions=NS(create=self._crea))

    def _crea(self, **_kwargs):
        return self.flussi.pop(0)


@pytest.fixture(autouse=True)
def senza_attese(monkeypatch):
    monkeypatch.setattr("llm_gateway.time.sleep", lambda _s: None)


def test_un_flusso_muto_oltre_la_soglia_viene_interrotto_e_riconosciuto_come_stallo():
    events = EventSink()
    flusso = FlussoBloccato(_chunks("interrotta")[:3])
    gateway = OpenAIChatGateway(
        ClientInStreaming(flusso), "m", ContabileFinto(), stream=True, retry_max=1,
        stall_timeout_s=0.3, event_sink=events)

    inizio = time.monotonic()
    with pytest.raises(RuntimeError, match="irraggiungibile"):
        gateway.complete([], [])

    assert time.monotonic() - inizio < 3
    interruzione = next(d for t, d in events.events if t == "stream_interrupted")
    assert "stallo" in interruzione["reason"]
    assert interruzione["chunks"] == 3


def test_dopo_uno_stallo_il_tentativo_successivo_puo_riuscire():
    contabile = ContabileFinto()
    client = ClientInStreaming(FlussoBloccato(_chunks("interrotta")[:3]),
                               FlussoLento(_chunks("testo"), 0.0))
    gateway = OpenAIChatGateway(client, "m", contabile, stream=True, retry_max=2, stall_timeout_s=0.3)

    turno = gateway.complete([], [])

    assert turno.content and [r.attempt for r in contabile.records] == [2]


def test_un_flusso_che_procede_non_e_toccato_dal_guardiano():
    """Piu' lungo della soglia in tutto, ma mai fermo per tanto."""
    chunks = _chunks("una_tool_call")
    gateway = OpenAIChatGateway(
        ClientInStreaming(FlussoLento(chunks, 0.05)), "m", ContabileFinto(), stream=True,
        retry_max=1, stall_timeout_s=0.3)

    inizio = time.monotonic()
    turno = gateway.complete([], [])

    assert time.monotonic() - inizio > 0.3          # il flusso e' durato piu' della soglia
    assert [c.name for c in turno.tool_calls] == ["write_file"]


def test_senza_soglia_non_c_e_nessun_controllo():
    gateway = OpenAIChatGateway(
        ClientInStreaming(FlussoLento(_chunks("testo"), 0.0)), "m", ContabileFinto(),
        stream=True, retry_max=1)

    assert gateway.stall_timeout_s is None
    assert gateway.complete([], []).content


# -- Misura (livello 2) ---------------------------------------------------------

def test_il_record_porta_le_misure_del_flusso():
    contabile = ContabileFinto()
    chunks = _chunks("una_tool_call")
    gateway = OpenAIChatGateway(
        ClientInStreaming(FlussoLento(chunks, 0.0)), "m", contabile, stream=True, retry_max=1)

    gateway.complete([], [])

    dimensioni = contabile.records[0].dimensions
    assert dimensioni["chunks"] == len(chunks)
    assert dimensioni["max_chunk_gap_s"] >= 0
    assert dimensioni["reasoning_chars"] > 0


# -- Una lettura di rete vera ---------------------------------------------------

class _Muto(BaseHTTPRequestHandler):
    """Manda un chunk e poi tace, come un modello che si blocca (connessione aperta)."""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        evento = {"id": "gen-muto", "choices": [{"index": 0, "delta": {"content": "ciao"},
                                                 "finish_reason": None}]}
        try:
            self.wfile.write(f"data: {json.dumps(evento)}\n\n".encode())
            self.wfile.flush()
            for _ in range(60):
                dormi(0.1)
        except OSError:
            pass

    def log_message(self, format, *args):  # noqa: A002 - firma della classe base
        pass


@pytest.fixture
def server_muto():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Muto)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def test_il_guardiano_sblocca_una_lettura_di_rete_vera(server_muto):
    """`close()` da un altro thread non basta: serve `shutdown` del socket.

    Il timeout di rete del client e' 30 s: se il guardiano non sbloccasse la
    lettura, il test durerebbe 30 s invece di meno di 3.
    """
    events = EventSink()
    client = openai.OpenAI(api_key="x", base_url=f"http://127.0.0.1:{server_muto.server_port}/v1",
                           max_retries=0, timeout=30)
    gateway = OpenAIChatGateway(client, "m", ContabileFinto(), stream=True, retry_max=1,
                                stall_timeout_s=0.5, event_sink=events)

    inizio = time.monotonic()
    with pytest.raises(RuntimeError, match="irraggiungibile"):
        gateway.complete([], [])

    assert time.monotonic() - inizio < 3
    interruzione = next(d for t, d in events.events if t == "stream_interrupted")
    assert "stallo" in interruzione["reason"]
    assert interruzione["generation_id"] == "gen-muto"
