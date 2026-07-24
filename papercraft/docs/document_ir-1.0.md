# DocumentIR 1.0 contract

`DocumentIR` version `1.0.0` is the frozen input boundary for PaperCraft's
paper-analysis stage.

## Stability rules

- `schema_version` must be exactly `1.0.0`.
- Existing field names, meanings, ID formats, and required fields are stable.
- `artifact_revision` tracks regenerated content; it does not change the schema.
- Additive or incompatible contract work requires an explicit later schema
  version and a migration path. It must not silently alter version 1.0.
- Analysis code consumes only public `DocumentIR` fields and resolves evidence
  through `source_ref_id`.

## Source-grounding guarantee

Every text block, equation candidate, and asset can be located by page and
bounding box. A semantic analysis object must cite at least one existing
`source_ref_id`; it may not introduce text or geometry references that are absent
from the input `DocumentIR`.

## Deliberate limitations

- English PDFs with a usable text layer only.
- No OCR or LaTeX-source input.
- `pdf_text` equations preserve extracted text and geometry but do not promise
  canonical LaTeX or visual symbol order.
