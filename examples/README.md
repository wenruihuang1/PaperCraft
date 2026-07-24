# PaperCraft examples

## Turn a local PDF into a reviewed poster

After completing the root [quick start](../README.md#quick-start-with-codex),
open a new Codex task in this repository and use:

```text
Use $papercraft-poster to turn /absolute/path/to/paper.pdf into a reviewed poster.
```

Expected output for a successful run:

```text
papercraft/output/<job_id>/
├── interactive/index.html
├── screen-16x9.png
├── print-a0-preview.png
├── method-inspector.png
├── equation-inspector.png
└── render_metrics.json
```

The A0 PDF is written to `papercraft/output/pdf/`.

## Resume a partially completed job

Run these from `papercraft/` when the job ID is known:

```bash
.venv/bin/papercraft codex-analyze <job_id>
.venv/bin/papercraft codex-narrate <job_id>
.venv/bin/papercraft plan <job_id>
.venv/bin/papercraft direct <job_id>
.venv/bin/papercraft export <job_id>
```

Use `codex-analyze` only when semantic analysis needs to be created or retried;
do not restart ingestion after downstream stages already have validated
artifacts.

## Use the deterministic demo without model calls

```bash
cd papercraft
.venv/bin/papercraft demo
```

This uses the bundled AMP gold artifacts and produces the same output classes
locally. See the [engine README](../papercraft/README.md) for the full command
reference.
