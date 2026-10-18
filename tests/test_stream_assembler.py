"""L'assemblatore ricompone i chunk dello streaming e riconosce un flusso interrotto.

Nota di design (tesi):
    I flussi di questi test non sono inventati: sono le righe SSE catturate da una
    sonda su `minimax-m3` (OpenRouter, fornitore `minimax/fp8`, 14 ott 2026), in
    `tests/fixtures/streaming/`. Mostrano cose che la documentazione non dice: le
    tool call arrivano intere alla fine (due chunk per chiamata), il chunk finale
    ripete il `finish_reason` e porta l'`usage` dentro una `choice`, e il
    ragionamento viaggia in due campi (`reasoning` e `reasoning_details`).

    `interrotta.jsonl` e' un flusso chiuso di proposito dopo 40 chunk: e' il caso
    reale di un flusso senza `finish_reason`. `lunghezza_ridotto.jsonl` e' la
    richiesta fermata dal limite di 8000 token (tutti di ragionamento); delle 2.301
    righe originali restano le prime 15 e le ultime 4, quelle del mezzo sono solo
    ragionamento.
"""

import json
from pathlib import Path

import pytest

from accounting.mappers.openai import OpenAIChatCompletionsUsageMapper
from llm_contracts import TurnOutcome
from llm_gateway import OpenAIChatGateway
from stream_assembler import StreamAssembler, StreamInterrupted

FIXTURES = Path(__file__).parent / "fixtures" / "streaming"


def _flusso(nome):
    """I chunk (dizionari) di un flusso catturato, senza commenti e senza `[DONE]`."""
    chunks = []
    for riga in (FIXTURES / f"{nome}.jsonl").read_text().splitlines():
        linea = json.loads(riga)["line"]
        if linea.startswith("data:") and "[DONE]" not in linea:
            chunks.append(json.loads(linea[5:]))
    return chunks


def _assembla(chunks, clock=None):
    assemblatore = StreamAssembler(clock) if clock else StreamAssembler()
    for chunk in chunks:
        assemblatore.feed(chunk)
    return assemblatore


