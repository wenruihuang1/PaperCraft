"""Application service that advances one job without hiding stage boundaries."""

from __future__ import annotations

import json
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path

from papercraft.analysis.heuristic_analyzer import HeuristicPaperAnalyzer
from papercraft.analysis.reference_profiles import reviewed_reference_analysis
from papercraft.analysis.semantic_analyzer import SemanticPaperAnalyzer
from papercraft.evidence import OfflineEvidenceBuilder, SemanticEvidenceBuilder
from papercraft.ingest import PyMuPDFAdapter
from papercraft.ingest.arxiv import download_arxiv
from papercraft.models import (
    DocumentIR,
    EvidenceGraph,
    NarrativePlan,
    PaperAnalysis,
    PosterPlan,
    ReviewResult,
    VisualPlan,
)
from papercraft.planning import SemanticNarrativePlanner, VisualDirector, build_poster_plan
from papercraft.providers import AnthropicStructuredProvider, CodexExecStructuredProvider
from papercraft.providers.base import MissingCredentialError, ModelUnavailableError
from papercraft.render import ExportResult, PosterExporter, generate_source_previews
from papercraft.review import (
    apply_repair_batch,
    apply_semantic_repairs,
    request_semantic_repairs,
    run_deterministic_review,
    run_semantic_audit,
)
from papercraft.runtime import BudgetLedger, BudgetExceededError
from papercraft.runtime.budget import UsageRecord
from papercraft.storage import ArtifactRepository, JobStore
from papercraft.validation import validate_artifact_set, validate_paper_analysis


