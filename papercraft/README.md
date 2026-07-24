# PaperCraft

PaperCraft is a local, evidence-first research-poster application. It turns an
English text PDF into source-addressable intermediate data, a reader-oriented
paper analysis, a Claim–Evidence graph, optional scientific NarrativePlan and
VisualPlan artifacts, and deterministic interactive Screen and Print posters.

The current deep sample is **Adaptive MLP Pruning for Large Vision
Transformers**. Its gold analysis was produced and audited in-repository; users
do not edit JSON by hand.

## What works now

- explicit rejection of scanned, textless, encrypted, malformed, and
  predominantly non-English PDFs;
- frozen `DocumentIR 1.0` with pages, blocks, reading order, bounding boxes,
  source ranges, display equations, figures, tables, captions, and image crops;
- five required contracts plus optional NarrativePlan and VisualPlan contracts, all with
  checked-in JSON Schemas;
- cross-file IDs, revisions, source references, evidence links, component links,
  layout bounds, and collision validation;
- reviewed AMP gold analysis and evidence graph, including two source-paper
  numerical inconsistencies that remain visible as warnings;
- five controlled component families: `method_flow`, `equation_explorer`,
  `claim_evidence_chain`, `result_chart`, and `visual_gallery`;
- independent Screen 16:9 and Print A0 layouts with content-demand scoring,
  asymmetric Hero/supporting mosaics, and framework-first figure sizing;
- interactive source drawer, explanations, original/reconstruction switching,
  profile switching, and secondary-content folding;
- browser-level occupancy, visual ratio, reading order, minimum font, spacing,
  clipping, authored truncation, component utilization, internal blank area,
  visual balance, visible-formula density, collision, and canvas checks;
- offline static HTML, a 1920×1080 preview, and a one-page A0 PDF;
- OpenAI analysis/repair and Claude independent-review adapters, mockable in
  tests and never invoked implicitly;
- persistent SQLite job, artifact revision, status, review, and API-cost state.

The MVP intentionally excludes OCR, scanned PDFs, LaTeX input, PPTX export, and
non-English papers.

## Quick start — no API calls

```bash
cd /Users/RexRyder/PycharmProjects/PaperCraft/papercraft
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
npm install --prefix web
.venv/bin/papercraft demo
```

The demo writes:

- `output/amp_demo/interactive/index.html` — offline interactive poster;
- `output/amp_demo/screen-16x9.png` — Screen preview;
- `output/amp_demo/print-a0-preview.png` — PDF-rasterized Print preview;
- `output/pdf/ppr_dev_001-a0.pdf` — exact one-page A0 landscape PDF;
- `output/amp_demo/render_metrics.json` — measured layout evidence.

Run the local studio:

```bash
.venv/bin/papercraft serve
```

Then open `http://127.0.0.1:8000`. Uploading a PDF performs only capability
detection and deterministic DocumentIR extraction. Paid semantic analysis is a
separate explicit action.

## Optional model stage

### Codex Skill — no model API key

The repository includes a Codex Skill at
`../.agents/skills/papercraft-poster`. Start a new Codex task in the repository
and invoke it with:

```text
Use $papercraft-poster to turn papers/my-paper.pdf into a reviewed poster.
```

The Skill calls the checked-in PaperCraft engine and uses locally authenticated
`codex exec --output-schema` turns for semantic stages. It removes common model
API-key variables from child processes. Check the environment and remotely
validate the saved Codex token before a multi-paper batch:

```bash
python ../.agents/skills/papercraft-poster/scripts/check_environment.py --auth-probe
```

The direct command behind the Skill is:

```bash
python ../.agents/skills/papercraft-poster/scripts/run_pipeline.py /absolute/path/paper.pdf
```

Codex account usage is recorded with token activity and zero API-dollar cost in
the PaperCraft ledger. It still consumes Codex account quota and requires a
valid Codex CLI login.

### Direct model API path

Put local credentials in `.env` (the CLI also accepts `.env.example` for this
local setup). Never commit either file or paste keys into chat.

```dotenv
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

Then run a prepared job explicitly:

```bash
.venv/bin/papercraft analyze <job_id>
.venv/bin/papercraft narrate <job_id>
.venv/bin/papercraft direct <job_id>
```

The semantic analysis provider uses `claude-sonnet-4-6` structured outputs for
the analysis passes, evidence construction, and at most two object-local
repairs. The model can be overridden with `PAPERCRAFT_CLAUDE_MODEL`. The
independent reviewer uses the same configured Claude model with a forced strict
tool schema. `narrate` makes one additional structured call over PaperAnalysis,
EvidenceGraph, and only their cited source excerpts. It writes an optional
shadow NarrativePlan and does not change PosterPlan or the job's current status.
`direct` is local and deterministic: it maps the narrative archetype and
primary path to a constrained VisualPlan, then only reorders existing components
within the existing Screen and Print grid slots. A deterministic review failure
persists a `fallback` VisualPlan and retains the baseline PosterPlan.
Every call reserves its worst-case cost before execution. The per-job hard cap
is USD 8.00; insufficient balance produces `budget_paused` instead of a model
downgrade. Only validated structured results, model name, tokens, and cost are
stored—never raw model responses or keys.

## Tests

```bash
.venv/bin/pytest
npm test --prefix web
npm run build --prefix web
```

The normal test suite is offline and uses fixed provider responses. Regenerate
the public JSON Schemas with:

```bash
.venv/bin/python -m papercraft.schema_export
```

See [architecture](docs/architecture.md), [annotation and evaluation](evaluation/README.md),
the [Narrative Planner v1 audit](evaluation/narrative_planner.v1.audit.json), and
[reference-project gaps](docs/reference-project-gaps.md) for details.

## Honest current boundary

The deterministic AMP path is stable and fully exported. The Claude-backed
Narrative Planner has been shadow-run on all three gold papers with validated
artifacts and a checked-in audit. The deterministic Visual Director now lets
that narrative reorder existing poster components without changing grid
geometry, but it does not yet introduce archetype-specific components or new
rendering primitives. Full live PDF-to-analysis-to-evidence execution and
formal 10–15-paper evaluation remain incomplete, as do repeated
Paper2Poster/PosterGen baselines and multi-format renderers beyond the current
poster output.
