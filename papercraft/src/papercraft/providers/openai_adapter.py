"""OpenAI Responses API adapter using native Pydantic Structured Outputs."""

from __future__ import annotations

import os
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from papercraft.providers.base import (
    ImageInput,
    InvalidProviderResponse,
    MissingCredentialError,
    ModelUnavailableError,
    ProviderRefusalError,
    ProviderResult,
    estimate_image_tokens,
    estimate_text_tokens,
)
from papercraft.runtime.budget import BudgetLedger


T = TypeVar("T", bound=BaseModel)


class OpenAIStructuredProvider:
    provider = "openai"

    def __init__(
        self,
        budget: BudgetLedger,
        *,
        model: str = "gpt-5.6-sol",
        api_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.budget = budget
        self.model = model
        if client is not None:
            self.client = client
            return
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise MissingCredentialError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        self.client = OpenAI(api_key=key)

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
        content: list[dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        for item in images or []:
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{item.media_type};base64,{item.base64_data}",
                    "detail": "original",
                }
            )
        try:
            request: dict[str, Any] = dict(
                model=self.model,
                instructions=system_prompt,
                input=[{"role": "user", "content": content}],
                text_format=output_model,
                store=False,
                max_output_tokens=max_output_tokens,
            )
            if reasoning_effort is not None:
                request["reasoning"] = {"effort": reasoning_effort}
            response = self.client.responses.parse(**request)
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                for output in getattr(response, "output", []):
                    for part in getattr(output, "content", []):
                        refusal = getattr(part, "refusal", None)
                        if refusal:
                            raise ProviderRefusalError(refusal)
                        parsed = getattr(part, "parsed", None) or parsed
            if parsed is None:
                raise InvalidProviderResponse("OpenAI response contained no parsed output")
            value = parsed if isinstance(parsed, output_model) else output_model.model_validate(parsed)
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", estimated_input))
            output_tokens = int(getattr(usage, "output_tokens", 0))
            record = self.budget.commit(
                call_id, input_tokens=input_tokens, output_tokens=output_tokens
            )
            return ProviderResult(
                value=value,
                provider=self.provider,
                model=self.model,
                request_id=getattr(response, "id", None),
                usage=record,
            )
        except (ProviderRefusalError, InvalidProviderResponse):
            self.budget.cancel(call_id)
            raise
        except Exception as exc:
            self.budget.cancel(call_id)
            status = getattr(exc, "status_code", None)
            if status in {400, 403, 404}:
                raise ModelUnavailableError(str(exc)) from exc
            raise
