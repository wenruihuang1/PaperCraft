"""Small, reviewed offline profiles for papers shipped as visual references.

Profiles are used only when model access is unavailable.  Every statement is
linked to a source reference extracted from the PDF, so the result remains
auditable and is never presented as an LLM semantic review.
"""

from __future__ import annotations

from papercraft.models import DocumentIR, PaperAnalysis
from papercraft.models.paper_analysis import (
    AnalysisMetadata,
    Claim,
    Concept,
    Experiment,
    ExperimentResult,
    InsightNarrative,
    Method,
    MethodStep,
    MotivationNarrative,
    NarrativeFrame,
    ProblemNarrative,
    UnderstandingStep,
)


def reviewed_reference_analysis(document: DocumentIR) -> PaperAnalysis | None:
    if document.metadata.title.startswith("Paper2Poster:"):
        return _paper2poster(document)
    return None


def _paper2poster(document: DocumentIR) -> PaperAnalysis:
    abstract_ref = "src_p001_b0005"
    overview_ref = "src_p002_b0005"
    pipeline_ref = "src_p005_b0023"
    result_ref = "src_p002_b0006"
    judge_ref = "src_p024_b0022"
    quiz_ref = "src_p010_b0001"
    quiz_baseline_ref = "src_p010_b0002"
    efficiency_ref = "src_p009_b0017"
    concepts = [
        Concept(
            concept_id="cpt_problem",
            concept_type="problem",
            statement="Scientific poster generation must compress long, interleaved papers into one coherent visual page.",
            importance="critical",
            source_refs=[abstract_ref],
        ),
        Concept(
            concept_id="cpt_motivation",
            concept_type="motivation",
            statement="Evaluation must measure visual quality, textual coherence, holistic quality, and how well a poster communicates paper knowledge.",
            importance="high",
            source_refs=[abstract_ref],
        ),
        Concept(
            concept_id="cpt_key_insight",
            concept_type="key_insight",
            statement="Use a top-down, visual-in-the-loop pipeline: build an asset library, plan a readable layout, then iteratively render and critique each panel.",
            importance="critical",
            source_refs=[overview_ref, pipeline_ref],
        ),
        Concept(
            concept_id="cpt_conclusion",
            concept_type="conclusion",
            statement="Structured compression and visual feedback let open-source PosterAgent variants compete with costlier agent systems using far fewer tokens.",
            importance="high",
            source_refs=[result_ref, efficiency_ref],
        ),
    ]
    claims = [
        Claim(
            claim_id="clm_pipeline",
            statement="PosterAgent converts a paper into a poster through Parser, Planner, and Painter–Commenter stages with visual feedback.",
            claim_type="main",
            scope="PosterAgent pipeline described in the paper",
            importance="critical",
            source_refs=[overview_ref, pipeline_ref],
        ),
        Claim(
            claim_id="clm_efficiency",
            statement="The reported open-source variants outperform existing GPT-4o-driven multi-agent systems on nearly all metrics while using 87% fewer tokens.",
            claim_type="main",
            scope="Paper2Poster benchmark comparisons reported by the authors",
            qualifiers=["reported benchmark result", "no offline semantic audit"],
            importance="critical",
            source_refs=[result_ref, efficiency_ref],
        ),
    ]
    methods = [
        Method(
            method_id="mth_parser",
            name="Parser: asset library",
            purpose="Extract figures and tables and summarize sections into a structured, layout-ready asset library.",
            inputs=["paper PDF"],
            outputs=["structured text–visual assets"],
            steps=[MethodStep(index=1, description="Parse the PDF and build section-level text and visual assets.", source_refs=[overview_ref, pipeline_ref])],
            claim_refs=["clm_pipeline"],
            source_refs=[overview_ref, pipeline_ref],
        ),
        Method(
            method_id="mth_planner",
            name="Planner: match and layout",
            purpose="Match synopses to visuals and allocate a binary-tree layout that preserves reading order and spatial balance.",
            inputs=["asset library"],
            outputs=["panel layout"],
            steps=[MethodStep(index=1, description="Match text and visuals, size panels by content, and preserve reading order.", source_refs=[overview_ref, pipeline_ref])],
            claim_refs=["clm_pipeline"],
            source_refs=[overview_ref, pipeline_ref],
        ),
        Method(
            method_id="mth_painter_commenter",
            name="Painter–Commenter loop",
            purpose="Render concise panels as executable poster code and use zoomed VLM feedback to correct overflow and alignment.",
            inputs=["panel layout", "matched assets"],
            outputs=["editable poster"],
            steps=[MethodStep(index=1, description="Render, inspect each panel, and iteratively repair visual failures.", source_refs=[overview_ref, pipeline_ref])],
            claim_refs=["clm_pipeline"],
            source_refs=[overview_ref, pipeline_ref],
        ),
    ]
    experiments = [
        Experiment(
            experiment_id="exp_benchmark",
            question="How do PosterAgent outputs compare with other automatic poster systems?",
            setup="Compare oracle, end-to-end, and multi-agent posters with visual, language, VLM-judge, PaperQuiz, and efficiency measures.",
            datasets=["Paper2Poster: 100 paper–author-poster pairs"],
            metrics=["VLM-as-Judge", "PaperQuiz", "token use", "cost"],
            baselines=["4o-Image", "4o-HTML", "OWL", "PPTAgent"],
            results=[
                ExperimentResult(result_id="res_judge", metric="VLM-as-Judge overall", value="4o-Image 2.33 vs PosterAgent-4o 3.72", comparison="PosterAgent-4o vs 4o-Image", source_refs=[judge_ref]),
                ExperimentResult(result_id="res_quiz", metric="PaperQuiz augmented example", value="4o-HTML 116.02 vs PosterAgent 122.67", comparison="PosterAgent vs 4o-HTML", source_refs=[quiz_ref, quiz_baseline_ref]),
                ExperimentResult(result_id="res_cost", metric="Reported cost per poster", value="4o $0.55 vs Qwen $0.0045", comparison="Qwen vs 4o", source_refs=[efficiency_ref]),
            ],
            limitations=["The example PaperQuiz comparison is figure-specific; broader results remain accessible through the linked source."],
            claim_refs=["clm_efficiency"],
            source_refs=[judge_ref, quiz_ref, quiz_baseline_ref, efficiency_ref],
        )
    ]
    return PaperAnalysis(
        schema_version="1.2.0",
        artifact_revision=1,
        paper_id=document.paper_id,
        source_revision=document.artifact_revision,
        metadata=AnalysisMetadata(title=document.metadata.title, authors=document.metadata.authors, language="en"),
        concepts=concepts,
        claims=claims,
        methods=methods,
        experiments=experiments,
        narrative_frame=NarrativeFrame(
            problem=ProblemNarrative(concept_ref="cpt_problem", context=concepts[0].statement, conventional_assumption="A long paper can be summarized directly into a fixed poster template.", failure_mechanism="Long-context text, figures, layout, and reading order must be compressed jointly.", consequence="Direct generation produces overflow, blank regions, or weak communication.", source_refs=[abstract_ref]),
            motivation=MotivationNarrative(concept_ref="cpt_motivation", observation="Poster quality is both visual and informational.", limitation="A single similarity or language metric cannot measure reader comprehension.", design_requirement="Evaluate visual quality, coherence, holistic quality, and communicated knowledge together.", source_refs=[abstract_ref]),
            insight=InsightNarrative(concept_ref="cpt_key_insight", principle="Plan globally and refine visually at panel level.", operationalization="Parser → Planner → Painter–Commenter.", expected_effect="A dense, readable, editable poster with fewer overflow and alignment failures.", source_refs=[overview_ref, pipeline_ref]),
        ),
        understanding_path=[
            UnderstandingStep(step_id="step_problem", role="problem", object_refs=["cpt_problem"], transition="The benchmark makes this compression task measurable."),
            UnderstandingStep(step_id="step_motivation", role="motivation", object_refs=["cpt_motivation"], transition="PosterAgent addresses generation with a staged visual workflow."),
            UnderstandingStep(step_id="step_method", role="method", object_refs=["mth_parser", "mth_planner", "mth_painter_commenter"], transition="The benchmark then measures output quality and efficiency."),
            UnderstandingStep(step_id="step_evidence", role="evidence", object_refs=["exp_benchmark", "res_judge", "res_quiz", "res_cost"], transition="The source-linked results support a qualified conclusion."),
            UnderstandingStep(step_id="step_conclusion", role="conclusion", object_refs=["cpt_conclusion", "clm_efficiency"]),
        ],
        analysis_warnings=["Reviewed offline reference profile; no LLM semantic audit was available."],
    )
