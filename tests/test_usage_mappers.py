"""Contratti dei mapper: payload OpenAI -> UsageRecord indipendente dall'SDK."""

from types import SimpleNamespace as NS

from accounting.mappers import (
    OpenAIChatCompletionsUsageMapper,
    OpenAIImageUsageMapper,
    OpenAIResponsesUsageMapper,
    OpenAIVideoUsageMapper,
)


def test_chat_scompone_cache_e_reasoning():
    response = NS(
        id="chat_1",
        usage=NS(
            prompt_tokens=350,
            completion_tokens=120,
            prompt_tokens_details=NS(cached_tokens=200),
            completion_tokens_details=NS(reasoning_tokens=80),
        ),
        choices=[NS(
            finish_reason="tool_calls",
            message=NS(tool_calls=[object(), object()]),
        )],
    )

    record = OpenAIChatCompletionsUsageMapper.to_record(
        response, model="m", latency_s=0.2,
    )

    assert record.quantities == {
        "input_tokens": 150,
        "cached_input_tokens": 200,
        "output_tokens": 120,
    }
    assert record.reasoning_tokens == 80
    assert record.n_tool_calls == 2
    assert record.operation == "chat_completion"
    assert record.api_provider == "openai"
    assert record.billing_provider == "openai"


def test_responses_conserva_cache_write_come_unita_fatturabile():
    response = {
        "id": "resp_1",
        "status": "completed",
        "usage": {
            "input_tokens": 300,
            "input_tokens_details": {"cached_tokens": 100, "cache_write_tokens": 50},
            "output_tokens": 40,
            "output_tokens_details": {"reasoning_tokens": 12},
        },
    }

    record = OpenAIResponsesUsageMapper.to_record(response, model="m", latency_s=0.1)

    assert record.quantities == {
        "input_tokens": 200,
        "cached_input_tokens": 100,
        "cache_write_tokens": 50,
        "output_tokens": 40,
    }
    assert record.reasoning_tokens == 12


def test_image_gpt_image_mappa_token_testuali_e_immagine():
    response = {
        "id": "img_1",
        "size": "1024x1536",
        "quality": "high",
        "usage": {
            "input_tokens_details": {"text_tokens": 12, "image_tokens": 30},
            "output_tokens_details": {"text_tokens": 1, "image_tokens": 900},
        },
    }

    record = OpenAIImageUsageMapper.to_record(response, model="gpt-image", latency_s=2.0)

    assert record.quantities == {
        "input_text_tokens": 12,
        "input_image_tokens": 30,
        "output_text_tokens": 1,
        "output_image_tokens": 900,
    }
    assert record.dimensions == {"size": "1024x1536", "quality": "high"}
    assert record.measurement_source == "reported"


def test_image_senza_usage_registra_numero_asset_come_misura_derivata():
    response = {"data": [{}, {}, {}], "size": "1024x1024"}

    record = OpenAIImageUsageMapper.to_record(response, model="legacy", latency_s=1.0)

    assert record.quantities == {"image": 3}
    assert record.measurement_source == "derived"


def test_video_contabilizza_solo_al_completamento():
    queued = OpenAIVideoUsageMapper.to_record(
        {"id": "vid_1", "status": "queued", "seconds": "8"},
        model="sora", latency_s=0.1,
    )
    completed = OpenAIVideoUsageMapper.to_record(
        {"id": "vid_1", "status": "completed", "seconds": "8", "size": "1280x720"},
        model="sora", latency_s=0.1,
    )

    assert queued.quantities == {}
    assert queued.measurement_source == "missing"
    assert completed.quantities == {"video_second": 8}
    assert completed.dimensions == {"size": "1280x720"}
