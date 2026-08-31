"""Giuntura fra i mapper dei provider e il listino reale di `models.toml`.

Nota di design (tesi):
    Gli altri test isolano ogni pezzo: i mapper girano contro un registro
    finto, il registro contro record scritti a mano. E' l'approccio giusto,
    ma lascia scoperta proprio la giunzione fra i due — e li' e' vissuto a
    lungo un difetto reale: il mapper scorpora i token serviti dalla cache in
    un'unita' `cached_input_tokens`, che `opus-5` non dichiarava a listino.
    La prima risposta con prompt cache attiva faceva quindi morire la run
    **dopo** aver pagato la chiamata, registrandola a costo zero.

    Questi test partono percio' da una risposta come la restituisce il
    provider e arrivano fino al costo in dollari, usando il listino vero. E'
    l'unico livello a cui quel difetto era visibile.
"""

from types import SimpleNamespace

import pytest

from accounting import InMemoryAccountant, ModelRegistry
from accounting.mappers.openai import OpenAIChatCompletionsUsageMapper


def _registro():
    return ModelRegistry.from_file("models.toml")


def _risposta_chat(*, prompt=350, completion=120, cached=0, reasoning=0):
    """Costruisce una risposta `chat.completions` come quella di un provider."""
    return SimpleNamespace(
        id="resp_1",
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        ),
        choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="ok", tool_calls=None),
        )],
    )


def _modelli_di_chat():
    """I modelli del listino che possono servire una `chat.completions`."""
    registro = _registro()
    return sorted(set(registro.models_with("text")) | set(registro.models_with("code")))


# ── Ogni modello di chat sa prezzare cio' che il mapper produce ───────────

@pytest.mark.parametrize("model", _modelli_di_chat())
@pytest.mark.parametrize("cached", [0, 200], ids=["senza_cache", "con_cache"])
def test_ogni_modello_prezza_l_output_del_mapper(model, cached):
    """Nessun modello del listino puo' produrre un'unita' che non sa prezzare.

    Il caso `con_cache` e' quello che contava: la prompt cache e' attiva di
    default presso molti fornitori, quindi non e' un caso limite ma la
    condizione ordinaria di una conversazione che cresce.
    """
    contabile = InMemoryAccountant(_registro())
    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(cached=cached), model=model, latency_s=0.1,
    )

    costo = contabile.register(record)

    assert costo > 0
    assert record.cost == costo


def test_i_token_da_cache_costano_meno_di_quelli_pieni():
    """Lo sconto della cache si riflette davvero nel totale.

    Non e' una verifica del listino ma dello scorporo: se il mapper sommasse
    i token da cache a quelli di input invece di sottrarli, la stessa
    risposta costerebbe di piu' con la cache che senza.
    """
    contabile = InMemoryAccountant(_registro())
    pieno = contabile.register(OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(cached=0), model="opus-5", latency_s=0.1))
    scontato = contabile.register(OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(cached=200), model="opus-5", latency_s=0.1))

    assert scontato < pieno


def test_lo_scorporo_non_conta_due_volte_i_token_di_input():
    """350 token di cui 200 da cache restano 350, non 550."""
    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(prompt=350, cached=200), model="opus-5", latency_s=0.1,
    )

    assert record.quantities["input_tokens"] == 150
    assert record.quantities["cached_input_tokens"] == 200


def test_i_token_di_ragionamento_restano_fuori_dal_costo():
    """`reasoning_tokens` e' un dettaglio di `output_tokens`, non una voce a se'.

    Sommarlo farebbe pagare due volte la parte di ragionamento.
    """
    contabile = InMemoryAccountant(_registro())
    senza = contabile.register(OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(reasoning=0), model="opus-5", latency_s=0.1))
    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(reasoning=80), model="opus-5", latency_s=0.1)
    con = contabile.register(record)

    assert con == senza
    assert record.reasoning_tokens == 80
    assert "reasoning_tokens" not in record.quantities


def test_il_costo_e_quello_atteso_a_mano():
    """Ancora numerica sul percorso completo, con opus-5.

    150 input pieni a $5/milione            = $0.00075
    200 input da cache a $0.50/milione      = $0.00010
    120 output a $25/milione                = $0.00300
                                              ---------
                                              $0.00385
    """
    contabile = InMemoryAccountant(_registro())
    record = OpenAIChatCompletionsUsageMapper.to_record(
        _risposta_chat(prompt=350, completion=120, cached=200),
        model="opus-5", latency_s=0.1,
    )

    assert contabile.register(record) == pytest.approx(0.00385)