def _chunk(delta=None, finish_reason=None, **extra):
    """Un chunk sintetico, per i casi che non e' comodo catturare dal vero."""
    corpo = {"id": "gen-1", "model": "m", "provider": "P",
             "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish_reason}]}
    corpo.update(extra)
    return corpo


def _frammento_tool(index, id=None, name=None, arguments=None):
    funzione = {}
    if name is not None:
        funzione["name"] = name
    if arguments is not None:
        funzione["arguments"] = arguments
    frammento = {"index": index, "function": funzione}
    if id is not None:
        frammento["id"] = id
        frammento["type"] = "function"
    return {"tool_calls": [frammento]}


# -- Flussi veri ---------------------------------------------------------------

def test_un_flusso_di_solo_testo_diventa_una_risposta_intera():
    risposta = _assembla(_flusso("testo")).result()

    scelta = risposta.choices[0]
    assert scelta.finish_reason == "stop"
    assert scelta.message.content
    assert scelta.message.tool_calls == ()
    assert risposta.provider == "Minimax"
    assert risposta.id is not None and risposta.id.startswith("gen-")


def test_una_tool_call_vera_arriva_intera_e_con_argomenti_validi():
    risposta = _assembla(_flusso("una_tool_call")).result()

    chiamate = risposta.choices[0].message.tool_calls
    assert risposta.choices[0].finish_reason == "tool_calls"
    assert len(chiamate) == 1
    assert chiamate[0].id.startswith("call_")
    assert chiamate[0].function.name == "write_file"
    assert json.loads(chiamate[0].function.arguments)["path"] == "hello.py"


def test_due_tool_call_vere_restano_distinte_e_in_ordine():
    risposta = _assembla(_flusso("due_tool_call")).result()

    chiamate = risposta.choices[0].message.tool_calls
    assert [json.loads(c.function.arguments)["path"] for c in chiamate] == ["a.py", "b.py"]
    assert chiamate[0].id != chiamate[1].id


def test_il_finish_reason_ripetuto_dal_chunk_di_usage_non_cambia_il_risultato():
    """OpenRouter ripete il `finish_reason` nel chunk che porta l'usage."""
    chunks = _flusso("una_tool_call")
    ripetizioni = [c for c in chunks if c["choices"][0].get("finish_reason")]
    assert len(ripetizioni) == 2          # la sonda lo ha davvero visto due volte

    assert _assembla(chunks).result().choices[0].finish_reason == "tool_calls"


def test_la_risposta_ricomposta_attraversa_il_codice_esistente_senza_modifiche():
    """Stesso `_to_turn` e stesso mapper dell'usage della risposta non in streaming."""
    risposta = _assembla(_flusso("una_tool_call")).result()

    turno = OpenAIChatGateway._to_turn(risposta)
    record = OpenAIChatCompletionsUsageMapper.to_record(
        risposta, model="minimax-m3", latency_s=1.0)

    assert turno.outcome is TurnOutcome.TOOL_REQUEST
    assert [c.name for c in turno.tool_calls] == ["write_file"]
    assert record.finish_reason == "tool_calls"
    assert record.n_tool_calls == 1
    assert record.served_by == "Minimax"
    assert record.reported_cost == pytest.approx(0.00018678)
    assert record.reasoning_tokens == 38


def test_un_flusso_fermato_dal_limite_di_token_e_uno_stato_non_un_errore():
    """8000 token tutti di ragionamento, `finish_reason: length`, niente testo ne' tool call."""
    risposta = _assembla(_flusso("lunghezza_ridotto")).result()

    turno = OpenAIChatGateway._to_turn(risposta)
    assert risposta.choices[0].finish_reason == "length"
    assert turno.outcome is TurnOutcome.TRUNCATED
    assert turno.content is None and turno.tool_calls == ()
    assert risposta.usage is not None and risposta.usage["completion_tokens"] == 8000


def test_un_flusso_chiuso_prima_della_fine_e_interrotto():
    """Il caso vero: la connessione chiusa dopo 40 chunk, senza `finish_reason`."""
    assemblatore = _assembla(_flusso("interrotta"))

    with pytest.raises(StreamInterrupted) as errore:
        assemblatore.result()

    assert "finish_reason" in errore.value.reason
    assert errore.value.generation_id is not None and errore.value.generation_id.startswith("gen-")
    assert errore.value.stats.chunk_count == 40
    assert errore.value.stats.reasoning_chars > 7000


# -- Casi limite ---------------------------------------------------------------

def test_un_flusso_vuoto_e_interrotto():
    with pytest.raises(StreamInterrupted, match="vuoto"):
        StreamAssembler().result()


def test_un_evento_di_errore_dentro_il_flusso_porta_il_dettaglio_del_fornitore():
    """Il fornitore ha gia' risposto 200: l'errore arriva come evento con campo `error`."""
    assemblatore = _assembla([
        _chunk({"content": "Ciao"}),
        _chunk(finish_reason="error", error={"code": 502, "message": "upstream"}),
    ])

    with pytest.raises(StreamInterrupted) as errore:
        assemblatore.result()

    assert errore.value.provider_error == {"code": 502, "message": "upstream"}
    assert errore.value.generation_id == "gen-1"


def test_un_errore_come_primo_e_unico_evento_e_un_fallimento():
    with pytest.raises(StreamInterrupted):
        _assembla([{"error": {"code": 500, "message": "x"}}]).result()


def test_gli_argomenti_a_pezzi_si_concatenano_per_indice_anche_se_le_chiamate_si_alternano():
    risposta = _assembla([
        _chunk(_frammento_tool(0, id="a", name="f", arguments="")),
        _chunk(_frammento_tool(0, arguments='{"x": ')),
        _chunk(_frammento_tool(1, id="b", name="g", arguments="")),
        _chunk(_frammento_tool(0, arguments="1}")),
        _chunk(_frammento_tool(1, arguments='{"y": 2}')),
        _chunk(finish_reason="tool_calls"),
    ]).result()

    chiamate = risposta.choices[0].message.tool_calls
    assert [(c.id, c.function.name, c.function.arguments) for c in chiamate] == [
        ("a", "f", '{"x": 1}'), ("b", "g", '{"y": 2}')]


def test_una_tool_call_senza_argomenti_ha_un_oggetto_vuoto_come_nella_risposta_intera():
    risposta = _assembla([
        _chunk(_frammento_tool(0, id="a", name="f", arguments="")),
        _chunk(finish_reason="tool_calls"),
    ]).result()

    assert risposta.choices[0].message.tool_calls[0].function.arguments == "{}"


def test_una_tool_call_senza_id_o_nome_in_un_flusso_concluso_e_un_errore():
    assemblatore = _assembla([
        _chunk(_frammento_tool(0, arguments='{"x": 1}')),
        _chunk(finish_reason="tool_calls"),
    ])

    with pytest.raises(StreamInterrupted, match="tool call"):
        assemblatore.result()


def test_un_frammento_di_tool_call_senza_index_non_si_indovina():
    """Senza index non si sa a quale chiamata appartiene: fonderle sarebbe peggio di fermarsi."""
    frammento = {"tool_calls": [{"id": "a", "function": {"name": "f", "arguments": "{}"}}]}

    with pytest.raises(StreamInterrupted, match="index"):
        StreamAssembler().feed(_chunk(frammento))


def test_con_length_una_tool_call_incompleta_si_scarta_senza_errore():
    """Il taglio e' gia' la notizia: lo dice `length`, l'agente non eseguira' nulla."""
    risposta = _assembla([
        _chunk(_frammento_tool(0, arguments='{"x"')),
        _chunk(finish_reason="length"),
    ]).result()

    assert risposta.choices[0].finish_reason == "length"
    assert risposta.choices[0].message.tool_calls == ()


def test_senza_usage_il_flusso_concluso_e_valido_e_l_usage_resta_assente():
    risposta = _assembla([_chunk({"content": "ok"}), _chunk(finish_reason="stop")]).result()

    assert risposta.usage is None


def test_un_chunk_di_usage_senza_choices_si_legge_senza_errori():
    """E' la forma standard di OpenAI (OpenRouter invece usa una `choice` vuota)."""
    usage = {"prompt_tokens": 5, "completion_tokens": 2}
    risposta = _assembla([
        _chunk({"content": "ok"}),
        _chunk(finish_reason="stop"),
        {"id": "gen-1", "choices": [], "usage": usage},
    ]).result()

    assert risposta.usage == usage


def test_si_misura_l_intervallo_massimo_fra_due_chunk():
    istanti = iter([0.0, 1.0, 4.0, 5.0])
    assemblatore = StreamAssembler(clock=lambda: next(istanti))

    for _ in range(4):
        assemblatore.feed(_chunk({"reasoning": "x"}))

    assert assemblatore.stats.max_gap_s == 3.0
    assert assemblatore.stats.chunk_count == 4
    assert assemblatore.stats.reasoning_chars == 4
