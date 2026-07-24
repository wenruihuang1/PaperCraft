from __future__ import annotations

import fitz
from fastapi.testclient import TestClient

from papercraft.api import create_app


def test_local_api_bootstraps_demo_without_paid_calls(project_root, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(create_app(project_root, runtime_root=tmp_path / "runtime"))
    assert client.get("/api/health").json()["paid_calls"] == "explicit_only"
    created = client.post("/api/demo")
    assert created.status_code == 200
    assert created.json()["spent_usd"] == "0"
    bundle = client.get("/api/jobs/amp_demo/bundle")
    assert bundle.status_code == 200
    assert set(bundle.json()) == {
        "document_ir",
        "paper_analysis",
        "evidence_graph",
        "poster_plan",
        "review_result",
    }
    explicit = client.post("/api/jobs/amp_demo/run/analyze")
    assert explicit.status_code == 409


def test_upload_rejects_textless_pdf_clearly(project_root, tmp_path):
    path = tmp_path / "textless.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    client = TestClient(create_app(project_root, runtime_root=tmp_path / "runtime"))
    response = client.post(
        "/api/jobs",
        files={"file": ("textless.pdf", path.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "text layer" in response.json()["detail"]


def test_arxiv_ingest_rejects_non_arxiv_url(project_root, tmp_path):
    client = TestClient(create_app(project_root, runtime_root=tmp_path / "runtime"))
    response = client.post("/api/jobs/arxiv", json={"url": "https://example.com/paper.pdf"})
    assert response.status_code == 422
    assert "arXiv" in response.json()["detail"]
