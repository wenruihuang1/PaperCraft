"""Codex CLI adapter using account authentication and JSON Schema outputs.

This provider deliberately runs Codex in a temporary, read-only workspace. The
full task context is passed through stdin and image inputs are attached as
temporary files, so the child run does not need to inspect or modify the
PaperCraft repository. API-key environment variables are removed before the
process starts; Codex reuses its own saved account authentication.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeVar

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
from papercraft.runtime.budget import BudgetLedger, ModelPricing


T = TypeVar("T", bound=BaseModel)


class CodexExecStructuredProvider:
    """Implement ``StructuredProvider`` with the local ``codex exec`` command."""

    provider = "codex"

    def __init__(
        self,
        budget: BudgetLedger,
        *,
        executable: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.budget = budget
        self.executable = executable or os.getenv("PAPERCRAFT_CODEX_EXECUTABLE", "codex")
        if shutil.which(self.executable) is None:
            raise MissingCredentialError(
                f"Codex CLI executable was not found: {self.executable}"
            )
        self.requested_model = model or os.getenv("PAPERCRAFT_CODEX_MODEL")
        self.model = self.requested_model or "account-default"
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("PAPERCRAFT_CODEX_TIMEOUT_SECONDS", "1800")
        )
        if not any(
            item.provider == self.provider and item.model == self.model
            for item in self.budget.pricing
        ):
            # ChatGPT-managed Codex runs are rate-limited account usage, not
            # metered PaperCraft API spend. Keep token telemetry while recording
            # zero API cost in the existing per-job ledger.
            self.budget.pricing += (
                ModelPricing(
                    provider=self.provider,
                    model=self.model,
                    input_usd_per_million=Decimal("0"),
                    output_usd_per_million=Decimal("0"),
                ),
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
        del strict_output  # JSON Schema validation is always enforced by Codex.
        estimated_input = estimate_text_tokens(system_prompt, user_prompt)
        estimated_input += estimate_image_tokens(images)
        self.budget.reserve(
            call_id=call_id,
            provider=self.provider,
            model=self.model,
            estimated_input_tokens=estimated_input,
            max_output_tokens=max_output_tokens,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="papercraft-codex-") as temporary:
                temp_root = Path(temporary)
                schema_path = temp_root / "output.schema.json"
                result_path = temp_root / "result.json"
                schema_path.write_text(
                    json.dumps(
                        _strict_json_schema(output_model.model_json_schema()), indent=2
                    )
                    + "\n",
                    encoding="utf-8",
                )
                image_paths = self._write_images(temp_root, images or [])
                prompt = _build_prompt(
                    call_id=call_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    image_paths=image_paths,
                )
                command = [
                    self.executable,
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--json",
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(result_path),
                    "--cd",
                    str(temp_root),
                ]
                if self.requested_model:
                    command.extend(["--model", self.requested_model])
                if reasoning_effort is not None:
                    command.extend(
                        ["--config", f'model_reasoning_effort="{reasoning_effort}"']
                    )
                for image_path in image_paths:
                    command.extend(["--image", str(image_path)])
                command.append("-")
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    env=_codex_environment(),
                    check=False,
                )
                if completed.returncode != 0:
                    details = _last_error(completed.stdout, completed.stderr)
                    raise ModelUnavailableError(
                        f"Codex stage {call_id} failed with exit code "
                        f"{completed.returncode}: {details}"
                    )
                if not result_path.is_file():
                    raise InvalidProviderResponse(
                        f"Codex stage {call_id} produced no final structured output"
                    )
                raw_result = result_path.read_text(encoding="utf-8")
                try:
                    value = output_model.model_validate_json(raw_result)
                except Exception as exc:
                    raise InvalidProviderResponse(
                        f"Codex stage {call_id} returned invalid structured output: {exc}"
                    ) from exc
                input_tokens, output_tokens = _usage_from_jsonl(completed.stdout)
                record = self.budget.commit(
                    call_id,
                    input_tokens=input_tokens or estimated_input,
                    output_tokens=output_tokens,
                )
                return ProviderResult(
                    value=value,
                    provider=self.provider,
                    model=self.model,
                    request_id=None,
                    usage=record,
                )
        except (InvalidProviderResponse, ModelUnavailableError):
            self.budget.cancel(call_id)
            raise
        except subprocess.TimeoutExpired as exc:
            self.budget.cancel(call_id)
            raise ModelUnavailableError(
                f"Codex stage {call_id} exceeded {self.timeout_seconds} seconds"
            ) from exc
        except Exception:
            self.budget.cancel(call_id)
            raise

    @staticmethod
    def _write_images(root: Path, images: list[ImageInput]) -> list[Path]:
        import base64

        paths: list[Path] = []
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        for index, item in enumerate(images, start=1):
            path = root / f"input-{index:02d}{extensions.get(item.media_type, '.img')}"
            path.write_bytes(base64.b64decode(item.base64_data))
            paths.append(path)
        return paths


def _build_prompt(
    *,
    call_id: str,
    system_prompt: str,
    user_prompt: str,
    image_paths: list[Path],
) -> str:
    image_note = "\n".join(
        f"- Attached image {index}: {path.name}"
        for index, path in enumerate(image_paths, start=1)
    )
    return f"""You are executing one bounded PaperCraft semantic stage.

Return only the final JSON object required by the supplied output schema. Do not
write files, run commands, inspect the workspace, browse the web, or call external
tools. Work only from the material and attached images in this prompt. Preserve
all identifiers and source references exactly; never invent a source reference.

CALL ID
{call_id}

STAGE INSTRUCTIONS
{system_prompt}

ATTACHED IMAGES
{image_note or "None"}

SOURCE MATERIAL
{user_prompt}
"""


def _strict_json_schema(schema: dict) -> dict:
    """Normalize Pydantic JSON Schema for Codex structured outputs."""

    normalized = json.loads(json.dumps(schema))

    def visit(value) -> None:
        if isinstance(value, dict):
            # Pydantic emits discriminated unions as ``oneOf``. Codex structured
            # outputs accepts the equivalent ``anyOf`` form, but rejects
            # ``oneOf`` before the request is executed.
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["additionalProperties"] = False
                value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(normalized)
    return normalized


def _codex_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "ZHIPU_API_KEY",
    ):
        environment.pop(name, None)
    return environment


def _usage_from_jsonl(stdout: str) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
    return input_tokens, output_tokens


def _last_error(stdout: str, stderr: str) -> str:
    messages: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") in {"error", "turn.failed"}:
            messages.append(str(event.get("message") or event.get("error") or event))
    if messages:
        return messages[-1][:1_500]
    compact = " ".join(stderr.strip().split())
    return compact[-1_500:] or "unknown Codex execution error"
