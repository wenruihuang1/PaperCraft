---
name: papercraft-poster
description: Turn English text-based research-paper PDFs into evidence-grounded, reviewed interactive and print posters with the local PaperCraft engine and the user's authenticated Codex account. Use for PaperCraft paper-to-poster runs, local PDF or arXiv poster generation, Codex-only semantic analysis without model API keys, rerunning failed PaperCraft stages, inspecting generated artifacts, or validating Screen 16:9 and A0 outputs.
---

# PaperCraft Poster

Use the checked-in PaperCraft engine as the only execution implementation. Do
not recreate its parsing, schemas, planning, rendering, review, or repair logic
inside the conversation.

## Run a paper

1. Read `references/pipeline.md` before the first run in a task.
2. Run `scripts/check_environment.py --auth-probe` before a new multi-paper
   batch. The probe consumes one small Codex turn but catches revoked account
   tokens before expensive semantic stages start.
3. Resolve the input PDF to an absolute path.
4. Run `scripts/run_pipeline.py <absolute-pdf-path>`.
5. Inspect the reported job status and output paths.
6. Open the Screen PNG and Print preview and check hierarchy, clipping,
   authored ellipses/line clamps, internal blank area, text density, visual
   balance, formula-to-panel fit, framework legibility, and source-grounding
   indicators.
7. Report the generated interactive HTML, Screen PNG, Print PNG, and A0 PDF.

The runner uses `papercraft codex-run`. Semantic stages execute through local
`codex exec --output-schema` with saved Codex account authentication. They do
not use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or another model API key.

## Resume a failed run

Preserve validated artifacts. Do not restart from the PDF unless ingestion is
the failed stage.

- Resume semantic analysis with `papercraft codex-analyze <job_id>`.
- If Codex reports a hard account quota and a provisional poster is still
  required, run `papercraft offline-analyze <job_id>`, then `papercraft plan`
  and `papercraft export`. Clearly label this as an extractive offline fallback,
  not a Codex semantic review.
- Resume narrative planning with `papercraft codex-narrate <job_id>`.
- Rebuild an existing baseline with the current layout engine using
  `papercraft plan <job_id>`.
- Resume constrained visual direction with `papercraft direct <job_id>`.
- Resume rendering and layout repair with `papercraft export <job_id>`.

Read `references/artifacts.md` when diagnosing a stage or explaining outputs.

## Guardrails

- Accept only supported English text PDFs; surface capability rejection instead
  of attempting OCR.
- Never invent source references, results, equations, affiliations, or venues.
- Keep Codex execution account-authenticated and remove model API keys from
  child-process environments.
- Treat `runtime/` and `output/` as generated data, not source code.
- Do not delete prior artifact revisions during repair.
- Do not call the legacy `papercraft analyze` or `papercraft narrate` commands
  for a Codex-only run; those use the configured Anthropic API provider.
- Do not report an offline fallback as Codex-generated or semantically audited.

## Finish

Provide one compact result per paper:

- job ID and final status;
- narrative and visual archetypes;
- output file links;
- semantic, evidence, layout, or aesthetic warnings;
- whether any model API key was used (expected: no).