class PaperCraftService:
    def __init__(self, project_root: Path, runtime_root: Path | None = None) -> None:
        self.project_root = project_root
        self.runtime_root = runtime_root or project_root / "runtime"
        self.store = JobStore(self.runtime_root)
        self.artifacts = ArtifactRepository(self.store)
        self.exporter = PosterExporter(project_root)

    def bootstrap_amp_demo(self, *, job_id: str = "amp_demo") -> dict:
        annotations = (
            self.project_root / "evaluation" / "papers" / "ppr_dev_001" / "annotations"
        )
        document = DocumentIR.model_validate_json(
            (annotations / "document_ir.gold.json").read_text(encoding="utf-8")
        )
        analysis = PaperAnalysis.model_validate_json(
            (annotations / "paper_analysis.gold.json").read_text(encoding="utf-8")
        )
        evidence = EvidenceGraph.model_validate_json(
            (annotations / "evidence_graph.gold.json").read_text(encoding="utf-8")
        )
        try:
            self.store.delete_job(job_id)
        except KeyError:
            pass
        self.store.create_job(
            job_id=job_id,
            paper_id=document.paper_id,
            title=analysis.metadata.title,
            status="poster_ready",
        )
        job_dir = self.artifacts.job_dir(job_id)
        source_assets = job_dir / "assets"
        source_assets.mkdir(parents=True, exist_ok=True)
        for source in (annotations / "assets").glob("*"):
            if source.is_file():
                shutil.copy2(source, source_assets / source.name)
        self.artifacts.save(job_id, "document_ir", document)
        self.artifacts.save(job_id, "paper_analysis", analysis)
        self.artifacts.save(job_id, "evidence_graph", evidence)
        plan = build_poster_plan(document, analysis, evidence)
        self.artifacts.save(job_id, "poster_plan", plan)
        provisional = run_deterministic_review(document, analysis, evidence, plan)
        self.artifacts.save(job_id, "review_result", provisional)
        validate_artifact_set(document, analysis, evidence, plan, provisional)
        return self.store.get_job(job_id).as_dict()

    def bootstrap_evaluation_document(
        self, paper_id: str, *, job_id: str | None = None
    ) -> dict:
        """Create a model-ready job from a reviewed evaluation DocumentIR."""

        annotations = self.project_root / "evaluation" / "papers" / paper_id / "annotations"
        document = DocumentIR.model_validate_json(
            (annotations / "document_ir.gold.json").read_text(encoding="utf-8")
        )
        job_id = job_id or f"{paper_id}_demo"
        try:
            self.store.delete_job(job_id)
        except KeyError:
            pass
        self.store.create_job(
            job_id=job_id,
            paper_id=document.paper_id,
            title=document.metadata.title,
            status="document_ready",
            budget_limit_usd=Decimal("4.00") if paper_id == "ppr_dev_003" else Decimal("8.00"),
        )
        target_assets = self.artifacts.job_dir(job_id) / "assets"
        target_assets.mkdir(parents=True, exist_ok=True)
        for source in (annotations / "assets").glob("*"):
            if source.is_file():
                shutil.copy2(source, target_assets / source.name)
        source_pdf = self.project_root / "evaluation" / "papers" / paper_id / "source" / "paper.pdf"
        if source_pdf.is_file():
            shutil.copy2(source_pdf, self.artifacts.job_dir(job_id) / "source.pdf")
            generate_source_previews(document, source_pdf, target_assets)
        self.artifacts.save(job_id, "document_ir", document)
        return self.store.get_job(job_id).as_dict()

    def bootstrap_pdf(
        self,
        pdf_path: Path,
        *,
        paper_id: str,
        job_id: str,
        latex_root: Path | None = None,
        source_url: str | None = None,
    ) -> dict:
        """Create a model-ready job from a local PDF, optionally retaining TeX."""

        try:
            self.store.delete_job(job_id)
        except KeyError:
            pass
        self.store.create_job(
            job_id=job_id,
            paper_id=paper_id,
            title=pdf_path.stem,
            status="document_ready",
            budget_limit_usd=Decimal("8.00"),
        )
        job_dir = self.artifacts.job_dir(job_id)
        shutil.copy2(pdf_path, job_dir / "source.pdf")
        document = PyMuPDFAdapter().extract(pdf_path, paper_id, job_dir)
        if latex_root and latex_root.exists():
            shutil.copytree(latex_root, job_dir / "source_latex", dirs_exist_ok=True)
        if source_url:
            (job_dir / "source_manifest.json").write_text(
                json.dumps({"source_url": source_url, "paper_id": paper_id}, indent=2) + "\n",
                encoding="utf-8",
            )
        generate_source_previews(document, pdf_path, job_dir / "assets")
        self.artifacts.save(job_id, "document_ir", document)
        # PDF filenames are often generic (for example ``paper.pdf`` from an
        # arXiv download). Once the text layer has been extracted, expose the
        # actual paper title in the job record instead of leaking that
        # transport filename to the UI.
        job = self.store.upsert_job(
            job_id=job_id,
            paper_id=paper_id,
            title=document.metadata.title,
            status="document_ready",
            budget_limit_usd=Decimal("8.00"),
        )
        return job.as_dict()

    def bootstrap_arxiv(self, url: str, *, paper_id: str, job_id: str) -> dict:
        cache_dir = self.runtime_root / "arxiv" / paper_id
        manifest = download_arxiv(url, cache_dir)
        result = self.bootstrap_pdf(
            Path(manifest["pdf_path"]),
            paper_id=paper_id,
            job_id=job_id,
            latex_root=Path(manifest["latex_root"]),
            source_url=url,
        )
        result["arxiv"] = manifest
        return result

    def bootstrap_gold_demo(self, paper_id: str, *, job_id: str | None = None) -> dict:
        """Create a poster-ready job from one adjudicated evaluation sample."""

        annotations = self.project_root / "evaluation" / "papers" / paper_id / "annotations"
        document = DocumentIR.model_validate_json((annotations / "document_ir.gold.json").read_text())
        analysis = PaperAnalysis.model_validate_json((annotations / "paper_analysis.gold.json").read_text())
        evidence = EvidenceGraph.model_validate_json((annotations / "evidence_graph.gold.json").read_text())
        job_id = job_id or f"{paper_id}_gold"
        try:
            self.store.delete_job(job_id)
        except KeyError:
            pass
        self.store.create_job(
            job_id=job_id,
            paper_id=paper_id,
            title=analysis.metadata.title,
            status="evidence_ready",
            budget_limit_usd=Decimal("4.00") if paper_id == "ppr_dev_003" else Decimal("8.00"),
        )
        target_assets = self.artifacts.job_dir(job_id) / "assets"
        target_assets.mkdir(parents=True, exist_ok=True)
        for source in (annotations / "assets").glob("*"):
            if source.is_file():
                shutil.copy2(source, target_assets / source.name)
        source_pdf = self.project_root / "evaluation" / "papers" / paper_id / "source" / "paper.pdf"
        if source_pdf.is_file():
            shutil.copy2(source_pdf, self.artifacts.job_dir(job_id) / "source.pdf")
            generate_source_previews(document, source_pdf, target_assets)
        self.artifacts.save(job_id, "document_ir", document)
        self.artifacts.save(job_id, "paper_analysis", analysis)
        self.artifacts.save(job_id, "evidence_graph", evidence)
        plan = build_poster_plan(document, analysis, evidence)
        self.artifacts.save(job_id, "poster_plan", plan)
        review = run_deterministic_review(document, analysis, evidence, plan)
        self.artifacts.save(job_id, "review_result", review)
        validate_artifact_set(document, analysis, evidence, plan, review)
        self.store.update_status(job_id, "poster_ready")
        return self.store.get_job(job_id).as_dict()

    def analyze_with_models(
        self, job_id: str, *, provider_name: str = "anthropic"
    ) -> dict:
        """Run semantic stages with an explicitly selected structured provider."""

        if provider_name == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY must be configured in papercraft/.env "
                "or papercraft/.env.example"
            )
        if provider_name not in {"anthropic", "codex"}:
            raise ValueError(f"unsupported semantic provider: {provider_name}")
        document = self.artifacts.load(job_id, "document_ir")
        assert isinstance(document, DocumentIR)
        ledger = self._load_ledger(job_id)
        existing_call_ids = {record.call_id for record in ledger.records}
        try:
            provider = (
                AnthropicStructuredProvider(ledger)
                if provider_name == "anthropic"
                else CodexExecStructuredProvider(ledger)
            )
            if self.artifacts.has(job_id, "paper_analysis"):
                analysis = self.artifacts.load(job_id, "paper_analysis")
                assert isinstance(analysis, PaperAnalysis)
                validate_paper_analysis(document, analysis)
            else:
                analysis_revision = self._next_model_revision(
                    job_id,
                    ledger,
                    "paper_analysis",
                    f"{document.paper_id}:analysis:logic:",
                )
                analysis = SemanticPaperAnalyzer(provider).analyze(
                    document,
                    asset_root=self.artifacts.job_dir(job_id),
                    artifact_revision=analysis_revision,
                )
                validate_paper_analysis(document, analysis)
                self.artifacts.save(job_id, "paper_analysis", analysis)
                self.store.update_status(job_id, "analysis_ready")
            if self.artifacts.has(job_id, "evidence_graph"):
                evidence = self.artifacts.load(job_id, "evidence_graph")
                assert isinstance(evidence, EvidenceGraph)
            else:
                evidence_revision = self._next_model_revision(
                    job_id,
                    ledger,
                    "evidence_graph",
                    f"{document.paper_id}:evidence:",
                )
                evidence = SemanticEvidenceBuilder(provider).build(
                    document,
                    analysis,
                    artifact_revision=evidence_revision,
                )
                self.artifacts.save(job_id, "evidence_graph", evidence)
                self.store.update_status(job_id, "evidence_ready")
            unresolved = False
            audit_prefix = (
                f"{document.paper_id}:semantic-audit:{analysis.artifact_revision}:"
            )
            audit_sequence = 1
            for record in ledger.records:
                if record.call_id.startswith(audit_prefix):
                    suffix = record.call_id.removeprefix(audit_prefix)
                    if re.fullmatch(r"\d+", suffix):
                        audit_sequence = max(audit_sequence, int(suffix) + 1)
            for audit_round in range(2):
                audit = run_semantic_audit(
                    provider,
                    document,
                    analysis,
                    evidence,
                    round_number=audit_sequence + audit_round,
                )
                audit_path = (
                    self.artifacts.job_dir(job_id)
                    / f"semantic_audit.r{audit_round + 1:02d}.json"
                )
                audit_path.write_text(
                    json.dumps(audit.model_dump(mode="json"), indent=2, ensure_ascii=False)
                    + "\n",
                    encoding="utf-8",
                )
                errors = [item for item in audit.findings if item.severity == "error"]
                if not errors:
                    unresolved = False
                    break
                unresolved = True
                if audit_round == 1:
                    break
                batch = request_semantic_repairs(
                    provider,
                    document,
                    analysis,
                    evidence,
                    errors,
                    round_number=audit_sequence + audit_round,
                )
                if not batch.replacements:
                    break
                repaired_analysis, repaired_evidence = apply_semantic_repairs(
                    analysis, evidence, batch
                )
                validation_plan = build_poster_plan(
                    document, repaired_analysis, repaired_evidence
                )
                validation_review = run_deterministic_review(
                    document,
                    repaired_analysis,
                    repaired_evidence,
                    validation_plan,
                )
                validate_artifact_set(
                    document,
                    repaired_analysis,
                    repaired_evidence,
                    validation_plan,
                    validation_review,
                )
                analysis, evidence = repaired_analysis, repaired_evidence
                self.artifacts.save(job_id, "paper_analysis", analysis)
                self.artifacts.save(job_id, "evidence_graph", evidence)
            if unresolved:
                self.store.update_status(
                    job_id,
                    "review_failed",
                    error="Independent semantic audit still has errors after one targeted repair.",
                )
            else:
                self.store.update_status(job_id, "evidence_ready")
        except BudgetExceededError as exc:
            self.store.update_status(job_id, "budget_paused", error=str(exc))
            raise
        except (MissingCredentialError, ModelUnavailableError) as exc:
            self.store.update_status(job_id, "model_paused", error=str(exc))
            raise
        except Exception as exc:
            self.store.update_status(
                job_id,
                "failed",
                error=(
                    f"{provider_name} analysis failed before a validated artifact "
                    f"was produced: {type(exc).__name__}"
                ),
            )
            raise
        finally:
            for record in ledger.records:
                if record.call_id not in existing_call_ids:
                    self.store.record_usage(job_id, record)
        return self.store.get_job(job_id).as_dict()

    def analyze_with_codex(self, job_id: str) -> dict:
        """Run all semantic stages through the locally authenticated Codex CLI."""

        return self.analyze_with_models(job_id, provider_name="codex")

    def analyze_offline(self, job_id: str) -> dict:
        """Create an extractive, visibly qualified fallback without model calls."""

        document = self.artifacts.load(job_id, "document_ir")
        assert isinstance(document, DocumentIR)
        analysis = reviewed_reference_analysis(document) or HeuristicPaperAnalyzer().analyze(document)
        validate_paper_analysis(document, analysis)
        evidence = OfflineEvidenceBuilder().build(document, analysis)
        self.artifacts.save(job_id, "paper_analysis", analysis)
        self.artifacts.save(job_id, "evidence_graph", evidence)
        self.store.update_status(job_id, "evidence_ready")
        return self.store.get_job(job_id).as_dict()

    def plan(self, job_id: str) -> PosterPlan:
        document, analysis, evidence = self._semantic_artifacts(job_id)
        revision = (
            self.artifacts.load(job_id, "poster_plan").artifact_revision + 1
            if self.artifacts.has(job_id, "poster_plan")
            else 1
        )
        plan = build_poster_plan(
            document, analysis, evidence, artifact_revision=revision
        )
        self.artifacts.save(job_id, "poster_plan", plan)
        self.store.update_status(job_id, "poster_ready")
        return plan

    def narrate_with_model(
        self, job_id: str, *, provider_name: str = "anthropic"
    ) -> NarrativePlan:
        """Generate an optional shadow NarrativePlan without changing job status."""

        if provider_name == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY must be configured in papercraft/.env "
                "or papercraft/.env.example"
            )
        if provider_name not in {"anthropic", "codex"}:
            raise ValueError(f"unsupported narrative provider: {provider_name}")
        document, analysis, evidence = self._semantic_artifacts(job_id)
        ledger = self._load_ledger(job_id)
        existing_call_ids = {record.call_id for record in ledger.records}
        revision = self._next_model_revision(
            job_id,
            ledger,
            "narrative_plan",
            f"{document.paper_id}:narrative:",
        )
        try:
            provider = (
                AnthropicStructuredProvider(ledger)
                if provider_name == "anthropic"
                else CodexExecStructuredProvider(ledger)
            )
            narrative = SemanticNarrativePlanner(provider).plan(
                document,
                analysis,
                evidence,
                artifact_revision=revision,
            )
            self.artifacts.save(job_id, "narrative_plan", narrative)
            self.store.add_event(
                job_id,
                "narrative_plan_ready",
                {"artifact_revision": narrative.artifact_revision},
            )
            return narrative
        except Exception as exc:
            self.store.add_event(
                job_id,
                "narrative_plan_failed",
                {"error_type": type(exc).__name__},
            )
            raise
        finally:
            for record in ledger.records:
                if record.call_id not in existing_call_ids:
                    self.store.record_usage(job_id, record)

    def narrate_with_codex(self, job_id: str) -> NarrativePlan:
        """Generate the NarrativePlan through the locally authenticated Codex CLI."""

        return self.narrate_with_model(job_id, provider_name="codex")

    def direct(self, job_id: str) -> tuple[VisualPlan, PosterPlan]:
        """Apply a constrained visual direction or retain the validated baseline."""

        document, analysis, evidence = self._semantic_artifacts(job_id)
        if not self.artifacts.has(job_id, "narrative_plan"):
            raise RuntimeError("NarrativePlan is required; run the explicit narrate stage first.")
        narrative = self.artifacts.load(job_id, "narrative_plan")
        assert isinstance(narrative, NarrativePlan)

        previous = (
            self.artifacts.load(job_id, "poster_plan")
            if self.artifacts.has(job_id, "poster_plan")
            else None
        )
        if (
            isinstance(previous, PosterPlan)
            and previous.analysis_revision == analysis.artifact_revision
            and previous.evidence_revision == evidence.artifact_revision
        ):
            baseline = previous
            poster_revision = previous.artifact_revision + 1
        else:
            poster_revision = 1
            baseline = build_poster_plan(
                document, analysis, evidence, artifact_revision=poster_revision
            )
        visual_revision = (
            self.artifacts.load(job_id, "visual_plan").artifact_revision + 1
            if self.artifacts.has(job_id, "visual_plan")
            else 1
        )
        result = VisualDirector().direct(
            narrative, baseline, artifact_revision=visual_revision
        )
        candidate = result.poster_plan.model_copy(
            update={"artifact_revision": poster_revision}, deep=True
        )
        candidate = PosterPlan.model_validate(candidate.model_dump(mode="json"))
        review = run_deterministic_review(document, analysis, evidence, candidate)
        errors = [item for item in review.issues if item.severity == "error"]
        if errors:
            visual = result.visual_plan.model_copy(
                update={
                    "status": "fallback",
                    "fallback_reason": "; ".join(item.code for item in errors[:3]),
                }
            )
            candidate = baseline.model_copy(
                update={"artifact_revision": poster_revision}, deep=True
            )
            candidate = PosterPlan.model_validate(candidate.model_dump(mode="json"))
        else:
            visual = result.visual_plan
        self.artifacts.save(job_id, "visual_plan", visual)
        self.artifacts.save(job_id, "poster_plan", candidate)
        self.store.add_event(
            job_id,
            "visual_direction_ready",
            {
                "artifact_revision": visual.artifact_revision,
                "status": visual.status,
                "visual_archetype": visual.visual_archetype,
            },
        )
        self.store.update_status(job_id, "poster_ready")
        return visual, candidate

    def review(self, job_id: str, *, metrics=()) -> ReviewResult:
        document, analysis, evidence = self._semantic_artifacts(job_id)
        plan = self.artifacts.load(job_id, "poster_plan")
        assert isinstance(plan, PosterPlan)
        revision = (
            self.artifacts.load(job_id, "review_result").artifact_revision + 1
            if self.artifacts.has(job_id, "review_result")
            else 1
        )
        review = run_deterministic_review(
            document,
            analysis,
            evidence,
            plan,
            render_metrics=metrics,
            artifact_revision=revision,
        )
        self.artifacts.save(job_id, "review_result", review)
        validate_artifact_set(document, analysis, evidence, plan, review)
        self.store.update_status(
            job_id, "complete" if review.status == "passed" else "review_failed"
        )
        return review

    def export(self, job_id: str, *, max_layout_repairs: int = 3) -> ExportResult:
        if not self.artifacts.has(job_id, "poster_plan"):
            self.plan(job_id)
        if not self.artifacts.has(job_id, "review_result"):
            self.review(job_id)
        output_dir = self.project_root / "output" / job_id
        result: ExportResult | None = None
        for attempt in range(max_layout_repairs + 1):
            plan = self.artifacts.load(job_id, "poster_plan")
            assert isinstance(plan, PosterPlan)
            result = self.exporter.export(
                bundle=self.artifacts.bundle(job_id),
                plan=plan,
                source_assets_dir=self.artifacts.job_dir(job_id) / "assets",
                output_dir=output_dir,
                render_revision=plan.artifact_revision,
            )
            review = self.review(job_id, metrics=result.metrics)
            if review.status == "passed":
                break
            operations = review.repair_batch.operations
            if not operations or attempt == max_layout_repairs:
                break
            try:
                repaired = apply_repair_batch(plan, review.repair_batch)
            except (KeyError, ValueError, RuntimeError):
                break
            self.artifacts.save(job_id, "poster_plan", repaired)
        assert result is not None
        final_review = self.artifacts.load(job_id, "review_result")
        if final_review.status == "passed":
            # The browser render that produced the passing metrics necessarily
            # contained the previous review revision. Re-render once with the
            # newly persisted passing review so screenshots and PDF never show
            # stale unresolved-error badges.
            final_plan = self.artifacts.load(job_id, "poster_plan")
            assert isinstance(final_plan, PosterPlan)
            result = self.exporter.export(
                bundle=self.artifacts.bundle(job_id),
                plan=final_plan,
                source_assets_dir=self.artifacts.job_dir(job_id) / "assets",
                output_dir=output_dir,
                render_revision=final_plan.artifact_revision,
            )
        self.exporter.write_static_bundle(
            bundle=self.artifacts.bundle(job_id),
            source_assets_dir=self.artifacts.job_dir(job_id) / "assets",
            output_dir=output_dir,
        )
        metrics_path = output_dir / "render_metrics.json"
        metrics_path.write_text(
            json.dumps(
                [item.model_dump(mode="json") for item in result.metrics],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if final_review.status != "passed":
            self.store.update_status(
                job_id,
                "review_failed",
                error="Layout repair limit reached; inspect review_result.json.",
            )
        return result

    def _semantic_artifacts(self, job_id: str):
        document = self.artifacts.load(job_id, "document_ir")
        analysis = self.artifacts.load(job_id, "paper_analysis")
        evidence = self.artifacts.load(job_id, "evidence_graph")
        assert isinstance(document, DocumentIR)
        assert isinstance(analysis, PaperAnalysis)
        assert isinstance(evidence, EvidenceGraph)
        return document, analysis, evidence

    def _load_ledger(self, job_id: str) -> BudgetLedger:
        job = self.store.get_job(job_id)
        records = [
            UsageRecord(
                call_id=row["call_id"],
                provider=row["provider"],
                model=row["model"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                cost_usd=Decimal(row["cost_usd"]),
            )
            for row in self.store.usage_rows(job_id)
        ]
        return BudgetLedger(limit_usd=Decimal(job.budget_limit_usd), records=records)

    def _next_model_revision(
        self,
        job_id: str,
        ledger: BudgetLedger,
        artifact_name: str,
        call_prefix: str,
    ) -> int:
        """Choose a fresh revision after either a saved artifact or partial paid run."""

        revision = 1
        if self.artifacts.has(job_id, artifact_name):
            artifact = self.artifacts.load(job_id, artifact_name)
            revision = max(revision, artifact.artifact_revision + 1)
        for record in ledger.records:
            if not record.call_id.startswith(call_prefix):
                continue
            suffix = record.call_id.removeprefix(call_prefix)
            if re.fullmatch(r"\d+", suffix):
                revision = max(revision, int(suffix) + 1)
        return revision
