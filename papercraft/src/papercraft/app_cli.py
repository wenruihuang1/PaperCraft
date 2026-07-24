"""Local application commands; paid model work is never the default."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

from papercraft.service import PaperCraftService


def main() -> None:
    parser = argparse.ArgumentParser(prog="papercraft")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="run the local Web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    demo = subcommands.add_parser("demo", help="build and export the reviewed AMP demo")
    demo.add_argument("--no-export", action="store_true")
    bootstrap = subcommands.add_parser(
        "bootstrap-eval", help="prepare one reviewed evaluation DocumentIR for analysis"
    )
    bootstrap.add_argument("paper_id")
    bootstrap.add_argument("--job-id")
    gold_demo = subcommands.add_parser(
        "gold-demo", help="prepare one adjudicated evaluation sample for export"
    )
    gold_demo.add_argument("paper_id")
    gold_demo.add_argument("--job-id")
    analyze = subcommands.add_parser(
        "analyze", help="explicitly run configured paid model stages for one job"
    )
    analyze.add_argument("job_id")
    codex_analyze = subcommands.add_parser(
        "codex-analyze",
        help="run semantic stages with the locally authenticated Codex CLI",
    )
    codex_analyze.add_argument("job_id")
    offline_analyze = subcommands.add_parser(
        "offline-analyze",
        help="build a source-extractive fallback when no model is available",
    )
    offline_analyze.add_argument("job_id")
    narrate = subcommands.add_parser(
        "narrate", help="explicitly generate the optional shadow NarrativePlan"
    )
    narrate.add_argument("job_id")
    codex_narrate = subcommands.add_parser(
        "codex-narrate",
        help="generate the NarrativePlan with the locally authenticated Codex CLI",
    )
    codex_narrate.add_argument("job_id")
    plan = subcommands.add_parser(
        "plan", help="rebuild the deterministic baseline with the current layout engine"
    )
    plan.add_argument("job_id")
    direct = subcommands.add_parser(
        "direct", help="apply the NarrativePlan through constrained visual direction"
    )
    direct.add_argument("job_id")
    export = subcommands.add_parser("export", help="export one prepared job")
    export.add_argument("job_id")
    arxiv = subcommands.add_parser("import-arxiv", help="download an arXiv PDF and TeX source")
    arxiv.add_argument("url")
    arxiv.add_argument("--paper-id", required=True)
    arxiv.add_argument("--job-id", required=True)
    codex_run = subcommands.add_parser(
        "codex-run",
        help="run a local PDF end-to-end through Codex without model API keys",
    )
    codex_run.add_argument("pdf", type=Path)
    codex_run.add_argument("--job-id")
    codex_run.add_argument("--paper-id")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    # Keep the local example file usable for the user's current setup while
    # preserving the normal precedence of an untracked .env file.
    load_dotenv(project_root / ".env.example", override=False)
    service = PaperCraftService(project_root)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("papercraft.api:app", host=args.host, port=args.port, reload=False)
        return
    if args.command == "demo":
        job = service.bootstrap_amp_demo()
        output = {"job": job}
        if not args.no_export:
            result = service.export(job["job_id"])
            output["job"] = service.store.get_job(job["job_id"]).as_dict()
            output["export"] = {
                "interactive": str(result.static_dir),
                "screen_png": str(result.screen_png),
                "print_png": str(result.print_png),
                "a0_pdf": str(result.a0_pdf),
                "method_inspector_png": str(result.method_inspector_png),
                "source_inspector_png": str(result.source_inspector_png),
                "equation_inspector_png": str(result.equation_inspector_png),
            }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return
    if args.command == "bootstrap-eval":
        print(
            json.dumps(
                service.bootstrap_evaluation_document(
                    args.paper_id, job_id=args.job_id
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.command == "gold-demo":
        print(json.dumps(service.bootstrap_gold_demo(args.paper_id, job_id=args.job_id), indent=2, ensure_ascii=False))
        return
    if args.command == "import-arxiv":
        print(json.dumps(service.bootstrap_arxiv(args.url, paper_id=args.paper_id, job_id=args.job_id), indent=2, ensure_ascii=False))
        return
    if args.command == "analyze":
        print(json.dumps(service.analyze_with_models(args.job_id), indent=2))
        return
    if args.command == "codex-analyze":
        print(json.dumps(service.analyze_with_codex(args.job_id), indent=2))
        return
    if args.command == "offline-analyze":
        print(json.dumps(service.analyze_offline(args.job_id), indent=2))
        return
    if args.command == "narrate":
        print(
            json.dumps(
                service.narrate_with_model(args.job_id).model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.command == "codex-narrate":
        print(
            json.dumps(
                service.narrate_with_codex(args.job_id).model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.command == "plan":
        print(
            json.dumps(
                service.plan(args.job_id).model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.command == "direct":
        visual, poster = service.direct(args.job_id)
        print(
            json.dumps(
                {
                    "visual_plan": visual.model_dump(mode="json"),
                    "poster_plan": poster.model_dump(mode="json"),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.command == "export":
        result = service.export(args.job_id)
        print(
            json.dumps(
                {
                    "interactive": str(result.static_dir),
                    "screen_png": str(result.screen_png),
                    "print_png": str(result.print_png),
                    "a0_pdf": str(result.a0_pdf),
                    "method_inspector_png": str(result.method_inspector_png),
                    "source_inspector_png": str(result.source_inspector_png),
                    "equation_inspector_png": str(result.equation_inspector_png),
                },
                indent=2,
            )
        )
        return
    if args.command == "codex-run":
        pdf_path = args.pdf.expanduser().resolve()
        if not pdf_path.is_file():
            parser.error(f"PDF not found: {pdf_path}")
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:12]
        job_id = args.job_id or f"codex_{digest}"
        paper_id = args.paper_id or f"ppr_codex_{digest}"
        service.bootstrap_pdf(
            pdf_path,
            paper_id=paper_id,
            job_id=job_id,
        )
        service.analyze_with_codex(job_id)
        narrative = service.narrate_with_codex(job_id)
        visual, _poster = service.direct(job_id)
        result = service.export(job_id)
        print(
            json.dumps(
                {
                    "job": service.store.get_job(job_id).as_dict(),
                    "narrative_archetype": narrative.archetype,
                    "visual_archetype": visual.visual_archetype,
                    "interactive": str(result.static_dir),
                    "screen_png": str(result.screen_png),
                    "print_png": str(result.print_png),
                    "a0_pdf": str(result.a0_pdf),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
