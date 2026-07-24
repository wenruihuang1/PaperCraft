import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import katex from "katex";
import { BlockMath } from "react-katex";
import { Bundle, PosterComponent, SourceRef } from "./types";

type ViewerState = { title: string; refs: string[]; presentationIds?: string[] } | null;
type Profile = "screen_16_9" | "print_a0_landscape";

export function Poster({ bundle }: { bundle: Bundle }) {
  const requestedProfile = new URLSearchParams(location.search).get("profile");
  const initialProfile: Profile = requestedProfile === "print_a0_landscape" ? requestedProfile : bundle.profile || "screen_16_9";
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [viewer, setViewer] = useState<ViewerState>(null);
  const [layoutExplanationOpen, setLayoutExplanationOpen] = useState(new URLSearchParams(location.search).get("explain") === "1");
  const theme = bundle.poster_plan.theme;
  const refs = useMemo(() => new Map<string, SourceRef>(bundle.document_ir.source_refs.map((item: SourceRef) => [item.source_ref_id, item])), [bundle]);
  const authors = bundle.paper_analysis.metadata.authors.join(" · ");
  const layoutOnlyCodes = new Set(["VISUAL_RATIO_OUT_OF_RANGE", "FONT_BELOW_MINIMUM", "GAP_BELOW_MINIMUM"]);
  const reviewErrors = bundle.review_result.issues.filter((item: any) => item.severity === "error" && item.status === "open" && !layoutOnlyCodes.has(item.code)).length;
  const style = {
    "--pc-bg": theme.background, "--pc-surface": theme.surface, "--pc-fg": theme.foreground,
    "--pc-muted": theme.muted, "--pc-accent": theme.accent, "--pc-accent-2": theme.accent_secondary,
    "--pc-success": theme.success, "--pc-warning": theme.warning, "--pc-danger": theme.danger,
  } as React.CSSProperties;

  const mode = bundle.poster_plan.narrative_mode || "balanced";
  return <div className={`poster-stage profile-${profile} mode-${mode}`} style={style} data-profile={profile} data-narrative-mode={mode}>
    <header className="poster-toolbar no-print">
      <div><strong>PaperCraft</strong><span>reader-path poster · source grounded</span></div>
      <div className="toolbar-actions">
        <button onClick={() => setLayoutExplanationOpen(true)}>Explain layout</button>
        <button className={profile === "screen_16_9" ? "active" : ""} onClick={() => setProfile("screen_16_9")}>Screen 16:9</button>
        <button className={profile === "print_a0_landscape" ? "active" : ""} onClick={() => setProfile("print_a0_landscape")}>Print A0</button>
      </div>
    </header>
    <article className="poster-canvas" id="poster-canvas">
      <header className="paper-heading">
        <div className={`heading-copy ${bundle.paper_analysis.metadata.title.length > 62 ? "heading-long" : ""}`}>
          <p className="eyebrow">PROBLEM → MOTIVATION → INSIGHT → METHOD → EQUATIONS → RESULTS</p>
          <h1>{bundle.paper_analysis.metadata.title}</h1>
          <p className="authors">{authors}</p>
        </div>
        <div className="poster-status"><span>REVIEWED TRACE</span><strong>{reviewErrors === 0 ? "Every visible statement is grounded" : `${reviewErrors} unresolved errors`}</strong><small>{bundle.poster_plan.paper_id} · analysis r{bundle.paper_analysis.artifact_revision}</small></div>
      </header>
      <NarrativePath bundle={bundle} onSource={setViewer} />
      <section className="poster-grid">
        {bundle.poster_plan.components.map((component: PosterComponent) => <ComponentCard key={component.component_id} component={component} bundle={bundle} profile={profile} onSource={setViewer} />)}
      </section>
      <footer className="poster-footer"><span>Source trace remains available from each visual and result.</span><span>DocumentIR 1.0 · PosterPlan {bundle.poster_plan.schema_version}</span></footer>
    </article>
    {viewer && <SourceViewer viewer={viewer} refs={refs} bundle={bundle} onClose={() => setViewer(null)} />}
    {layoutExplanationOpen && <LayoutExplanation bundle={bundle} profile={profile} onClose={() => setLayoutExplanationOpen(false)} />}
  </div>;
}

