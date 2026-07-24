"""Provider-neutral structured generation interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from papercraft.runtime.budget import UsageRecord


T = TypeVar("T", bound=BaseModel)


class MissingCredentialError(RuntimeError):
    pass


class ModelUnavailableError(RuntimeError):
    pass


class ProviderRefusalError(RuntimeError):
    pass


class InvalidProviderResponse(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageInput:
    media_type: str
    base64_data: str
    label: str


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    value: T
    provider: str
    model: str
    request_id: str | None
    usage: UsageRecord


class StructuredProvider(Protocol):
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
    ) -> ProviderResult[T]: ...


def estimate_text_tokens(*parts: str) -> int:
    """Conservative tokenizer-independent estimate suitable for preflight cost caps."""

    characters = sum(len(part) for part in parts)
    return max(1, (characters + 2) // 3)


def estimate_image_tokens(images: list[ImageInput] | None) -> int:
    # Actual vision accounting is provider-specific. Reserving 2k tokens per crop
    # is deliberately conservative for the small page/figure crops we send.
    return 2_000 * len(images or [])
