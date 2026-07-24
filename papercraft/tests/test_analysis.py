from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from papercraft.analysis import HeuristicPaperAnalyzer, PaperAnalyzer
from papercraft.analysis.semantic_analyzer import _normalize_source_equation_ids
from papercraft.models.document_ir import DocumentIR
from papercraft.models.paper_analysis import PaperAnalysis
from papercraft.validation import ArtifactReferenceError, validate_paper_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPER_IDS = ("ppr_dev_001", "ppr_dev_002")


def test_paper_analyzer_boundary_is_abstract():
    assert PaperAnalyzer.__abstractmethods__ == {"analyze"}


def test_document_ir_1_0_contract_rejects_future_version(valid_payloads):
    payload = valid_payloads["document_ir"]
    payload["schema_version"] = "1.1.0"
    with pytest.raises(ValidationError, match="schema_version"):
        DocumentIR.model_validate(payload)


def test_paper_analysis_requires_problem_and_motivation(valid_payloads):
    payload = valid_payloads["paper_analysis"]
    payload["concepts"] = [
        item for item in payload["concepts"] if item["concept_type"] != "motivation"
    ]
    with pytest.raises(ValidationError, match="motivation"):
        PaperAnalysis.model_validate(payload)


def test_standalone_analysis_validation_rejects_unknown_source(valid_models):
    document_ir, paper_analysis, *_ = valid_models
    invalid = paper_analysis.model_copy(deep=True)
    invalid.claims[0].source_refs = ["src_missing"]
    with pytest.raises(ArtifactReferenceError, match="UNRESOLVABLE_SOURCE_REF"):
        validate_paper_analysis(document_ir, invalid)


@pytest.mark.parametrize("paper_id", PAPER_IDS)
def test_heuristic_baseline_is_source_grounded_for_development_papers(paper_id):
    path = (
        PROJECT_ROOT
        / "evaluation"
        / "papers"
        / paper_id
        / "annotations"
        / "document_ir.gold.json"
    )
    document_ir = DocumentIR.model_validate_json(path.read_text(encoding="utf-8"))
    analysis = HeuristicPaperAnalyzer().analyze(document_ir)
    validate_paper_analysis(document_ir, analysis)

    assert {item.concept_type for item in analysis.concepts} >= {"problem", "motivation"}
    assert analysis.methods and analysis.claims and analysis.experiments
    assert analysis.equations == []

    source_quotes = {
        item.source_ref_id: " ".join(item.quote.split())
        for item in document_ir.source_refs
    }
    extracted_fields = [
        *[(item.statement, item.source_refs) for item in analysis.concepts],
        *[(item.statement, item.source_refs) for item in analysis.claims],
        *[
            (step.description, step.source_refs)
            for method in analysis.methods
            for step in method.steps
        ],
        *[
            (result.value, result.source_refs)
            for experiment in analysis.experiments
            for result in experiment.results
        ],
    ]
    for text, refs in extracted_fields:
        normalized = " ".join(text.split())
        assert any(normalized in source_quotes[source_ref] for source_ref in refs)

    repeated = HeuristicPaperAnalyzer().analyze(document_ir)
    assert repeated == analysis


def test_standalone_analysis_validation_checks_revision(valid_models):
    document_ir, paper_analysis, *_ = valid_models
    invalid = copy.deepcopy(paper_analysis)
    invalid.source_revision = document_ir.artifact_revision + 1
    with pytest.raises(ArtifactReferenceError, match="REVISION_MISMATCH"):
        validate_paper_analysis(document_ir, invalid)


def test_semantic_equation_shorthand_resolves_from_cited_source(valid_models):
    document_ir, paper_analysis, *_ = valid_models
    original = paper_analysis.equations[0]
    text_source = next(
        item.source_ref_id
        for item in document_ir.source_refs
        if item.locator.source_equation_id is None
    )
    shorthand = original.model_copy(
        update={
            "source_equation_id": "seq_1",
            "label": f"({original.label})",
            "source_refs": [text_source],
        }
    )

    normalized = _normalize_source_equation_ids([shorthand], document_ir)

    assert normalized[0].source_equation_id == original.source_equation_id
