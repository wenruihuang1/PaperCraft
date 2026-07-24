"""Deterministic visual direction constrained by NarrativePlan and PosterPlan."""

from __future__ import annotations

import re
from dataclasses import dataclass

from papercraft.models import NarrativePlan, PosterPlan, VisualPlan
from papercraft.models.poster_plan import NarrativeRegion
from papercraft.planning.layout_engine import build_component_placements


_ARCHETYPE_VISUAL = {
    "causal_intervention": "cause_intervention_effect",
    "mechanism": "mechanism_explainer",
    "method_pipeline": "pipeline_story",
    "benchmark_comparison": "benchmark_matrix",
    "case_based": "case_gallery",
    "dataset_characterization": "dataset_landscape",
    "theory_derivation": "theory_derivation",
    "decision_loop": "decision_loop",
    "agent_workflow": "agent_workflow",
    "system_architecture": "system_architecture",
    "taxonomy_survey": "taxonomy_map",
    "balanced": "balanced_story",
}

_COMPONENT_PRIORITY = {
    "pipeline_story": ("method_flow", "equation_explorer", "result_chart", "visual_gallery"),
    "cause_intervention_effect": ("method_flow", "visual_gallery", "result_chart", "equation_explorer"),
    "mechanism_explainer": ("method_flow", "visual_gallery", "equation_explorer", "result_chart"),
    "benchmark_matrix": ("result_chart", "visual_gallery", "method_flow", "equation_explorer"),
    "case_gallery": ("visual_gallery", "method_flow", "result_chart", "equation_explorer"),
    "dataset_landscape": ("visual_gallery", "result_chart", "method_flow", "equation_explorer"),
    "theory_derivation": ("equation_explorer", "method_flow", "result_chart", "visual_gallery"),
    "decision_loop": ("method_flow", "result_chart", "equation_explorer", "visual_gallery"),
    "agent_workflow": ("method_flow", "visual_gallery", "result_chart", "equation_explorer"),
    "system_architecture": ("method_flow", "visual_gallery", "result_chart", "equation_explorer"),
    "taxonomy_map": ("visual_gallery", "result_chart", "method_flow", "equation_explorer"),
    "balanced_story": ("method_flow", "equation_explorer", "result_chart", "visual_gallery"),
}

_EYEBROWS = {
    "pipeline_story": ("THE BOTTLENECK", "THE PIPELINE", "THE PAYOFF"),
    "cause_intervention_effect": ("THE CONFOUNDER", "THE INTERVENTION", "THE EFFECT"),
    "mechanism_explainer": ("THE FAILURE MODE", "THE MECHANISM", "THE SELECTIVE FIX"),
    "benchmark_matrix": ("THE SETTING", "THE COMPARISON", "THE RESULT"),
    "case_gallery": ("THE CASE", "THE VISUAL CUE", "THE OUTCOME"),
    "dataset_landscape": ("THE DATA", "THE STRUCTURE", "THE TAKEAWAY"),
    "theory_derivation": ("THE QUESTION", "THE DERIVATION", "THE CONSEQUENCE"),
    "decision_loop": ("THE STATE", "THE DECISION", "THE RETURN"),
    "agent_workflow": ("THE TASK", "THE WORKFLOW", "THE OUTCOME"),
    "system_architecture": ("THE CONSTRAINT", "THE ARCHITECTURE", "THE RESULT"),
    "taxonomy_map": ("THE FIELD", "THE MAP", "THE TAKEAWAY"),
    "balanced_story": ("THE PROBLEM", "THE INSIGHT", "THE TAKEAWAY"),
}


@dataclass(frozen=True)
class VisualDirectionResult:
    visual_plan: VisualPlan
    poster_plan: PosterPlan


class VisualDirector:
    """Select a visual grammar, never arbitrary components or coordinates."""

    def direct(
        self,
        narrative: NarrativePlan,
        baseline: PosterPlan,
        *,
        artifact_revision: int = 1,
    ) -> VisualDirectionResult:
        visual_archetype = _ARCHETYPE_VISUAL[narrative.archetype]
        ordered = _ordered_components(baseline, visual_archetype)
        nodes_by_id = {item.node_id: item for item in narrative.nodes}
        primary = [nodes_by_id[item] for item in narrative.primary_path]
        hero_nodes = _hero_nodes(primary)
        visual = VisualPlan(
            schema_version="1.0.0",
            artifact_revision=artifact_revision,
            paper_id=narrative.paper_id,
            narrative_revision=narrative.artifact_revision,
            baseline_poster_revision=baseline.artifact_revision,
            visual_archetype=visual_archetype,
            component_sequence=[item.component_id for item in ordered],
            primary_node_refs=narrative.primary_path,
            hero_node_refs=[item.node_id for item in hero_nodes],
        )
        directed = _apply_direction(baseline, ordered, primary, visual_archetype)
        return VisualDirectionResult(visual_plan=visual, poster_plan=directed)


def _ordered_components(baseline, visual_archetype):
    priority = {kind: index for index, kind in enumerate(_COMPONENT_PRIORITY[visual_archetype])}
    original = {item.component_id: index for index, item in enumerate(baseline.components)}
    return sorted(
        baseline.components,
        key=lambda item: (priority.get(item.component_type, len(priority)), original[item.component_id]),
    )


def _hero_nodes(primary):
    preferred = [
        item
        for item in primary
        if item.role in {"insight", "intervention", "mechanism", "method"}
    ]
    evidence = next((item for item in primary if item.role == "evidence"), None)
    if evidence is not None and evidence not in preferred:
        preferred.append(evidence)
    return (preferred or primary[1:2] or primary[:1])[:3]


