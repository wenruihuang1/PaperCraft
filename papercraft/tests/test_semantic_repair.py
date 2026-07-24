from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis
from papercraft.review.semantic_repair import (
    ReplaceClaim,
    SemanticRepairBatch,
    apply_semantic_repairs,
    semantic_object_hashes,
)


def test_semantic_repair_changes_only_named_object_and_revisions(project_root):
    root = project_root / "evaluation" / "papers" / "ppr_dev_001" / "annotations"
    document = DocumentIR.model_validate_json((root / "document_ir.gold.json").read_text())
    analysis = PaperAnalysis.model_validate_json((root / "paper_analysis.gold.json").read_text())
    evidence = EvidenceGraph.model_validate_json((root / "evidence_graph.gold.json").read_text())
    original = analysis.claims[0]
    replacement = original.model_copy(
        update={"qualifiers": original.qualifiers + ["targeted repair marker"]}
    )
    before = semantic_object_hashes(analysis, evidence)
    repaired_analysis, repaired_evidence = apply_semantic_repairs(
        analysis,
        evidence,
        SemanticRepairBatch(
            replacements=[
                ReplaceClaim(
                    operation="replace_claim",
                    target_id=original.claim_id,
                    replacement=replacement,
                )
            ]
        ),
    )
    after = semantic_object_hashes(repaired_analysis, repaired_evidence)
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {f"Claim:{original.claim_id}"}
    assert repaired_analysis.artifact_revision == analysis.artifact_revision + 1
    assert repaired_evidence.analysis_revision == repaired_analysis.artifact_revision
    assert repaired_evidence.artifact_revision == evidence.artifact_revision + 1
