# Evaluation and annotation workspace

Development deliberately reserves only two real English text PDFs:

```text
evaluation/papers/<paper_id>/
├── metadata.json
├── source/paper.pdf
└── annotations/
    ├── capability_report.json
    ├── document_ir.gold.json
    ├── document_ir.audit.json
    ├── paper_analysis.baseline.json
    ├── paper_analysis.baseline.audit.json
    └── assets/*.png
```

The first paper, `ppr_dev_001` (Adaptive MLP Pruning), additionally contains:

- `paper_analysis.gold.json`;
- `evidence_graph.gold.json`;
- `poster_expectations.json`;
- `annotation_audit.json`.

The audit records confidence, inclusion/exclusion decisions, rejected
overstatements, and source-paper inconsistencies. In particular, the AMP paper's
prose reports two numerical improvements that conflict with its own tables; the
gold artifacts preserve the table-grounded interpretation and the Reviewer keeps
both conflicts as warnings.

Users do not type JSON. The local application presents normal review controls;
accepted changes are validated and written as new artifact revisions.

The second medical paper remains a generalization slot with reviewed DocumentIR
and deterministic baseline. It must not inherit AMP-specific manual layout
parameters. Formal 10–15-paper expansion, repeated runs, and Paper2Poster /
PosterGen baselines remain deferred until live model execution is stable.

Future paper admission requires an open English text PDF, 8–16 preferred pages,
clear method logic, at least two useful figures, two experiment groups, and one
display equation. Add one paper at a time only after the previous paper passes
semantic, source, and render review.