function NarrativePath({ bundle, onSource }: { bundle: Bundle; onSource: (state: ViewerState) => void }) {
  return <section className="narrative-path" aria-label="Reader path">
    {(bundle.poster_plan.narrative_regions || []).map((region: any, index: number) => <article className={`narrative-region narrative-${region.role}`} data-narrative-role={region.role} key={region.role}>
      <div className="narrative-top"><span>{region.eyebrow}</span>{index < 2 && <b>→</b>}</div>
      <h2>{region.headline}</h2><p>{region.body}</p>
      <button className="source-link no-print" onClick={() => onSource({ title: region.headline, refs: region.source_refs, presentationIds: region.presentation_ref ? [region.presentation_ref] : [] })}>{region.presentation_ref ? "Open visual explanation" : "Read grounded source"} ↗</button>
    </article>)}
  </section>;
}

function ComponentCard({ component, bundle, profile, onSource }: { component: PosterComponent; bundle: Bundle; profile: Profile; onSource: (state: ViewerState) => void }) {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const placement = bundle.poster_plan.layout_profiles[profile].component_layouts.find((item: any) => item.component_id === component.component_id);
  if (!placement) return null;
  const isHero = placement.column_span >= 7 && placement.row_span >= 7;
  const gridStyle = { gridColumn: `${placement.column_start} / span ${placement.column_span}`, gridRow: `${placement.row_start} / span ${placement.row_span}` };
  return <section className={`poster-component type-${component.component_type} ${isHero ? "component-hero" : "component-supporting"}`} data-component-id={component.component_id} data-column-span={placement.column_span} data-row-span={placement.row_span} style={gridStyle}>
    <div className="component-kicker"><span>{component.component_type.replaceAll("_", " ")}</span><span>{component.source_refs.length} grounded sources</span></div>
    <h2>{component.title}</h2><p className="component-summary">{component.summary}</p>
    <div className="component-visual">
      {component.component_type === "method_flow" && <MethodFlow component={component} bundle={bundle} profile={profile} isHero={isHero} />}
      {component.component_type === "equation_explorer" && <EquationExplorer component={component} bundle={bundle} isHero={isHero} />}
      {component.component_type === "claim_evidence_chain" && <ClaimChain component={component} bundle={bundle} profile={profile} onSource={onSource} />}
      {component.component_type === "result_chart" && <ResultChart component={component} bundle={bundle} profile={profile} isHero={isHero} />}
      {component.component_type === "visual_gallery" && <VisualGallery component={component} bundle={bundle} onSource={onSource} />}
    </div>
    <div className="component-actions no-print">
      {(component.component_type === "method_flow" || component.component_type === "equation_explorer" || component.component_type === "result_chart") && <button onClick={() => setInspectorOpen(true)}>{component.component_type === "method_flow" ? "Open Method Inspector" : component.component_type === "equation_explorer" ? "Explore all equations" : "Inspect benchmark"}</button>}
      <button onClick={() => onSource({ title: component.title, refs: component.source_refs })}>View sources</button>
    </div>
    {inspectorOpen && createPortal(component.component_type === "method_flow" ? <MethodInspector component={component} bundle={bundle} onClose={() => setInspectorOpen(false)} onSource={onSource} /> : component.component_type === "equation_explorer" ? <EquationInspector component={component} bundle={bundle} onClose={() => setInspectorOpen(false)} /> : <ResultInspector component={component} bundle={bundle} onClose={() => setInspectorOpen(false)} />, document.body)}
  </section>;
}

