"""Content-driven poster layouts shared by baseline and directed plans.

The grid is intentionally small and deterministic: models choose the story,
while this module gives the visually dominant component enough room to be
read.  Unlike the old count-only templates, component demand now affects the
layout and method/framework visuals become a true hero when they carry the
largest amount of information.
"""

from __future__ import annotations

from collections.abc import Sequence

from papercraft.models.poster_plan import ComponentPlacement, PosterComponent


_TYPE_DEMAND = {
    "method_flow": 9.0,
    "visual_gallery": 6.5,
    "result_chart": 6.0,
    "equation_explorer": 5.5,
    "claim_evidence_chain": 4.5,
}


def component_demand(component: PosterComponent) -> float:
    """Estimate visible information demand without relying on text pixels."""

    score = _TYPE_DEMAND[component.component_type]
    score += min(4.0, len(component.asset_refs) * 1.4)
    score += min(2.0, len(component.details) * 0.25)
    if component.component_type == "method_flow":
        score += min(5.0, len(component.steps) * 1.1)
    elif component.component_type == "equation_explorer":
        score += min(5.0, len(component.equation_refs) * 0.65)
    elif component.component_type == "result_chart":
        score += min(4.0, len(component.result_refs) * 0.8)
    elif component.component_type == "visual_gallery":
        score += min(4.0, len(component.presentation_refs) * 0.9)
    else:
        score += min(3.0, len(component.claim_refs) * 0.7)
    return score


def order_for_layout(components: Sequence[PosterComponent]) -> list[PosterComponent]:
    """Put the highest-demand component first while keeping ties stable."""

    if not components:
        return []
    indexed = list(enumerate(components))
    hero_index, _hero = max(indexed, key=lambda pair: (component_demand(pair[1]), -pair[0]))
    return [components[hero_index], *components[:hero_index], *components[hero_index + 1 :]]


def build_component_placements(
    components: Sequence[PosterComponent],
) -> tuple[list[ComponentPlacement], list[ComponentPlacement]]:
    """Create a dense asymmetric mosaic for Screen and A0.

    The first component is the hero.  Callers should use ``order_for_layout``
    (or an archetype-specific sequence) before this function.
    """

    count = len(components)
    if count < 1 or count > 5:
        raise ValueError("PaperCraft currently supports one to five poster components")

    screen_specs = _four_component_specs(components, printable=False) if count == 4 else _screen_specs(count)
    print_specs = _four_component_specs(components, printable=True) if count == 4 else _print_specs(count)
    return (
        _placements(components, screen_specs),
        _placements(components, print_specs),
    )


def _screen_specs(count: int) -> list[tuple[int, int, int, int, float, float]]:
    # column_start, column_span, row_start, row_span, minimum_height, preferred_height
    return {
        1: [(1, 12, 1, 10, 650, 760)],
        2: [(1, 8, 1, 10, 650, 760), (9, 4, 1, 10, 650, 760)],
        3: [(1, 8, 1, 10, 650, 760), (9, 4, 1, 5, 310, 370), (9, 4, 6, 5, 310, 370)],
        4: [(1, 7, 1, 10, 650, 760), (8, 5, 1, 3, 185, 235), (8, 5, 4, 4, 245, 305), (8, 5, 8, 3, 185, 235)],
        # The evidence-analysis card needs one extra support row to keep its
        # logic, claim/evidence, experiment, and conclusion blocks visible.
        # The gallery remains in the left bottom strip, so the asymmetric
        # columns still fit the 16:9 canvas without overlap.
        5: [(1, 7, 1, 8, 520, 620), (8, 5, 1, 3, 185, 235), (8, 5, 4, 2, 120, 165), (8, 5, 6, 5, 300, 365), (1, 7, 9, 2, 120, 160)],
    }[count]


def _print_specs(count: int) -> list[tuple[int, int, int, int, float, float]]:
    return {
        1: [(1, 12, 1, 10, 500, 610)],
        2: [(1, 7, 1, 10, 500, 610), (8, 5, 1, 10, 500, 610)],
        3: [(1, 7, 1, 10, 500, 610), (8, 5, 1, 5, 240, 300), (8, 5, 6, 5, 240, 300)],
        4: [(1, 7, 1, 10, 500, 610), (8, 5, 1, 3, 145, 190), (8, 5, 4, 5, 240, 300), (8, 5, 9, 2, 100, 140)],
        5: [(1, 7, 1, 8, 390, 480), (8, 5, 1, 4, 190, 245), (8, 5, 5, 1, 80, 110), (8, 5, 6, 5, 240, 300), (1, 7, 9, 2, 100, 140)],
    }[count]


def _four_component_specs(
    components: Sequence[PosterComponent], *, printable: bool
) -> list[tuple[int, int, int, int, float, float]]:
    """Stack supporting panels by content family, not by a fixed slot name."""

    supports = list(components[1:])
    priority = {
        "result_chart": 4,
        "claim_evidence_chain": 3,
        "visual_gallery": 2,
        "equation_explorer": 2,
        "method_flow": 0,
    }
    large = max(
        range(len(supports)),
        key=lambda index: (priority[supports[index].component_type], component_demand(supports[index])),
    )
    if printable:
        # A0 can devote two rows to the compact formula summary and give both
        # quantitative results and visual evidence four rows.  This avoids a
        # large, mostly empty equation card while preserving the ten-row grid.
        second = max(
            (index for index in range(len(supports)) if index != large),
            key=lambda index: (priority[supports[index].component_type], component_demand(supports[index])),
        )
        spans = [2, 2, 2]
        spans[large] = 4
        spans[second] = 4
    else:
        spans = [2, 2, 2]
        spans[large] = 4
        spans[second] = 4
    hero_heights = (500, 610) if printable else (650, 760)
    row = 1
    specs = [(1, 7, 1, 10, *hero_heights)]
    for span in spans:
        if printable:
            heights = (190, 245) if span == 4 else (145, 190)
        else:
            heights = (245, 305) if span == 4 else (185, 235)
        specs.append((8, 5, row, span, *heights))
        row += span
    return specs


def _placements(
    components: Sequence[PosterComponent],
    specs: Sequence[tuple[int, int, int, int, float, float]],
) -> list[ComponentPlacement]:
    return [
        ComponentPlacement(
            component_id=component.component_id,
            order=index,
            column_start=spec[0],
            column_span=spec[1],
            row_start=spec[2],
            row_span=spec[3],
            minimum_height=spec[4],
            preferred_height=spec[5],
        )
        for index, (component, spec) in enumerate(zip(components, specs, strict=True), start=1)
    ]
