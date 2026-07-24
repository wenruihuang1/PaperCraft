from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis, PosterPlan, ReviewResult


ARTIFACT_MODELS = {
    "document_ir": DocumentIR,
    "paper_analysis": PaperAnalysis,
    "evidence_graph": EvidenceGraph,
    "poster_plan": PosterPlan,
    "review_result": ReviewResult,
}


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixture_root(project_root: Path) -> Path:
    return project_root / "tests" / "fixtures"


@pytest.fixture
def valid_payloads(fixture_root: Path) -> dict[str, dict[str, Any]]:
    base = fixture_root / "valid" / "minimal"
    return {
        name: json.loads((base / f"{name}.json").read_text(encoding="utf-8"))
        for name in ARTIFACT_MODELS
    }


@pytest.fixture
def valid_models(valid_payloads: dict[str, dict[str, Any]]) -> tuple[Any, ...]:
    return tuple(
        ARTIFACT_MODELS[name].model_validate(copy.deepcopy(valid_payloads[name]))
        for name in ARTIFACT_MODELS
    )


def replace_at_path(payload: dict[str, Any], path: list[str | int], replacement: Any) -> None:
    target: Any = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement

