"""Conservative, offline PaperAnalysis baseline.

This module is intentionally a baseline rather than a substitute for semantic
reasoning. It selects source sentences using section and lexical boundaries and
never invents a source reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from papercraft.analysis.base import PaperAnalysisError, PaperAnalyzer
from papercraft.models.document_ir import DocumentIR
from papercraft.models.paper_analysis import (
    AnalysisMetadata,
    Claim,
    Concept,
    Experiment,
    ExperimentResult,
    Method,
    MethodStep,
    PaperAnalysis,
    UnderstandingStep,
)


PROBLEM_TERMS = (
    "suffer",
    "challenge",
    "problem",
    "limitation",
    "bottleneck",
    "cumbersome",
    "do not generalize",
    "however",
    "nevertheless",
)
MOTIVATION_TERMS = (
    "important",
    "common",
    "need",
    "demand",
    "to address",
    "therefore",
    "thus",
    "practical",
)
METHOD_TERMS = (
    "we propose",
    "we introduce",
    "we present",
    "our method",
    "our approach",
    "we employ",
    "we use",
)
STEP_TERMS = (
    "first",
    "second",
    "third",
    "then",
    "afterwards",
    "finally",
    "specifically",
)
CLAIM_TERMS = (
    "experimental results",
    "performance gain",
    "consistent performance",
    "results show",
    "demonstrate",
    "outperform",
    "yields",
    "achieve",
    "improve",
)
EXPERIMENT_TERMS = (
    "we evaluate",
    "we compare",
    "we compared",
    "we conduct",
    "experiment",
    "evaluation",
    "performance comparison",
)


@dataclass(frozen=True)
class _Sentence:
    text: str
    source_ref: str
    section_title: str


class HeuristicPaperAnalyzer(PaperAnalyzer):
    """Produce a reproducible, source-extractive analysis baseline without LLMs."""

    def analyze(self, document_ir: DocumentIR) -> PaperAnalysis:
        sentences = _source_sentences(document_ir)
        if not sentences:
            raise PaperAnalysisError("DocumentIR has no source-addressable prose")

        abstract = [item for item in sentences if "abstract" in item.section_title.lower()]
        method_pool = [item for item in sentences if _is_method_section(item.section_title)]
        experiment_pool = [
            item for item in sentences if _is_experiment_section(item.section_title)
        ]
        conclusion_pool = [
            item for item in sentences if "conclusion" in item.section_title.lower()
        ]
        front_pool = abstract or sentences[:20]

        problem = _select(front_pool, PROBLEM_TERMS) or front_pool[0]
        motivation = _select(
            [item for item in front_pool if item.text != problem.text],
            MOTIVATION_TERMS,
        ) or _next_distinct(front_pool, problem)

        method_candidates = method_pool or front_pool
        purpose = _select(method_candidates + front_pool, METHOD_TERMS)
        if purpose is None:
            purpose = method_candidates[0]
        step_candidates = [
            item
            for item in method_candidates + front_pool
            if _is_step_sentence(item.text)
        ]
        if not step_candidates:
            step_candidates = method_candidates[:3]
        steps = _deduplicate_sentences(step_candidates)[:4]
        if not steps:
            steps = [purpose]

        claim_pool = abstract + conclusion_pool + experiment_pool
        claim_sentence = _select_best(claim_pool, CLAIM_TERMS)
        if claim_sentence is None:
            claim_sentence = (conclusion_pool or experiment_pool or front_pool)[-1]

        setup = _select_best(experiment_pool, EXPERIMENT_TERMS)
        if setup is None:
            setup = (experiment_pool or [claim_sentence])[0]

        method_source_refs = _unique([purpose.source_ref] + [item.source_ref for item in steps])
        experiment_source_refs = _unique([setup.source_ref, claim_sentence.source_ref])
        method_name = _method_name(method_pool, purpose)

        analysis = PaperAnalysis(
            schema_version="1.0.0",
            artifact_revision=1,
            paper_id=document_ir.paper_id,
            source_revision=document_ir.artifact_revision,
            metadata=AnalysisMetadata(
                title=document_ir.metadata.title,
                authors=document_ir.metadata.authors,
                language="en",
            ),
            concepts=[
                Concept(
                    concept_id="cpt_problem",
                    concept_type="problem",
                    statement=problem.text,
                    importance="critical",
                    source_refs=[problem.source_ref],
                ),
                Concept(
                    concept_id="cpt_motivation",
                    concept_type="motivation",
                    statement=motivation.text,
                    importance="high",
                    source_refs=[motivation.source_ref],
                ),
            ],
            claims=[
                Claim(
                    claim_id="clm_main_result",
                    statement=claim_sentence.text,
                    claim_type="main",
                    scope=f"reported in {claim_sentence.section_title or 'the paper'}",
                    qualifiers=_qualifiers(claim_sentence.text),
                    importance="critical",
                    source_refs=[claim_sentence.source_ref],
                )
            ],
            methods=[
                Method(
                    method_id="mth_primary",
                    name=method_name,
                    purpose=purpose.text,
                    inputs=[],
                    outputs=[],
                    steps=[
                        MethodStep(
                            index=index,
                            description=item.text,
                            source_refs=[item.source_ref],
                        )
                        for index, item in enumerate(steps, start=1)
                    ],
                    assumptions=[],
                    equation_refs=[],
                    claim_refs=["clm_main_result"],
                    source_refs=method_source_refs,
                )
            ],
            equations=[],
            experiments=[
                Experiment(
                    experiment_id="exp_primary",
                    question="Does the reported evaluation support the main result claim?",
                    setup=setup.text,
                    datasets=[],
                    metrics=[],
                    baselines=[],
                    results=[
                        ExperimentResult(
                            result_id="res_main",
                            metric="reported outcome",
                            value=claim_sentence.text,
                            comparison=None,
                            source_refs=[claim_sentence.source_ref],
                        )
                    ],
                    limitations=[
                        "Datasets, metrics, and baselines require semantic verification beyond this rule-based baseline."
                    ],
                    claim_refs=["clm_main_result"],
                    source_refs=experiment_source_refs,
                )
            ],
            understanding_path=[
                UnderstandingStep(
                    step_id="step_problem",
                    role="problem",
                    object_refs=["cpt_problem"],
                    transition="The paper's stated motivation frames why the problem matters.",
                ),
                UnderstandingStep(
                    step_id="step_motivation",
                    role="motivation",
                    object_refs=["cpt_motivation"],
                    transition="The primary method is introduced in response.",
                ),
                UnderstandingStep(
                    step_id="step_method",
                    role="method",
                    object_refs=["mth_primary"],
                    transition="The evaluation is used to test the reported claim.",
                ),
                UnderstandingStep(
                    step_id="step_evidence",
                    role="evidence",
                    object_refs=["clm_main_result", "exp_primary", "res_main"],
                    transition=None,
                ),
            ],
            analysis_warnings=[
                "Generated by heuristic_v1 without an LLM; semantic boundaries require human review.",
                "Only extractive source sentences are used; no equation semantics are inferred.",
            ],
        )
        return analysis


def _source_sentences(document_ir: DocumentIR) -> list[_Sentence]:
    section_titles = {item.section_id: item.title for item in document_ir.sections}
    ref_by_block = {
        ref.locator.block_id: ref.source_ref_id
        for ref in document_ir.source_refs
        if ref.source_type == "text_span" and ref.locator.block_id is not None
    }
    result: list[_Sentence] = []
    for block in sorted(document_ir.blocks, key=lambda item: item.reading_order):
        if block.block_type in {"title", "heading"} or block.block_id not in ref_by_block:
            continue
        section_title = section_titles.get(block.section_id, "")
        for sentence in _split_sentences(block.text):
            if len(sentence) < 30:
                continue
            result.append(
                _Sentence(
                    text=sentence,
                    source_ref=ref_by_block[block.block_id],
                    section_title=section_title,
                )
            )
    return result


def _split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", normalized)
        if part.strip()
    ]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _is_step_sentence(text: str) -> bool:
    lowered = text.lower().lstrip()
    sequencing = "|".join(re.escape(term) for term in STEP_TERMS)
    return bool(
        re.match(rf"^(?:{sequencing})\b", lowered)
        or re.match(rf"^we\s+(?:{sequencing})\b", lowered)
    )


def _select(items: list[_Sentence], terms: Iterable[str]) -> _Sentence | None:
    return next((item for item in items if _contains_any(item.text, terms)), None)


def _select_best(items: list[_Sentence], terms: Iterable[str]) -> _Sentence | None:
    weighted_terms = list(terms)
    scored = [
        (
            sum(
                len(weighted_terms) - index
                for index, term in enumerate(weighted_terms)
                if term in item.text.lower()
            ),
            item,
        )
        for item in items
    ]
    score, selected = max(scored, key=lambda pair: pair[0], default=(0, None))
    return selected if score > 0 else None


def _next_distinct(items: list[_Sentence], selected: _Sentence) -> _Sentence:
    return next((item for item in items if item.text != selected.text), selected)


def _deduplicate_sentences(items: list[_Sentence]) -> list[_Sentence]:
    result: list[_Sentence] = []
    seen: set[str] = set()
    for item in items:
        if item.text in seen:
            continue
        seen.add(item.text)
        result.append(item)
    return result


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _is_method_section(title: str) -> bool:
    lowered = title.lower()
    return "method" in lowered or "approach" in lowered


def _is_experiment_section(title: str) -> bool:
    lowered = title.lower()
    return "experiment" in lowered or "result" in lowered or "evaluation" in lowered


def _method_name(method_pool: list[_Sentence], purpose: _Sentence) -> str:
    if method_pool and method_pool[0].section_title:
        return method_pool[0].section_title
    return purpose.section_title or "Primary proposed method"


def _qualifiers(statement: str) -> list[str]:
    lowered = statement.lower()
    candidates = (
        "roughly",
        "near lossless",
        "on unseen domains",
        "in the evaluated scenarios",
        "without finetuning",
    )
    return [item for item in candidates if item in lowered]