function MethodFlow({ component, bundle, profile, isHero }: { component: PosterComponent; bundle: Bundle; profile: Profile; isHero: boolean }) {
  const primaryAsset = component.asset_refs[0] ? bundle.document_ir.assets.find((item: any) => item.asset_id === component.asset_refs[0]) : null;
  const secondaryAsset = component.asset_refs[1] ? bundle.document_ir.assets.find((item: any) => item.asset_id === component.asset_refs[1]) : null;
  const primaryBounds = primaryAsset?.bbox;
  const primaryAspect = primaryBounds && primaryBounds.y1 > primaryBounds.y0
    ? (primaryBounds.x1 - primaryBounds.x0) / (primaryBounds.y1 - primaryBounds.y0)
    : 2.4;
  const secondaryBounds = secondaryAsset?.bbox;
  const secondaryAspect = secondaryBounds && secondaryBounds.y1 > secondaryBounds.y0
    ? (secondaryBounds.x1 - secondaryBounds.x0) / (secondaryBounds.y1 - secondaryBounds.y0)
    : 2.4;
  const layoutStyle = {
    "--method-aspect": String(Math.max(.8, Math.min(8, primaryAspect))),
    "--method-secondary-aspect": String(Math.max(.8, Math.min(8, secondaryAspect))),
  } as React.CSSProperties;
  return <div className={`method-main-layout ${primaryAsset ? "has-primary-visual" : ""} ${isHero ? "method-hero-layout" : "method-compact-layout"}`} data-method-profile={profile} style={layoutStyle}>
    <div className="method-flow">{component.steps?.map((step, index) => <div className="flow-step" data-step-index={index + 1} key={step.label}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{step.label.replace(/^\d+\.\s*/, "")}</strong><p>{step.description}</p></div>{index < (component.steps?.length || 0) - 1 && <b aria-hidden="true">→</b>}</div>)}</div>
    {primaryAsset && <figure className="method-main-figure poster-visual-only" data-primary-method-visual="true"><img src={assetForId(bundle, primaryAsset.asset_id)} alt={primaryAsset.caption || "Original method overview"} /></figure>}
    {secondaryAsset && <figure className="method-secondary-figure poster-visual-only" data-secondary-method-visual="true"><img src={assetForId(bundle, secondaryAsset.asset_id)} alt={secondaryAsset.caption || "Supporting method evidence"} /></figure>}
  </div>;
}

function EquationExplorer({ component, bundle, isHero }: { component: PosterComponent; bundle: Bundle; isHero: boolean }) {
  const groups = equationGroups(component).slice(0, isHero ? 4 : 2);
  return <div className={`equation-chain ${isHero ? "equation-chain-spacious" : ""}`}>{groups.map((group: any, index: number) => { const equations = group.equation_refs.slice(0, isHero ? 2 : 1).map((id: string) => equationById(bundle, id)).filter(Boolean); return <article key={group.group_id}><span>{String(index + 1).padStart(2, "0")}</span><div className="equation-stage-content"><div className="equation-stage-copy"><strong>{group.title}</strong><p>{group.explanation}</p></div><div className="equation-formula-set">{equations.map((eq: any) => <SafeFormula key={eq.equation_id} equation={eq} bundle={bundle} compact />)}</div></div></article>; })}</div>;
}

function equationGroups(component: PosterComponent) {
  if (component.equation_groups?.length) return component.equation_groups;
  if (!component.equation_refs?.length) return [];
  return [{ group_id: "eqg_all", title: component.title, explanation: component.summary, equation_refs: component.equation_refs }];
}

function SafeFormula({ equation, bundle, compact = false }: { equation: any; bundle: Bundle; compact?: boolean }) {
  const presentation = (bundle.poster_plan.source_presentations || []).find((item: any) => item.equation_ref === equation.equation_id);
  const fallback = presentation ? assetPath(bundle, presentation.image_path) : "";
  let valid = true;
  try { katex.renderToString(equation.latex_original, { throwOnError: true }); } catch { valid = false; }
  return <div className={`safe-formula ${compact ? "formula-compact" : ""}`}>{valid ? <BlockMath math={equation.latex_original} /> : fallback ? <img src={fallback} alt={`Original Equation ${equation.label}`} /> : <span>Equation {equation.label} — open source crop</span>}</div>;
}

function ClaimChain({ component, bundle, profile, onSource }: { component: PosterComponent; bundle: Bundle; profile: Profile; onSource: (state: ViewerState) => void }) {
  const claims = component.claim_refs.map((id) => bundle.paper_analysis.claims.find((item: any) => item.claim_id === id)).filter(Boolean);
  const assessments = new Map(bundle.evidence_graph.claim_assessments.map((item: any) => [item.claim_id, item]));
  const experiments = (component.experiment_refs || []).map((id: string) => bundle.paper_analysis.experiments.find((item: any) => item.experiment_id === id)).filter(Boolean);
  const details = component.details || [];
  const visibleClaims = claims.slice(0, profile === "print_a0_landscape" ? 3 : 2);
  const visibleExperiments = experiments.slice(0, profile === "print_a0_landscape" ? 3 : 2);
  return <div className="analysis-card">
    <section className="analysis-box analysis-logic">
      <span className="analysis-label">LOGIC CHECK</span>
      <p>{details[0] || component.summary}</p>
    </section>
    <div className="analysis-grid">
      <section className="analysis-box analysis-claims">
        <span className="analysis-label">CLAIMS → EVIDENCE</span>
        <div className="claim-chain compact-evidence">{visibleClaims.map((claim: any) => {
          const assessment: any = assessments.get(claim.claim_id);
          const status = assessment?.status || "insufficient_evidence";
          const claimLabel = `${claim.claim_type === "main" ? "Main" : "Supporting"} claim · ${claim.scope || "Scope reported in source"}`;
          return <button className="claim-row" key={claim.claim_id} onClick={() => onSource({ title: claim.statement, refs: claim.source_refs })}>
            <span className={`assessment ${status}`}>{status.replaceAll("_", " ")}</span>
            <span><strong>{claimLabel}</strong><small>{assessment?.limitations?.[0] || "Evidence details available in the source inspector."}</small></span><b>↗</b>
          </button>;
        })}</div>
      </section>
      <section className="analysis-box analysis-experiments">
        <span className="analysis-label">EXPERIMENTS & LIMITS</span>
        <div className="experiment-checks">{visibleExperiments.map((experiment: any, index: number) => <button className="experiment-check" key={experiment.experiment_id} onClick={() => onSource({ title: experiment.question, refs: experiment.source_refs })}>
          <strong>Experiment {index + 1} · {[...(experiment.datasets || []), ...(experiment.metrics || [])].slice(0, 3).join(" · ") || "Scope not reported"}</strong>
          <small>{experiment.limitations?.[0] || "No limitation reported; inspect the linked source for setup and results."}</small>
        </button>)}</div>
      </section>
    </div>
    <section className="analysis-conclusion">
      <span className="analysis-label">CONTRIBUTION · CONCLUSION</span>
      <p>{details[1] || "Contributions are not explicitly reported."}</p>
      <p>{details[2] || "Conclusion is not explicitly reported."}</p>
    </section>
  </div>;
}

function ResultChart({ component, bundle, profile, isHero = false }: { component: PosterComponent; bundle?: Bundle; profile?: Profile; isHero?: boolean }) {
  const data = component.chart_data || [];
  const groups = [...new Set(data.map((item) => item.label))];
  const sourceAsset = bundle && component.asset_refs[0] ? bundle.document_ir.assets.find((item: any) => item.asset_id === component.asset_refs[0]) : null;
  const showSource = Boolean(sourceAsset && (isHero || profile === "print_a0_landscape") && groups.length <= 3);
  return <div className={`result-main-layout ${showSource ? "has-result-source" : ""}`}><div className="result-comparison">{groups.map((group) => { const rows = data.filter((item) => item.label === group); const base = rows[0]; const proposed = rows[rows.length - 1]; const delta = proposed && base ? proposed.value - base.value : 0; const deltaLabel = `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}`; return <article key={group}><span>{group}</span><div><small>{base?.series}</small><strong>{base?.display_value}</strong></div><b>→</b><div className="result-proposed"><small>{proposed?.series}</small><strong>{proposed?.display_value}</strong></div><em>{deltaLabel}</em></article>; })}</div>{showSource && sourceAsset && bundle && <figure className="result-source-asset poster-visual-only"><img src={assetForId(bundle, sourceAsset.asset_id)} alt={sourceAsset.caption} /></figure>}</div>;
}

