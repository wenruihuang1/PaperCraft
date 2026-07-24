from __future__ import annotations

import copy
import json

import pytest

from conftest import ARTIFACT_MODELS, replace_at_path
from papercraft.validation import ArtifactReferenceError, validate_artifact_set


def _materialize(payloads):
    return tuple(
        ARTIFACT_MODELS[name].model_validate(copy.deepcopy(payloads[name]))
        for name in ARTIFACT_MODELS
    )


def test_minimal_fixture_has_no_cross_artifact_errors(valid_models):
    validate_artifact_set(*valid_models)


def test_cross_reference_mutation_fixtures(fixture_root, valid_payloads):
    specs = []
    for path in sorted((fixture_root / "invalid").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec["validation_layer"] == "cross_reference":
            specs.append((path.name, spec))
    assert len(specs) >= 3

    for name, spec in specs:
        payloads = copy.deepcopy(valid_payloads)
        replace_at_path(
            payloads[spec["artifact"]],
            spec["path"],
            spec["replacement"],
        )
        with pytest.raises(ArtifactReferenceError) as exc_info:
            validate_artifact_set(*_materialize(payloads))
        assert spec["expected_error"] in str(exc_info.value), name


def test_revision_mismatch_is_rejected(valid_payloads):
    payloads = copy.deepcopy(valid_payloads)
    payloads["poster_plan"]["analysis_revision"] = 2
    with pytest.raises(ArtifactReferenceError, match="REVISION_MISMATCH"):
        validate_artifact_set(*_materialize(payloads))


def test_all_reference_errors_are_reported_together(valid_payloads):
    payloads = copy.deepcopy(valid_payloads)
    payloads["paper_analysis"]["claims"][0]["source_refs"][0] = "src_missing"
    payloads["poster_plan"]["components"][2]["evidence_refs"][0] = "ev_missing"
    with pytest.raises(ArtifactReferenceError) as exc_info:
        validate_artifact_set(*_materialize(payloads))
    codes = {issue.code for issue in exc_info.value.issues}
    assert {"UNRESOLVABLE_SOURCE_REF", "UNKNOWN_EVIDENCE_REF"} <= codes

