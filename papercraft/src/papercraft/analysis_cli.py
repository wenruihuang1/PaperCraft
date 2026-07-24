"""Offline CLI for the deterministic PaperAnalysis baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from papercraft.analysis import HeuristicPaperAnalyzer
from papercraft.models.document_ir import DocumentIR
from papercraft.validation import validate_paper_analysis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a source-grounded heuristic PaperAnalysis without an LLM"
    )
    parser.add_argument("document_ir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    document_ir = DocumentIR.model_validate_json(
        args.document_ir.read_text(encoding="utf-8")
    )
    analysis = HeuristicPaperAnalyzer().analyze(document_ir)
    validate_paper_analysis(document_ir, analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(analysis.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"extracted {len(analysis.concepts)} concepts, {len(analysis.methods)} methods, "
        f"{len(analysis.claims)} claims, {len(analysis.experiments)} experiments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