function VisualGallery({ component, bundle, onSource }: { component: PosterComponent; bundle: Bundle; onSource: (state: ViewerState) => void }) {
  const presentations = (component.presentation_refs || []).map((id) => presentationById(bundle, id)).filter(Boolean);
  return <div className="visual-gallery">{presentations.map((presentation: any) => <button className="gallery-item" key={presentation.presentation_id} aria-label={`Open source: ${presentation.title}`} onClick={() => onSource({ title: presentation.title, refs: [presentation.source_ref_id], presentationIds: [presentation.presentation_id] })}><PresentationImage presentation={presentation} bundle={bundle} compact visualOnly /></button>)}</div>;
}

function MethodInspector({ component, bundle, onClose, onSource }: { component: PosterComponent; bundle: Bundle; onClose: () => void; onSource: (state: ViewerState) => void }) {
  const panels = component.inspector_panels || [];
  const [activeId, setActiveId] = useState(panels[0]?.panel_id);
  const [view, setView] = useState<"reconstruction" | "original">("reconstruction");
  const panel = panels.find((item: any) => item.panel_id === activeId) || panels[0];
  if (!panel) return null;
  const method = bundle.paper_analysis.methods.find((item: any) => item.method_id === panel.method_ref);
  const equations = panel.equation_refs.map((id: string) => equationById(bundle, id)).filter(Boolean);
  const presentations = panel.presentation_refs.map((id: string) => presentationById(bundle, id)).filter(Boolean);
  const preferred = presentations.find((item: any) => item.role === (panel.method_ref === "mth_saam" ? "mechanism" : "method_overview")) || presentations[0];
  const experiment = panel.experiment_refs.map((id: string) => bundle.paper_analysis.experiments.find((item: any) => item.experiment_id === id)).find(Boolean);
  return <div className="inspector-backdrop no-print" role="dialog" aria-modal="true"><section className="method-inspector">
    <header><div><span>METHOD INSPECTOR</span><h2>{panel.title}</h2></div><button onClick={onClose}>×</button></header>
    <nav>{panels.map((item: any, i: number) => <button className={item.panel_id === panel.panel_id ? "active" : ""} key={item.panel_id} onClick={() => setActiveId(item.panel_id)}>{String(i + 1).padStart(2, "0")} {item.title}</button>)}</nav>
    <div className="inspector-layout">
      <div className="inspector-visual">
        <div className="view-toggle"><button className={view === "reconstruction" ? "active" : ""} onClick={() => setView("reconstruction")}>Reconstructed flow</button><button className={view === "original" ? "active" : ""} onClick={() => setView("original")}>Original figure</button></div>
        {view === "original" && preferred ? <PresentationImage presentation={preferred} bundle={bundle} /> : <ReconstructedMethod panel={panel} method={method} />}
        <div className="inspector-gallery" aria-label="Related paper visuals">
          {presentations.filter((item: any) => item.presentation_id !== preferred?.presentation_id).slice(0, 3).map((item: any) => <PresentationImage key={item.presentation_id} presentation={item} bundle={bundle} compact />)}
        </div>
      </div>
      <div className="inspector-explanation"><section><span>WHY THIS MODULE EXISTS</span><p>{panel.why_needed}</p></section><div className="io-grid"><section><span>INPUT</span>{panel.inputs.map((item: string) => <p key={item}>{item}</p>)}</section><section><span>OUTPUT</span>{panel.outputs.map((item: string) => <p key={item}>{item}</p>)}</section></div>
        <section className="inspector-equations"><span>RELATED EQUATIONS</span>{equations.slice(0, panel.method_ref === "mth_saam" ? 4 : 2).map((eq: any) => <div key={eq.equation_id}><b>Eq. {eq.label}</b><SafeFormula equation={eq} bundle={bundle} compact /></div>)}</section>
        {experiment && <section className="ablation-evidence"><span>DESIGN EVIDENCE</span><strong>{experiment.question}</strong><p>{experiment.results?.[0]?.value}</p></section>}
        <button className="source-button" onClick={() => onSource({ title: panel.title, refs: panel.source_refs, presentationIds: panel.presentation_refs })}>Open original text, figures, and ablations ↗</button>
      </div>
    </div>
  </section></div>;
}

