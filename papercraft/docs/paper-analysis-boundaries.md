# PaperAnalysis extraction boundaries

Stage C requires five semantic object classes. Every object and nested method
step/result must cite at least one `source_ref_id` from the input DocumentIR.

## Problem

The limitation, failure mode, unmet need, or research question addressed by the
paper. General background is not a problem unless the paper explicitly frames it
as a gap.

## Motivation

Why solving the problem matters or why existing approaches are inadequate. It
must be represented separately from the proposed solution.

## Method

The authors' proposed intervention or pipeline. A method contains its purpose,
ordered steps, inputs/outputs when verified, assumptions, and links to relevant
claims. Related work and experimental procedure are excluded.

## Claim

An author assertion that can in principle be supported or challenged. Claims
retain scope and qualifiers such as dataset, domain, comparison target, or
approximation. A result number without an asserted implication is not itself a
claim.

## Experiment

An evaluation unit consisting of a question, setup, datasets, metrics,
baselines, and one or more results. Unknown fields remain empty and are surfaced
as warnings instead of being guessed.

## Baseline status

`HeuristicPaperAnalyzer` is an offline, extractive baseline. It selects sentences
using section names and conservative lexical rules. Its output is suitable for
testing IDs, revisions, and provenance, but is not semantic gold and must be
reviewed before evidence sufficiency assessment.
