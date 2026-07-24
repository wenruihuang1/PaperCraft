"""FastAPI surface for local PaperCraft jobs."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from papercraft.ingest import PyMuPDFAdapter, UnsupportedPDFError
from papercraft.render import generate_source_previews
from papercraft.service import PaperCraftService


class ArxivJobRequest(BaseModel):
    """Request body for the URL-first arXiv ingestion path."""

    url: str = Field(min_length=1)
    paper_id: str | None = None
    job_id: str | None = None


def create_app(
    project_root: Path | None = None, runtime_root: Path | None = None
) -> FastAPI:
    root = project_root or Path(__file__).resolve().parents[2]
    service = PaperCraftService(root, runtime_root=runtime_root)
    app = FastAPI(title="PaperCraft", version="0.1.0")
    app.state.service = service

    @app.get("/api/health")
    def health():
        return {"status": "ok", "paid_calls": "explicit_only"}

    @app.get("/api/jobs")
    def list_jobs():
        return [job.as_dict() for job in service.store.list_jobs()]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return service.store.get_job(job_id).as_dict()
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc

    @app.post("/api/jobs")
    async def create_job(file: UploadFile = File(...)):
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(415, "PaperCraft accepts PDF files only")
        payload = await file.read()
        if len(payload) > 100 * 1024 * 1024:
            raise HTTPException(413, "PDF exceeds the 100 MB local safety limit")
        digest = hashlib.sha256(payload).hexdigest()
        job_id = f"job_{digest[:12]}"
        paper_id = f"ppr_{digest[:12]}"
        title = Path(file.filename or "paper.pdf").stem
        service.store.upsert_job(
            job_id=job_id,
            paper_id=paper_id,
            title=title,
            status="created",
            budget_limit_usd=Decimal("4.00"),
        )
        job_dir = service.artifacts.job_dir(job_id)
        pdf_path = job_dir / "source.pdf"
        pdf_path.write_bytes(payload)
        adapter = PyMuPDFAdapter()
        report = adapter.detect(pdf_path)
        (job_dir / "capability_report.json").write_text(
            json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        if report.status != "supported":
            message = _rejection_message(report.rejection_codes)
            service.store.update_status(job_id, "failed", error=message)
            raise HTTPException(422, message)
        try:
            document = adapter.extract(pdf_path, paper_id, job_dir)
        except UnsupportedPDFError as exc:
            message = _rejection_message(exc.report.rejection_codes)
            service.store.update_status(job_id, "failed", error=message)
            raise HTTPException(422, message) from exc
        service.artifacts.save(job_id, "document_ir", document)
        generate_source_previews(document, pdf_path, job_dir / "assets")
        job = service.store.upsert_job(
            job_id=job_id,
            paper_id=paper_id,
            title=document.metadata.title,
            status="document_ready",
        )
        return job.as_dict()

    @app.post("/api/jobs/arxiv")
    def create_arxiv_job(request: ArxivJobRequest):
        """Download an arXiv PDF plus TeX source and create a document-ready job."""

        digest = hashlib.sha256(request.url.encode("utf-8")).hexdigest()[:12]
        paper_id = request.paper_id or f"ppr_arxiv_{digest}"
        job_id = request.job_id or f"arxiv_{digest}"
        try:
            return service.bootstrap_arxiv(
                request.url,
                paper_id=paper_id,
                job_id=job_id,
            )
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/jobs/{job_id}/bundle")
    def get_bundle(job_id: str):
        try:
            job = service.store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc
        missing = [
            name
            for name in service.artifacts.required_artifact_names
            if not service.artifacts.has(job_id, name)
        ]
        if missing:
            raise HTTPException(
                409,
                {
                    "message": "This job has not reached Poster rendering yet.",
                    "status": job.status,
                    "missing": missing,
                },
            )
        return service.artifacts.bundle(job_id)

    @app.post("/api/jobs/{job_id}/run/{stage}")
    def run_stage(job_id: str, stage: str):
        try:
            service.store.get_job(job_id)
            if stage == "analyze":
                return service.analyze_with_models(job_id)
            if stage == "narrate":
                return service.narrate_with_model(job_id).model_dump(mode="json")
            if stage == "direct":
                visual, poster = service.direct(job_id)
                return {
                    "visual_plan": visual.model_dump(mode="json"),
                    "poster_plan": poster.model_dump(mode="json"),
                }
            if stage == "plan":
                return service.plan(job_id).model_dump(mode="json")
            if stage == "review":
                return service.review(job_id).model_dump(mode="json")
            if stage == "export":
                result = service.export(job_id)
                return {
                    "static_dir": str(result.static_dir),
                    "screen_png": str(result.screen_png),
                    "a0_pdf": str(result.a0_pdf),
                }
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(404, f"Unknown stage: {stage}")

    @app.post("/api/demo")
    def create_demo():
        return service.bootstrap_amp_demo()

    @app.get("/api/jobs/{job_id}/download/a0")
    def download_a0(job_id: str):
        path = root / "output" / "pdf" / f"{service.store.get_job(job_id).paper_id}-a0.pdf"
        if not path.exists():
            raise HTTPException(404, "A0 PDF has not been exported")
        return FileResponse(path, media_type="application/pdf", filename=path.name)

    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=output), name="outputs")
    distribution = root / "web" / "dist"
    if distribution.exists():
        app.mount("/", StaticFiles(directory=distribution, html=True), name="studio")

    return app


def _rejection_message(codes: list[str]) -> str:
    explanations = {
        "ENCRYPTED_PDF": "the PDF is encrypted",
        "NO_TEXT_LAYER": "the PDF has no usable text layer",
        "SCANNED_PDF": "the PDF appears to be scanned; OCR is outside the MVP",
        "NON_ENGLISH_PDF": "the PDF is not predominantly English",
        "MALFORMED_PDF": "the PDF is malformed or unreadable",
    }
    return "Unsupported PDF: " + "; ".join(explanations.get(code, code) for code in codes)


app = create_app()
