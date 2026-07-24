from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field, ValidationError

from papercraft.providers import AnthropicStructuredProvider, OpenAIStructuredProvider
from papercraft.providers.base import MissingCredentialError
from papercraft.providers.codex_exec_adapter import (
    _codex_environment,
    _strict_json_schema,
    _usage_from_jsonl,
)
from papercraft.runtime import BudgetLedger


class TinyOutput(BaseModel):
    answer: str


class ConstrainedListOutput(BaseModel):
    answers: list[str] = Field(min_length=2, max_length=3)


class ConstrainedNumberOutput(BaseModel):
    score: float = Field(gt=0, lt=1)


def test_openai_adapter_uses_parsed_output_without_storing_response():
    response = SimpleNamespace(
        id="resp_test",
        output_parsed=TinyOutput(answer="grounded"),
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        output=[],
    )
    calls = []
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **kwargs: calls.append(kwargs) or response)
    )
    provider = OpenAIStructuredProvider(
        BudgetLedger(limit_usd=Decimal("1")), client=client
    )
    result = provider.generate(
        call_id="openai-test",
        system_prompt="system",
        user_prompt="user",
        output_model=TinyOutput,
        max_output_tokens=20,
    )
    assert result.value.answer == "grounded"
    assert calls[0]["model"] == "gpt-5.6-sol"
    assert calls[0]["store"] is False
    assert calls[0]["text_format"] is TinyOutput


def test_anthropic_adapter_forces_strict_typed_tool():
    block = SimpleNamespace(
        type="tool_use", name="submit_structured_review", input={"answer": "checked"}
    )
    response = SimpleNamespace(
        id="msg_test",
        content=[block],
        usage=SimpleNamespace(input_tokens=12, output_tokens=6),
    )
    calls = []
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    provider = AnthropicStructuredProvider(
        BudgetLedger(limit_usd=Decimal("1")), client=client
    )
    result = provider.generate(
        call_id="claude-test",
        system_prompt="system",
        user_prompt="user",
        output_model=TinyOutput,
        max_output_tokens=20,
    )
    assert result.value.answer == "checked"
    assert calls[0]["model"] == "claude-sonnet-4-6"
    assert calls[0]["thinking"] == {"type": "adaptive"}
    assert calls[0]["output_config"] == {"effort": "high"}
    assert calls[0]["tools"][0]["strict"] is True


def test_anthropic_adapter_normalizes_unsupported_array_minimum():
    block = SimpleNamespace(
        type="tool_use",
        name="submit_structured_review",
        input={"answers": ["one", "two"]},
    )
    response = SimpleNamespace(
        id="msg_test",
        content=[block],
        usage=SimpleNamespace(input_tokens=12, output_tokens=6),
    )
    calls = []
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    provider = AnthropicStructuredProvider(
        BudgetLedger(limit_usd=Decimal("1")), client=client
    )
    provider.generate(
        call_id="claude-list-test",
        system_prompt="system",
        user_prompt="user",
        output_model=ConstrainedListOutput,
        max_output_tokens=20,
    )
    schema = calls[0]["tools"][0]["input_schema"]
    assert schema["properties"]["answers"]["minItems"] == 1
    assert "maxItems" not in schema["properties"]["answers"]


def test_anthropic_adapter_removes_unsupported_exclusive_numeric_bounds():
    block = SimpleNamespace(
        type="tool_use",
        name="submit_structured_review",
        input={"score": 0.5},
    )
    response = SimpleNamespace(
        id="msg_test",
        content=[block],
        usage=SimpleNamespace(input_tokens=12, output_tokens=6),
    )
    calls = []
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs) or response)
    )
    provider = AnthropicStructuredProvider(
        BudgetLedger(limit_usd=Decimal("1")), client=client
    )
    provider.generate(
        call_id="claude-number-test",
        system_prompt="system",
        user_prompt="user",
        output_model=ConstrainedNumberOutput,
        max_output_tokens=20,
    )
    number_schema = calls[0]["tools"][0]["input_schema"]["properties"]["score"]
    assert "exclusiveMinimum" not in number_schema
    assert "exclusiveMaximum" not in number_schema
    assert "minimum" not in number_schema
    assert "maximum" not in number_schema


def test_anthropic_adapter_records_billable_usage_before_local_validation():
    block = SimpleNamespace(
        type="tool_use", name="submit_structured_review", input={"wrong": "shape"}
    )
    response = SimpleNamespace(
        id="msg_invalid",
        content=[block],
        usage=SimpleNamespace(input_tokens=21, output_tokens=8),
    )
    ledger = BudgetLedger(limit_usd=Decimal("1"))
    provider = AnthropicStructuredProvider(
        ledger,
        client=SimpleNamespace(
            messages=SimpleNamespace(create=lambda **kwargs: response)
        ),
    )
    with pytest.raises(ValidationError):
        provider.generate(
            call_id="claude-invalid-local-shape",
            system_prompt="system",
            user_prompt="user",
            output_model=TinyOutput,
            max_output_tokens=20,
        )
    assert ledger.records[0].call_id == "claude-invalid-local-shape"
    assert ledger.records[0].input_tokens == 21
    assert ledger.records[0].output_tokens == 8


def test_anthropic_401_is_a_recoverable_credential_pause():
    class Unauthorized(RuntimeError):
        status_code = 401

    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(Unauthorized()))
    )
    provider = AnthropicStructuredProvider(
        BudgetLedger(limit_usd=Decimal("1")), client=client
    )
    with pytest.raises(MissingCredentialError, match="no fallback model"):
        provider.generate(
            call_id="claude-401",
            system_prompt="system",
            user_prompt="user",
            output_model=TinyOutput,
            max_output_tokens=20,
        )
    assert provider.budget.spent_usd == 0


def test_codex_schema_is_strict_and_usage_is_read_from_jsonl():
    schema = _strict_json_schema(TinyOutput.model_json_schema())
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["answer"]
    stdout = (
        '{"type":"turn.started"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":123,"output_tokens":45}}\n'
    )
    assert _usage_from_jsonl(stdout) == (123, 45)


def test_codex_schema_rewrites_one_of_as_any_of():
    schema = _strict_json_schema(
        {
            "type": "object",
            "properties": {
                "item": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ]
                }
            },
        }
    )
    item = schema["properties"]["item"]
    assert "oneOf" not in item
    assert item["anyOf"] == [{"type": "string"}, {"type": "integer"}]


def test_codex_child_environment_does_not_inherit_model_api_keys(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "ZHIPU_API_KEY",
    ):
        monkeypatch.setenv(name, "secret")
    environment = _codex_environment()
    assert not any(name in environment for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "ZHIPU_API_KEY",
    ))