function ReconstructedMethod({ panel, method }: { panel: any; method: any }) {
  const steps = method?.steps || [panel.why_needed];
  return <div className="reconstructed-method"><div className="recon-input">{panel.inputs.map((x: string) => <span key={x}>{x}</span>)}</div><b>→</b><div className="recon-process"><strong>{panel.title}</strong>{steps.slice(0, 5).map((step: any, i: number) => { const text = typeof step === "string" ? step : step.description; return <p key={`${i}-${text}`}><span>{i + 1}</span>{text}</p>; })}</div><b>→</b><div className="recon-output">{panel.outputs.map((x: string) => <span key={x}>{x}</span>)}</div></div>;
}

function EquationInspector({ component, bundle, onClose }: { component: PosterComponent; bundle: Bundle; onClose: () => void }) {
  const groups = equationGroups(component);
  const [groupId, setGroupId] = useState((groups.find((g: any) => g.group_id === "eqg_stability") || groups[0])?.group_id);
  const group = groups.find((item: any) => item.group_id === groupId) || groups[0];
  return <div className="inspector-backdrop no-print" role="dialog" aria-modal="true"><section className="equation-inspector method-inspector"><header><div><span>CORE EQUATION SYSTEM</span><h2>{component.title}</h2></div><button onClick={onClose}>×</button></header><nav>{groups.map((item: any) => <button className={item.group_id === groupId ? "active" : ""} key={item.group_id} onClick={() => setGroupId(item.group_id)}>{item.title}</button>)}</nav><div className="equation-inspector-body"><div className="equation-rationale"><span>COMPUTATION STAGE</span><h3>{group.title}</h3><p>{group.explanation}</p></div><div className="equation-sheet">{group.equation_refs.map((id: string) => { const eq = equationById(bundle, id); if (!eq) return null; return <article key={id}><div><span>EQ. {eq.label}</span><strong>{eq.semantic_role.replaceAll("_", " ")}</strong></div><SafeFormula equation={eq} bundle={bundle} /><p>{eq.computation_steps?.join(" → ")}</p><div className="equation-variables">{eq.variables?.slice(0, 4).map((v: any) => <span key={v.symbol}><b>{v.symbol}</b> {v.meaning}</span>)}</div></article>; })}</div></div></section></div>;
}

function ResultInspector({ component, bundle, onClose }: { component: PosterComponent; bundle: Bundle; onClose: () => void }) {
  const presentations = (bundle.poster_plan.source_presentations || []).filter((item: any) => component.asset_refs.includes(item.asset_ref));
  const experiments = (component.experiment_refs || []).map((id: string) => bundle.paper_analysis.experiments.find((item: any) => item.experiment_id === id)).filter(Boolean);
  return <div className="inspector-backdrop no-print" role="dialog" aria-modal="true"><section className="method-inspector result-inspector"><header><div><span>RESULT INSPECTOR</span><h2>{component.title}</h2></div><button onClick={onClose}>×</button></header><div className="result-inspector-grid"><div><ResultChart component={component} bundle={bundle} />{experiments.map((exp: any) => <section key={exp.experiment_id}><span>EVALUATION SCOPE</span><p>{exp.datasets.join(" · ")} · {exp.metrics.join(" · ")}</p>{exp.limitations?.map((x: string) => <small key={x}>{x}</small>)}</section>)}</div><div>{presentations.map((p: any) => <PresentationImage presentation={p} bundle={bundle} key={p.presentation_id} />)}</div></div></section></div>;
}