def _apply_direction(baseline, ordered, primary, visual_archetype):
    candidate = baseline.model_copy(deep=True)
    candidate.components = [item.model_copy(deep=True) for item in ordered]
    candidate.reading_path = [item.component_id for item in candidate.components]
    screen, printable = build_component_placements(candidate.components)
    candidate.layout_profiles.screen_16_9.component_layouts = screen
    candidate.layout_profiles.print_a0_landscape.component_layouts = printable
    candidate.narrative_regions = _directed_regions(
        baseline.narrative_regions, primary, visual_archetype
    )
    _direct_component_titles(candidate, primary)
    return PosterPlan.model_validate(candidate.model_dump(mode="json"))


def _directed_regions(baseline_regions, primary, visual_archetype):
    by_role = {item.role: item for item in baseline_regions}
    problem = primary[0]
    motivation = next(
        (item for item in primary if item.role in {"gap", "observation", "claim"}),
        primary[min(1, len(primary) - 1)],
    )
    insight = next(
        (
            item
            for item in primary
            if item.role in {"insight", "intervention", "mechanism", "method"}
        ),
        primary[-1],
    )
    eyebrows = _EYEBROWS[visual_archetype]
    selected = (
        ("problem", problem, eyebrows[0]),
        ("motivation", motivation, eyebrows[1]),
        ("key_insight", insight, eyebrows[2]),
    )
    return [
        NarrativeRegion(
            role=role,
            eyebrow=eyebrow,
            headline=_narrative_headline(node),
            body=_narrative_body(node),
            source_refs=node.source_refs,
            presentation_ref=by_role.get(role).presentation_ref if role in by_role else None,
            text_budget=by_role.get(role).text_budget if role in by_role else None,
        )
        for role, node, eyebrow in selected
    ]


def _direct_component_titles(plan, primary):
    solution = next(
        (
            item
            for item in primary
            if item.role in {"insight", "intervention", "mechanism", "method"}
        ),
        None,
    )
    takeaway = next((item for item in reversed(primary) if item.role == "takeaway"), None)
    for component in plan.components:
        if component.component_type == "method_flow" and solution is not None:
            component.title = _method_section_title(solution.statement)
        elif component.component_type == "result_chart" and takeaway is not None:
            component.title = (
                "What each design choice adds"
                if "ablation" in component.component_id
                else "What the full method achieves"
            )


def _narrative_headline(node) -> str:
    """Make a readable card headline without visibly truncating a claim."""

    statement = node.statement
    if node.role == "problem":
        match = re.search(r"\bbut\s+(.+?)(?:[;.]|$)", statement, flags=re.I)
        if match:
            headline = _brief(match.group(1), 72)
            if headline.lower().startswith("their "):
                headline = headline[6:]
            return _sentence_case(headline)
    if node.role == "gap":
        match = re.search(r"\brequiring\s+(.+?)(?:[;—.]|$)", statement, flags=re.I)
        if match:
            return _sentence_case(f"Taylor pruning requires {match.group(1).strip()}")
    if node.role == "insight" and "entropy" in statement.lower():
        if "label-free" in statement.lower() and "head-free" in statement.lower():
            return "Label-free entropy enables head-free pruning"
        return "Entropy guides adaptive pruning"
    return _sentence_case(_headline_brief(statement, 76))


def _narrative_body(node) -> str:
    statement = node.statement
    if node.role == "problem" and ";" in statement:
        return _sentence_case(_brief(statement.split(";", 1)[1], 132))
    if node.role == "gap" and "—" in statement:
        return _sentence_case(_brief(statement.split("—", 1)[1], 132))
    if node.role == "insight" and "usable both as" in statement.lower():
        return "It supplies both a Taylor scoring criterion and an adaptive stopping signal."
    return _brief(statement, 138)


def _headline_brief(text: str, maximum: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    first_clause = re.split(r"[,;]", normalized, maxsplit=1)[0].strip()
    if 28 <= len(first_clause) <= maximum:
        return first_clause
    result = _brief(normalized, maximum)
    dangling = re.compile(r"\b(?:and|but|or|with|by|to|for|from|exploit|treat|caused)\s*$", re.I)
    while dangling.search(result):
        result = dangling.sub("", result).rstrip(" ,;:")
    return result


def _method_section_title(statement: str) -> str:
    lowered = statement.lower()
    if "entropy" in lowered and "prun" in lowered:
        return "Label-free entropy pruning"
    if "causal" in lowered or "intervention" in lowered:
        return "The intervention pipeline"
    if "mechanism" in lowered:
        return "How the mechanism works"
    return "How the method works"


def _short(text: str, maximum: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= maximum:
        return normalized
    sentence = re.split(r"(?<=[.!?])\s+", normalized)[0]
    if len(sentence) <= maximum:
        return sentence
    shortened = normalized[: maximum - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (shortened or normalized[: maximum - 1]) + "…"


def _brief(text: str, maximum: int) -> str:
    """Trim at a semantic boundary and never expose an ellipsis in the poster."""

    normalized = re.sub(r"\s+", " ", text).strip()
    candidates = [
        item.strip(" ,;:")
        for item in re.split(r"(?<=[.!?;])\s+|\s+[—–-]\s+", normalized)
        if item.strip()
    ]
    for candidate in candidates:
        if len(candidate) <= maximum:
            return candidate
    words: list[str] = []
    for word in normalized.split():
        candidate = " ".join((*words, word))
        if len(candidate) > maximum:
            break
        words.append(word)
    return " ".join(words).rstrip(" ,;:") or normalized[:maximum].rstrip(" ,;:")


def _sentence_case(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text
