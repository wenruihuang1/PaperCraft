# PaperCraft deterministic iteration contract

## Required inputs

- Five public artifacts with compatible `paper_id` and upstream revisions.
- Browser-generated `render_metrics.json`.
- Current `review_result.json` with structured issue targets.

## Required browser checks

| Surface | Required assertions |
|---|---|
| Screen 16:9 | occupancy 78–88%, body ≥18px, no overlap/crop/overflow; Method has a primary overview visual using about 24–42% of its usable visual area |
| Print A0 | occupancy 82–92%, body ≥24pt, one exact 1189×841mm page |
| Method Inspector | image/reconstruction ≥45% width, tabs and source link work |
| Equation Inspector | grouped formulas compile; fallback crops remain available |
| Source Inspector | one large selected visual plus aligned thumbnails; no duplicated visual; tables are not flat text; page/bbox visible |
| Offline HTML | `file://` shows Problem region without network or backend |

## Allowed targeted operations

- `resize_component`
- `move_component`
- `adjust_typography` without crossing profile minimums
- `collapse_secondary`
- `adjust_semantic_crop`
- source-presentation role or fallback correction

## Invariants

- Stable IDs never change during layout repair.
- DocumentIR geometry is immutable.
- Unaffected component content and placement hashes remain unchanged.
- Evidence status can limit wording but cannot be changed by a layout loop.
- Three failed layout rounds produce a failure report, not a completed job.
