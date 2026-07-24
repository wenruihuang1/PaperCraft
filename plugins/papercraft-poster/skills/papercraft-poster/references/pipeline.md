# PaperCraft pipeline

Run the checked-in PaperCraft engine from the repository root. The plugin helper
scripts locate that root automatically; set `PAPERCRAFT_PROJECT_ROOT` only when
the plugin is installed from a different checkout location.

The Codex-only path is:

1. extract and validate the paper into a DocumentIR;
2. use the local Codex account for semantic analysis and narrative planning;
3. direct the visual structure, export interactive HTML, Screen 16:9 PNG, and
   A0 PDF/preview;
4. review the rendered artifacts and retain validated revisions.

Do not substitute legacy API-backed `papercraft analyze` or `papercraft narrate`
for the Codex-only stages.
