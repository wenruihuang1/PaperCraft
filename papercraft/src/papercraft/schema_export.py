"""Export the five public Pydantic contracts as checked-in JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from papercraft.models import (
    DocumentIR,
    EvidenceGraph,
    NarrativePlan,
    PaperAnalysis,
    PosterPlan,
    ReviewResult,
    VisualPlan,
)


SCHEMA_MODELS = {
    "document_ir.schema.json": DocumentIR,
    "paper_analysis.schema.json": PaperAnalysis,
    "evidence_graph.schema.json": EvidenceGraph,
    "narrative_plan.schema.json": NarrativePlan,
    "visual_plan.schema.json": VisualPlan,
    "poster_plan.schema.json": PosterPlan,
    "review_result.schema.json": ReviewResult,
}


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for file_name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://papercraft.local/schemas/{file_name}"
        path = output_dir / file_name
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    export_schemas(project_root / "schemas")


if __name__ == "__main__":
    main()
