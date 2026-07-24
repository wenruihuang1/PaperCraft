"""Claude Messages adapter with strict, forced JSON-schema tool output."""

from __future__ import annotations

import copy
import os
import time
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from papercraft.providers.base import (
    ImageInput,
    InvalidProviderResponse,
    MissingCredentialError,
    ModelUnavailableError,
    ProviderResult,
    estimate_image_tokens,
    estimate_text_tokens,
)
from papercraft.runtime.budget import BudgetLedger


T = TypeVar("T", bound=BaseModel)


def _anthropic_tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a Claude-compatible schema while keeping Pydantic authoritative.

    Claude's strict tool schema currently accepts array ``minItems`` only as
    zero or one and rejects ``maxItems``. Some PaperCraft contracts use both.
    Relax only those transport-level constraints; ``model_validate`` below
    still enforces the original Pydantic contract on the returned object.
    """

    schema = copy.deepcopy(model.model_json_schema())

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
                value.pop("discriminator", None)
            if isinstance(value.get("minItems"), int) and value["minItems"] > 1:
                value["minItems"] = 1
            value.pop("maxItems", None)
            # Claude's strict schema compiler does not accept JSON Schema's
            # exclusive numeric bounds. The original Pydantic model still
            # applies these constraints after the tool call is returned.
            value.pop("exclusiveMinimum", None)
            value.pop("exclusiveMaximum", None)
            value.pop("minimum", None)
            value.pop("maximum", None)
            for child in value.values():
                normalize(child)
        elif isinstance(value, list):
            for child in value:
                normalize(child)

    normalize(schema)
    return schema


class AnthropicStructuredProvider:
    provider = "anthropic"

    def __init__(
        self,
        budget: BudgetLedger,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.budget = budget
        self.model = model or os.getenv("PAPERCRAFT_CLAUDE_MODEL", "claude-sonnet-4-6")
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise MissingCredentialError("ANTHROPIC_API_KEY is not configured")
        import anthropic

        # Do not inherit ANTHROPIC_BASE_URL from the host process. Claude Code
        # and other developer tools may inject their own compatible gateway,
        # which would send PaperCraft's explicit API key to the wrong service.
        # A PaperCraft-specific override remains available for intentional
        # custom deployments.
        resolved_base_url = (
            base_url
            or os.getenv("PAPERCRAFT_ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com"
        )
        self.client = anthropic.Anthropic(
            api_key=key,
            base_url=resolved_base_url,
            timeout=600,
            max_retries=5,
        )

    def generate(
        self,
        *,
        call_id: str,
        system_prompt: str,
        user_prompt: str,
        output_model: type[T],
        images: list[ImageInput] | None = None,
        max_output_tokens: int = 8_000,
        reasoning_effort: Literal["low", "medium", "high"] | None = "high",
        strict_output: bool = True,
    ) -> ProviderResult[T]:
        estimated_input = estimate_text_tokens(system_prompt, user_prompt)
        estimated_input += estimate_image_tokens(images)
        self.budget.reserve(
            call_id=call_id,
            provider=self.provider,
            model=self.model,
            estimated_input_tokens=estimated_input,
            max_output_tokens=max_output_tokens,
        )
        content: list[dict[str, Any]] = []
        for item in images or []:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": item.base64_data,
                    },
                }
            )
        content.append({"type": "text", "text": user_prompt})
        tool_name = "submit_structured_review"
        request = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
            "tools": [
                {
                    "name": tool_name,
                    "description": "Return the validated PaperCraft structured result.",
                    "input_schema": _anthropic_tool_schema(output_model),
                    "strict": strict_output,
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if reasoning_effort is not None:
            request["thinking"] = {"type": "adaptive"}
            request["output_config"] = {"effort": reasoning_effort}
        try:
            # Streaming keeps long reasoning requests active through proxies
            # that otherwise close an idle HTTP response before Claude has
            # produced the final structured tool call. The fallback keeps
            # lightweight mock clients and older SDKs usable.
            response = None
            transport_attempts = int(os.getenv("PAPERCRAFT_API_RETRIES", "3"))
            for attempt in range(transport_attempts):
                try:
                    if hasattr(self.client.messages, "stream"):
                        with self.client.messages.stream(**request) as stream:
                            response = stream.get_final_message()
                    else:
                        response = self.client.messages.create(**request)
                    break
                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    retryable = status in {429, 500, 502, 503, 504, 529} or (
                        status is None
                        and type(exc).__name__
                        in {
                            "APIConnectionError",
                            "ConnectError",
                            "ReadError",
                            "ReadTimeout",
                            "RemoteProtocolError",
                        }
                    )
                    if not retryable or attempt == transport_attempts - 1:
                        raise
                    time.sleep(min(8, 2**attempt))
            assert response is not None
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", estimated_input))
            output_tokens = int(getattr(usage, "output_tokens", 0))
            # Once Claude has returned a response, the call is billable even if
            # its tool payload later fails local validation. Commit usage before
            # parsing so the persistent ledger never understates paid calls.
            record = self.budget.commit(
                call_id, input_tokens=input_tokens, output_tokens=output_tokens
            )
            tool_input = None
            for block in getattr(response, "content", []):
                if getattr(block, "type", None) == "tool_use" and getattr(
                    block, "name", None
                ) == tool_name:
                    tool_input = getattr(block, "input", None)
                    break
            if tool_input is None:
                raise InvalidProviderResponse("Claude returned no structured review tool call")
            value = output_model.model_validate(tool_input)
            return ProviderResult(
                value=value,
                provider=self.provider,
                model=self.model,
                request_id=getattr(response, "id", None),
                usage=record,
            )
        except InvalidProviderResponse:
            self.budget.cancel(call_id)
            raise
        except Exception as exc:
            self.budget.cancel(call_id)
            status = getattr(exc, "status_code", None)
            if status == 401:
                raise MissingCredentialError(
                    "Claude rejected ANTHROPIC_API_KEY (HTTP 401). Replace the local key and retry; no fallback model was used."
                ) from exc
            if status in {400, 403, 404}:
                raise ModelUnavailableError(str(exc)) from exc
            raise
