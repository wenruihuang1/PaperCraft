from __future__ import annotations

import json
from pathlib import Path

import pytest

from papercraft.analysis import HeuristicPaperAnalyzer
from papercraft.ingest import PDFCapabilityReport, PyMuPDFAdapter
from papercraft.models.document_ir import DocumentIR
from papercraft.models.paper_analysis import PaperAnalysis
from papercraft.validation import validate_paper_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = PROJECT_ROOT / "evaluation"
PAPER_IDS = ("ppr_dev_001", "ppr_dev_002")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_contains_two_development_papers_and_one_generalization_paper():
    manifest = _read_json(EVALUATION_ROOT / "manifest.json")
    assert manifest["stage"] == "MVP_SINGLE_PAPER"
    assert [entry["paper_id"] for entry in manifest["entries"]] == [
        "ppr_dev_001", "ppr_dev_002", "ppr_dev_003"
    ]
    assert [entry["split"] for entry in manifest["entries"]] == [
        "dev", "dev", "generalization"
    ]
    assert manifest["entries"][0]["status"] == "gold_poster_completed"
    assert manifest["entries"][1]["status"] == "analysis_baseline_reviewed"
    assert manifest["entries"][2]["status"] == "source_adjudicated_poster"


@pytest.mark.parametrize("paper_id", PAPER_IDS)
def test_reviewed_document_ir_is_traceable_and_matches_local_source(paper_id):
    paper_dir = EVALUATION_ROOT / "papers" / paper_id
    annotations = paper_dir / "annotations"
    metadata = _read_json(paper_dir / "metadata.json")
    report = PDFCapabilityReport.model_validate(
        _read_json(annotations / "capability_report.json")
    )
    ir = DocumentIR.model_validate(_read_json(annotations / "document_ir.gold.json"))
    audit = _read_json(annotations / "document_ir.audit.json")

    assert (paper_dir / metadata["source_file"]).is_file()
    assert report.status == "supported"
    assert report.rejection_codes == []
    assert report.sha256 == metadata["source_sha256"] == ir.source.sha256
    assert ir.paper_id == paper_id
    assert ir.source.page_count == len(ir.pages) == report.metrics.page_count
    assert len(ir.metadata.abstract or "") >= 1000
    assert audit["status"] == "passed_with_notes"
    assert audit["counts"] == {
        "pages": len(ir.pages),
        "sections": len(ir.sections),
        "blocks": len(ir.blocks),
        "equations": len(ir.equations),
        "assets": len(ir.assets),
    }

    pages = {page.page_number: page for page in ir.pages}
    for ref in ir.source_refs:
        if ref.locator.bbox is None:
            continue
        page = pages[ref.locator.page]
        assert 0 <= ref.locator.bbox.x0 < ref.locator.bbox.x1 <= page.width
        assert 0 <= ref.locator.bbox.y0 < ref.locator.bbox.y1 <= page.height
    for asset in ir.assets:
        asset_path = annotations / asset.path
        assert asset_path.is_file()
        assert asset_path.stat().st_size > 0
    generated_asset_paths = {
        path.relative_to(annotations).as_posix()
        for path in (annotations / "assets").glob("*.png")
    }
    assert generated_asset_paths == {
        asset.path for asset in ir.assets
    }


@pytest.mark.parametrize("paper_id", PAPER_IDS)
def test_current_adapter_reproduces_reviewed_structural_ir(paper_id, tmp_path):
    paper_dir = EVALUATION_ROOT / "papers" / paper_id
    pdf = paper_dir / "source" / "paper.pdf"
    annotations = paper_dir / "annotations"
    stored_report = PDFCapabilityReport.model_validate(
        _read_json(annotations / "capability_report.json")
    )
    gold = DocumentIR.model_validate(_read_json(annotations / "document_ir.gold.json"))

    adapter = PyMuPDFAdapter()
    assert adapter.detect(pdf) == stored_report
    generated = adapter.extract(pdf, paper_id, tmp_path / paper_id)

    assert generated.source == gold.source
    assert generated.pages == gold.pages
    assert generated.sections == gold.sections
    assert generated.blocks == gold.blocks
    assert generated.equations == gold.equations
    assert generated.assets == gold.assets
    assert generated.source_refs == gold.source_refs
    assert generated.metadata.title == gold.metadata.title
    assert generated.metadata.abstract == gold.metadata.abstract


def test_ieee_two_column_abstract_precedes_introduction():
    path = (
        EVALUATION_ROOT
        / "papers"
        / "ppr_dev_002"
        / "annotations"
        / "document_ir.gold.json"
    )
    ir = DocumentIR.model_validate(_read_json(path))
    abstract_heading = next(block for block in ir.blocks if block.text == "Abstract")
    continuation = next(
        block for block in ir.blocks if block.text.startswith("cross-sequence (bSSFP-LGE)")
    )
    introduction = next(block for block in ir.blocks if block.text == "I. INTRODUCTION")
    assert abstract_heading.reading_order < continuation.reading_order < introduction.reading_order
    assert "cross-site prostate MRI segmentation" in (ir.metadata.abstract or "")


@pytest.mark.parametrize("paper_id", PAPER_IDS)
def test_checked_in_analysis_baseline_is_grounded_and_audited(paper_id):
    annotations = EVALUATION_ROOT / "papers" / paper_id / "annotations"
    document_ir = DocumentIR.model_validate(
        _read_json(annotations / "document_ir.gold.json")
    )
    analysis = PaperAnalysis.model_validate(
        _read_json(annotations / "paper_analysis.baseline.json")
    )
    audit = _read_json(annotations / "paper_analysis.baseline.audit.json")

    validate_paper_analysis(document_ir, analysis)
    assert HeuristicPaperAnalyzer().analyze(document_ir) == analysis
    assert {item.concept_type for item in analysis.concepts} >= {"problem", "motivation"}
    assert analysis.methods and analysis.claims and analysis.experiments
    assert audit["status"] == "structurally_passed_semantic_review_required"


def test_stability_generalization_gold_has_full_grounded_narrative_and_equations():
    annotations = EVALUATION_ROOT / "papers" / "ppr_dev_003" / "annotations"
    document = DocumentIR.model_validate_json(
        (annotations / "document_ir.gold.json").read_text()
    )
    analysis = PaperAnalysis.model_validate_json(
        (annotations / "paper_analysis.gold.json").read_text()
    )
    validate_paper_analysis(document, analysis)
    assert analysis.schema_version == "1.2.0"
    assert analysis.narrative_frame is not None
    assert len(analysis.methods) == 3
    assert [item.label for item in analysis.equations] == [str(i) for i in range(1, 18)]
    valid_refs = {item.source_ref_id for item in document.source_refs}
    for equation in analysis.equations:
        assert set(equation.source_refs) <= valid_refs
        preview = annotations / "assets" / f"preview_{equation.source_refs[0]}.png"
        assert preview.is_file() and preview.stat().st_size > 0
    method_overview = next(asset for asset in document.assets if asset.asset_id == "ast_figure_002")
    caption = next(block for block in document.blocks if block.text == method_overview.caption)
    assert method_overview.bbox.y0 < caption.bbox.y0 - 100
