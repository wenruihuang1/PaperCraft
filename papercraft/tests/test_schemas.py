from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from conftest import ARTIFACT_MODELS, replace_at_path
from papercraft.schema_export import export_schemas


def test_minimal_fixture_validates_against_pydantic(valid_payloads):
    for artifact, model in ARTIFACT_MODELS.items():
        model.model_validate(valid_payloads[artifact])


def test_checked_in_json_schemas_accept_minimal_fixture(project_root, valid_payloads):
    for artifact, payload in valid_payloads.items():
        schema = json.loads(
            (project_root / "schemas" / f"{artifact}.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)


def test_checked_in_schemas_match_pydantic_export(project_root, tmp_path):
    export_schemas(tmp_path)
    for schema_path in sorted((project_root / "schemas").glob("*.schema.json")):
        generated = json.loads((tmp_path / schema_path.name).read_text(encoding="utf-8"))
        checked_in = json.loads(schema_path.read_text(encoding="utf-8"))
        assert checked_in == generated


def test_models_forbid_unknown_fields(valid_payloads):
    payload = valid_payloads["document_ir"]
    payload["future_unapproved_field"] = True
    with pytest.raises(ValidationError, match="future_unapproved_field"):
        ARTIFACT_MODELS["document_ir"].model_validate(payload)


@pytest.mark.parametrize(
    ("artifact", "path", "replacement"),
    [
        ("evidence_graph", ["claim_assessments", 0, "status"], "unsupported"),
        ("poster_plan", ["components", 0, "component_type"], "freeform_svg"),
        ("review_result", ["checker_summaries", 0, "checker"], "formula_depth"),
        ("poster_plan", ["layout_profiles", "screen_16_9", "typography", "body_min_px"], 17),
        ("poster_plan", ["layout_profiles", "print_a0_landscape", "minimum_component_gap_mm"], 7),
    ],
)
def test_mvp_boundaries_are_schema_enforced(valid_payloads, artifact, path, replacement):
    replace_at_path(valid_payloads[artifact], path, replacement)
    with pytest.raises(ValidationError):
        ARTIFACT_MODELS[artifact].model_validate(valid_payloads[artifact])


def test_schema_invalid_mutation_fixtures(fixture_root, valid_payloads):
    specs = []
    for path in sorted((fixture_root / "invalid").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec["validation_layer"] == "schema":
            specs.append((path.name, spec))
    assert len(specs) >= 3
    for name, spec in specs:
        payload = valid_payloads[spec["artifact"]]
        replace_at_path(payload, spec["path"], spec["replacement"])
        with pytest.raises(ValidationError) as exc_info:
            ARTIFACT_MODELS[spec["artifact"]].model_validate(payload)
        assert spec["expected_error"] in str(exc_info.value), name


def test_model_semantic_mutation_fixtures(fixture_root, valid_payloads):
    specs = []
    for path in sorted((fixture_root / "invalid").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec["validation_layer"] == "model":
            specs.append((path.name, spec))
    assert specs
    for name, spec in specs:
        payload = valid_payloads[spec["artifact"]]
        replace_at_path(payload, spec["path"], spec["replacement"])
        with pytest.raises(ValidationError) as exc_info:
            ARTIFACT_MODELS[spec["artifact"]].model_validate(payload)
        assert spec["expected_error"] in str(exc_info.value), name

