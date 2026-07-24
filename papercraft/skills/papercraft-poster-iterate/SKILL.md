---
name: papercraft-poster-iterate
description: Inspect, diagnose, and minimally repair PaperCraft Screen 16:9, Print A0, Method Inspector, equation, source, and offline HTML rendering. Use when a PaperCraft export has blank areas, weak visual hierarchy, clipping, damaged equations, undersized figures, a white file:// page, or a review_result layout issue. Preserve grounded content and unaffected component hashes; do not call an LLM API for layout work.
---

# PaperCraft Poster Iterate

Iterate on a versioned PaperCraft poster using browser measurements and the smallest deterministic patch that fixes the observed issue.

## Preconditions

- Work from a job containing all five validated artifacts.
- Read `references/review-contract.md` before changing layout or renderer behavior.
- Treat `document_ir.json` as frozen source geometry. Never modify its bbox values to make a crop look better.
- Do not call OpenAI, Claude, or a local model for layout review or repair.

## Workflow

1. Export the current job without altering semantic artifacts.
2. Inspect these artifacts at full size:
   - `screen-16x9.png`
   - `print-a0-preview.png`
   - `method-inspector.png`
   - `source-inspector.png`
   - `equation-inspector.png`
   - the A0 PDF rendered to an image
3. Open `interactive/index.html` through `file://` in Chrome. Confirm that the Problem region is visible, local fonts and images load, KaTeX renders, and the offline failure panel stays hidden.
4. Read `review_result.json` and `render_metrics.json`. Map every issue to one region, component, presentation, or profile.
5. Select one minimal repair in this order:
   - reallocate the affected grid span;
   - enlarge or adjust only the affected semantic crop;
   - shorten non-core explanatory copy without changing its claim;
   - fold secondary material into an inspector;
   - adjust a local renderer style.
6. Never regenerate the full PosterPlan for a local defect. Apply a targeted patch, increment the affected artifact revision, and preserve the content hash of unaffected components.
7. Re-export and repeat measurements. Stop after three layout rounds.
8. Mark the result complete only if all six reviewers contain no open error and the offline smoke check passes. Otherwise preserve the last valid export and report unresolved issues.

## Visual priorities

- Preserve the reader path: Problem → Motivation → Insight → Detailed Method → Core Equations → Results.
- Keep Problem, Motivation, and Insight near 28% of the main visual area; Method and Equations near 52%; Results and compact Evidence near 20%, each within five percentage points.
- Do not shrink Screen body text below 18px or Print body text below 24pt.
- Prefer visual structure, equations, and reconstructed charts over extra prose.
- Require the Screen 16:9 Method region to use the highest-ranked method overview figure. Give that primary visual roughly 24–42% of the Method component's usable visual area; do not leave the lower half of a text-only method card blank.
- Give the Method Inspector original or reconstructed imagery at least 45% of common desktop width.
- Present one selected source visual at a time in the Source Inspector, with aligned thumbnail navigation and a separate scrolling evidence column. Never repeat the selected figure inside its source excerpt or lay full-size figures in a horizontal strip.
- Keep claim assessment as a compact quality guardrail, not a headline section.

## Formula and source rules

- Compile reviewed LaTeX with KaTeX.
- If compilation fails or the reviewed notation does not match the source crop, show the original formula crop. Never show damaged PDF extraction text.
- Show table evidence as a reconstructed chart or a semantic crop. Never render a flattened table quote.
- Show ordinary paragraph excerpts only after removing line-break hyphenation and normalizing whitespace.
- Keep page and bbox provenance visible in the Source Inspector.
- Preserve the full semantic figure in inspectors with `object-fit: contain`. Crop only the Screen method preview, using the figure region rather than its printed caption; keep the caption as separate UI text.

## Output report

Report the affected region, issue code, applied operation, before/after metric, unchanged component hashes, offline result, and remaining warnings. Do not imply success when the repair limit was reached.
