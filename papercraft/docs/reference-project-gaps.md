# How PaperCraft differs from the reference projects

## Paper2Poster

Observed repository outputs retain the paper's original chapter order, repeat
Abstract/Introduction/Conclusion content, allocate space unevenly, reduce table
text too aggressively, and produce a static PPTX whose conclusions cannot be
traced to evidence.

PaperCraft instead uses a reader path, stable source IDs, Claim–Evidence
assessments, separate Screen and Print plans, visible evidence scope, and a
source drawer. It does not copy Paper2Poster's full pipeline.

## PosterGen

Observed outputs are cleaner but often reserve large low-information areas,
repeat method graphics, keep low-value Related Work, weakly connect experiments
to claims, and rely on occupancy proxies that do not match visual perception.

PaperCraft measures actual browser geometry and also performs visual PDF review.
The AMP A0 design was specifically revised after a nominal occupancy pass still
looked sparse: it now includes a six-dimension sufficiency matrix, original
method/table crops, multiple faithful equations, and experiment-scope notes.

## Shared gap

Both references largely treat formulas as static content, do not judge evidence
sufficiency, and tend to regenerate broadly when something is wrong. PaperCraft
preserves symbols, exposes variables and computation order, limits Claim status
to three explicit values, and patches only named semantic objects or layout
components while verifying untouched hashes.

No reference code or assets have been copied. If low-level licensed material is
later reused, its source, license, and attribution must be recorded here before
merge.