function SourceViewer({ viewer, refs, bundle, onClose }: { viewer: ViewerState; refs: Map<string, SourceRef>; bundle: Bundle; onClose: () => void }) {
  if (!viewer) return null;
  const explicit = (viewer.presentationIds || []).map((id) => presentationById(bundle, id)).filter(Boolean);
  const inferred = viewer.refs.map((id) => (bundle.poster_plan.source_presentations || []).find((item: any) => item.source_ref_id === id)).filter(Boolean);
  const presentations = [...new Map([...explicit, ...inferred].map((item: any) => [item.presentation_id, item])).values()];
  const [selectedId, setSelectedId] = useState((presentations[0] as any)?.presentation_id);
  const selected: any = presentations.find((item: any) => item.presentation_id === selectedId) || presentations[0];
  const visualSourceIds = new Set(presentations.map((item: any) => item.source_ref_id).filter(Boolean));
  return createPortal(<div className="inspector-backdrop no-print"><aside className="source-viewer" role="dialog" aria-modal="true"><header><div><span>SOURCE INSPECTOR</span><h2>{viewer.title}</h2></div><button aria-label="Close Source Inspector" onClick={onClose}>×</button></header><div className={`source-viewer-body ${presentations.length ? "has-media" : "no-media"}`}>
    {selected && <section className="source-gallery" aria-label="Source visuals"><div className="source-primary"><PresentationImage presentation={selected} bundle={bundle} /></div>{presentations.length > 1 && <nav className="source-thumbnails" aria-label="Choose source visual">{presentations.slice(0, 6).map((item: any) => <button className={item.presentation_id === selected.presentation_id ? "active" : ""} key={item.presentation_id} onClick={() => setSelectedId(item.presentation_id)}><SourceThumbnail presentation={item} bundle={bundle} /><span><small>{item.role.replaceAll("_", " ")} · page {item.page}</small><b>{item.title}</b></span></button>)}</nav>}</section>}
    <section className="source-evidence"><div className="source-evidence-heading"><span>GROUNDED EXCERPTS</span><small>{viewer.refs.length} linked source{viewer.refs.length === 1 ? "" : "s"}</small></div><div className="source-list">{viewer.refs.map((id) => refs.get(id)).filter(Boolean).map((ref) => <SourceExcerpt key={ref!.source_ref_id} sourceRef={ref!} bundle={bundle} suppressVisual={visualSourceIds.has(ref!.source_ref_id)} />)}</div></section>
  </div></aside></div>, document.body);
}

function SourceExcerpt({ sourceRef, bundle, suppressVisual = false }: { sourceRef: SourceRef; bundle: Bundle; suppressVisual?: boolean }) {
  const presentation = (bundle.poster_plan.source_presentations || []).find((item: any) => item.source_ref_id === sourceRef.source_ref_id);
  const visualType = sourceRef.source_type === "equation" || presentation?.display_kind === "reconstructed_chart" || presentation?.asset_ref;
  return <article><div><span>PAGE {sourceRef.locator.page}</span><code>{sourceRef.source_ref_id}</code></div>{visualType && presentation && !suppressVisual ? <PresentationImage presentation={presentation} bundle={bundle} compact /> : visualType && suppressVisual ? <p className="source-visual-note">The visual source is shown at full size in the visual inspector.</p> : <blockquote>{cleanQuote(sourceRef.quote)}</blockquote>}<small>Original location · bbox {sourceRef.locator.bbox ? Object.values(sourceRef.locator.bbox).map((value) => Number(value).toFixed(1)).join(" · ") : "full page"}</small></article>;
}

function SourceThumbnail({ presentation, bundle }: { presentation: any; bundle: Bundle }) {
  const path = presentation.image_path ? assetPath(bundle, presentation.image_path) : presentation.asset_ref ? assetForId(bundle, presentation.asset_ref) : "";
  return path ? <img src={path} alt="" /> : <span className="source-thumb-placeholder">{presentation.equation_ref ? "EQ" : "SOURCE"}</span>;
}

function PresentationImage({ presentation, bundle, compact = false, visualOnly = false }: { presentation: any; bundle: Bundle; compact?: boolean; visualOnly?: boolean }) {
  const path = presentation.image_path ? assetPath(bundle, presentation.image_path) : presentation.asset_ref ? assetForId(bundle, presentation.asset_ref) : "";
  const equation = presentation.equation_ref ? equationById(bundle, presentation.equation_ref) : null;
  return <figure className={`presentation-image ${compact ? "compact" : ""} ${visualOnly ? "poster-visual-only" : ""}`}>{equation && presentation.display_kind === "reconstructed_equation" ? <><SafeFormula equation={equation} bundle={bundle} /><details><summary>Compare with original PDF crop</summary><img src={path} alt={`${presentation.title} original crop`} /></details></> : <img src={path} alt={presentation.title} />}{!visualOnly && <figcaption><span>{presentation.role.replaceAll("_", " ")} · page {presentation.page}</span>{presentation.title}</figcaption>}</figure>;
}

