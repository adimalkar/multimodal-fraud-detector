"""Reading the vision model's answer. A slip in format must not crash a job."""

import json

import pytest

from backend import qwen_agent
from backend.qwen_agent import ModelOutputUnusable, parse_vision_output

GOOD = {"classification": "Fake", "confidence_score": 0.8, "vision_findings": "Warped text.", "reason": "Text is warped.",
        "visible_watermark": ""}


def body(content, finish="stop", cost=0.0001):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 400, "completion_tokens": 90, "total_tokens": 490, "cost": cost}}


def test_list_of_findings_is_joined():
    result = parse_vision_output(body(json.dumps({**GOOD, "vision_findings": ["Warped text", "Extra finger"]})))
    assert result[2] == "Warped text; Extra finger"


def test_fenced_json_and_percent_confidence():
    result = parse_vision_output(body("```json\n" + json.dumps({**GOOD, "confidence_score": "85%"}) + "\n```"))
    assert result[:2] == ("Fake", 0.85)


@pytest.mark.parametrize("label,expected", [("AI-generated", "Fake"), ("authentic", "Real"), ("REAL", "Real")])
def test_label_synonyms(label, expected):
    assert parse_vision_output(body(json.dumps({**GOOD, "classification": label})))[0] == expected


def test_low_confidence_is_floored_not_rejected():
    assert parse_vision_output(body(json.dumps({**GOOD, "confidence_score": 0.3})))[1] == 0.5


@pytest.mark.parametrize("content", [
    json.dumps(GOOD)[:60],                                   # cut off by the token limit
    "",                                                      # empty answer
    json.dumps({**GOOD, "classification": "Unclear"}),       # no usable label
    json.dumps({**GOOD, "reason": None}),                    # missing reason
])
def test_unusable_output_raises_its_own_error(content):
    with pytest.raises(ModelOutputUnusable):
        parse_vision_output(body(content, finish="length"))


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(qwen_agent, "missing_model_credentials", lambda: [])
    monkeypatch.setattr(qwen_agent, "VISION_MODEL_ID", "google/gemma-4-26b-a4b-it")


def test_one_retry_recovers_and_counts_both_calls(configured, monkeypatch):
    answers = iter([body("{broken"), body(json.dumps(GOOD))])
    monkeypatch.setattr(qwen_agent, "_request_vision", lambda content: next(answers))
    result = qwen_agent._analyze_images(["aGk="], "Image")
    assert result["classification"] == "Fake"
    assert result["model_usage"]["calls"] == 2
    assert result["model_usage"]["cost"] == pytest.approx(0.0002)


def test_second_failure_raises_unusable(configured, monkeypatch):
    monkeypatch.setattr(qwen_agent, "_request_vision", lambda content: body("{broken"))
    with pytest.raises(ModelOutputUnusable):
        qwen_agent._analyze_images(["aGk="], "Image")


def test_provider_error_is_not_mistaken_for_unusable_output(configured, monkeypatch):
    class Failed:
        status_code = 502

    monkeypatch.setattr(qwen_agent.requests, "post", lambda *args, **kwargs: Failed())
    with pytest.raises(RuntimeError) as caught:
        qwen_agent._analyze_images(["aGk="], "Image")
    assert not isinstance(caught.value, ModelOutputUnusable)
