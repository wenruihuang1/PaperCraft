# PaperCraft documentation

This top-level directory is the project-facing documentation entry point. The
engine keeps its detailed technical documents beside the code so its paths stay
stable for the local runtime.

## Start here

- [Project homepage](../README.md) — what PaperCraft does and the recommended
  Codex workflow.
- [Engine setup](../papercraft/README.md) — local Python and web setup, direct
  model-provider mode, tests, and operational limits.
- [Codex plugin guide](../plugins/papercraft-poster/README.md) — installation,
  environment checks, terminal use, and repair/resume commands.

## Technical references

- [Architecture and artifact flow](../papercraft/docs/architecture.md)
- [DocumentIR 1.0](../papercraft/docs/document_ir-1.0.md)
- [PaperAnalysis scope and boundaries](../papercraft/docs/paper-analysis-boundaries.md)
- [Reference-project gaps](../papercraft/docs/reference-project-gaps.md)
- [Evaluation protocol](../papercraft/evaluation/README.md)

The boundary is deliberate: project navigation lives here, while engine-level
documentation remains under `papercraft/docs/` so code and its contracts evolve
together.