function LayoutExplanation({ bundle, profile, onClose }: { bundle: Bundle; profile: Profile; onClose: () => void }) {
  const placements = bundle.poster_plan.layout_profiles[profile].component_layouts;
  const components = bundle.poster_plan.components.map((component: PosterComponent) => ({
    component,
    placement: placements.find((item: any) => item.component_id === component.component_id),
    demand: componentDemand(component),
  })).filter((item: any) => item.placement);
  const canvas = profile === "screen_16_9" ? "1920 × 1080 px (16:9)" : "1189 × 841 mm (A0 landscape)";
  return <div className="inspector-backdrop no-print layout-explanation-backdrop" role="dialog" aria-modal="true" aria-label="Layout explanation">
    <section className="layout-explanation">
      <header><div><span>DETERMINISTIC TRACE</span><h2>Why this poster has this shape</h2></div><button aria-label="Close layout explanation" onClick={onClose}>×</button></header>
      <div className="layout-explanation-body">
        <article><span>01 · CANVAS</span><strong>{canvas}</strong><p>The output profile fixes the final canvas. AI does not change its aspect ratio.</p></article>
        <article><span>02 · READER PATH</span><strong>Three semantic cards</strong><p>AI selects and writes the problem → intervention → effect story. CSS places those cards in a three-column row.</p></article>
        <article><span>03 · COMPONENT MOSAIC</span><strong>Demand-ranked, template-placed</strong><p>Content demand selects the hero; deterministic grid coordinates keep the artifact reproducible and printable.</p></article>
        <article><span>04 · IMAGE POLICY</span><strong>Visual-only on the poster</strong><p>Captions and page provenance stay in the source inspector, while the poster surface shows only the extracted visual.</p></article>
        <div className="layout-decision-table">
          {components.map(({ component, placement, demand }: any) => <div key={component.component_id}>
            <span>{placement.column_span >= 7 && placement.row_span >= 7 ? "HERO" : "SUPPORT"}</span>
            <strong>{component.title}</strong>
            <small>Demand {demand.toFixed(1)} · columns {placement.column_start}–{placement.column_start + placement.column_span - 1} · rows {placement.row_start}–{placement.row_start + placement.row_span - 1}</small>
          </div>)}
        </div>
      </div>
    </section>
  </div>;
}

function componentDemand(component: PosterComponent) {
  const typeDemand: Record<string, number> = { method_flow: 9, visual_gallery: 6.5, result_chart: 6, equation_explorer: 5.5, claim_evidence_chain: 4.5 };
  let score = typeDemand[component.component_type] || 0;
  score += Math.min(4, (component.asset_refs?.length || 0) * 1.4);
  score += Math.min(2, (component.details?.length || 0) * .25);
  if (component.component_type === "method_flow") score += Math.min(5, (component.steps?.length || 0) * 1.1);
  else if (component.component_type === "equation_explorer") score += Math.min(5, (component.equation_refs?.length || 0) * .65);
  else if (component.component_type === "result_chart") score += Math.min(4, (component.result_refs?.length || 0) * .8);
  else if (component.component_type === "visual_gallery") score += Math.min(4, (component.presentation_refs?.length || 0) * .9);
  else score += Math.min(3, (component.claim_refs?.length || 0) * .7);
  return score;
}

function equationById(bundle: Bundle, id: string) { return bundle.paper_analysis.equations.find((item: any) => item.equation_id === id); }
function presentationById(bundle: Bundle, id: string) { return (bundle.poster_plan.source_presentations || []).find((item: any) => item.presentation_id === id); }
function assetForId(bundle: Bundle, id: string) { const asset = bundle.document_ir.assets.find((item: any) => item.asset_id === id); return asset ? assetPath(bundle, asset.path) : ""; }
function assetPath(bundle: Bundle, path: string) { return `${bundle.asset_base || "./assets"}/${path.split("/").pop()}`; }
function cleanQuote(quote: string) { return quote.replace(/-\s*\n\s*/g, "").replace(/\s*\n\s*/g, " ").replace(/\s{2,}/g, " ").trim(); }
function cleanCaption(caption: string) { const text = cleanQuote(caption || "Method overview").replace(/^Figure\s+\d+\s*:\s*/i, ""); return text.split(/(?<=[.!?])\s+/)[0]; }
