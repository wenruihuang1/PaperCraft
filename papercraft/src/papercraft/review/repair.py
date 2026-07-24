"""Apply review patches to targeted components while preserving every other hash."""

from __future__ import annotations

import hashlib
import json

from papercraft.models import PosterPlan
from papercraft.models.review_result import RepairBatch


class RepairInvariantError(RuntimeError):
    pass


def component_hashes(plan: PosterPlan) -> dict[str, str]:
    return {
        component.component_id: hashlib.sha256(
            json.dumps(
                component.model_dump(mode="json"),
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        for component in plan.components
    }


def apply_repair_batch(plan: PosterPlan, batch: RepairBatch) -> PosterPlan:
    if any(operation.expected_revision != plan.artifact_revision for operation in batch.operations):
        raise RepairInvariantError("repair batch targets a stale PosterPlan revision")
    before = component_hashes(plan)
    payload = plan.model_dump(mode="json")
    components = {item["component_id"]: item for item in payload["components"]}
    for operation in batch.operations:
        component = components[operation.target_id]
        if operation.operation == "shorten_summary":
            maximum = int(operation.parameters.get("maximum_characters", 180))
            if len(component["summary"]) > maximum:
                component["summary"] = component["summary"][: maximum - 1].rstrip() + "…"
        elif operation.operation == "shorten_narrative":
            role = operation.parameters.get("role")
            maximum = int(operation.parameters.get("maximum_characters", 240))
            region = next(
                item for item in payload["narrative_regions"] if item["role"] == role
            )
            region["headline"] = _shorten_text(region["headline"], max(48, maximum // 3))
            region["body"] = _shorten_text(region["body"], maximum)
        elif operation.operation == "shorten_title":
            maximum = int(operation.parameters.get("maximum_characters", 72))
            component["title"] = _shorten_text(component["title"], maximum)
        elif operation.operation == "collapse_details":
            component["details"] = component["details"][:1]
            if not any(
                item["action"] == "collapse_secondary" for item in component["interactions"]
            ):
                component["interactions"].append(
                    {"event": "click", "action": "collapse_secondary"}
                )
        elif operation.operation == "adjust_chart_labels":
            for datum in component.get("chart_data", []):
                datum["label"] = datum["label"][:28]
        elif operation.operation == "qualify_claim":
            qualifier = "Evidence is limited; open the source chain for scope."
            if qualifier not in component["details"]:
                component["details"].insert(0, qualifier)
        elif operation.operation in {"resize", "increase_gap", "reorder"}:
            _apply_layout_patch(payload, operation.target_id, operation.operation, operation.parameters)
        elif operation.operation in {
            "restore_source_value",
            "replace_content",
            "repair_formula",
            "relink_evidence",
        }:
            raise RepairInvariantError(
                f"{operation.operation} requires a semantic artifact repair, not a PosterPlan patch"
            )
        else:
            raise RepairInvariantError(f"unsupported repair operation: {operation.operation}")
    payload["artifact_revision"] = plan.artifact_revision + 1
    repaired = PosterPlan.model_validate(payload)
    after = component_hashes(repaired)
    for component_id in batch.must_preserve_component_ids:
        if before[component_id] != after[component_id]:
            raise RepairInvariantError(f"repair changed preserved component {component_id}")
    return repaired


def _apply_layout_patch(payload, component_id, operation, parameters):
    profile_name = parameters.get("profile")
    profiles = payload["layout_profiles"]
    selected = [profiles[profile_name]] if profile_name in profiles else profiles.values()
    for profile in selected:
        for placement in profile["component_layouts"]:
            if placement["component_id"] != component_id:
                continue
            if operation == "resize":
                placement["row_span"] += 1
                placement["preferred_height"] *= 1.08
            elif operation == "increase_gap":
                key = (
                    "minimum_component_gap_px"
                    if profile["profile"] == "screen_16_9"
                    else "minimum_component_gap_mm"
                )
                profile[key] = max(profile[key], float(parameters.get("minimum", profile[key])))
            elif operation == "reorder":
                placement["order"] = int(parameters["order"])


def _shorten_text(text: str, maximum: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= maximum:
        return normalized
    sentences = normalized.split(". ")
    if sentences and len(sentences[0]) <= maximum:
        return sentences[0].rstrip(".!?") + "."
    words = normalized.split()
    result: list[str] = []
    for word in words:
        candidate = " ".join(result + [word])
        if len(candidate) > maximum - 1:
            break
        result.append(word)
    return " ".join(result).rstrip(" ,;:") + "…"
