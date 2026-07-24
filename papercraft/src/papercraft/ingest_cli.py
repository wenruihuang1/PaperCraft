"""Offline CLI for capability detection and deterministic DocumentIR extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from papercraft.ingest import PyMuPDFAdapter, UnsupportedPDFError


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract deterministic DocumentIR from an English text PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    adapter = PyMuPDFAdapter()
    report = adapter.detect(args.pdf)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "capability_report.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        document_ir = adapter.extract(args.pdf, args.paper_id, args.output_dir)
    except UnsupportedPDFError as error:
        print(error)
        return 2
    (args.output_dir / "document_ir.json").write_text(
        json.dumps(document_ir.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"extracted {len(document_ir.pages)} pages, {len(document_ir.blocks)} blocks, "
        f"{len(document_ir.equations)} equations, {len(document_ir.assets)} assets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

