import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Poster } from "./Poster";

describe("Poster", () => {
  it("renders four supported component families", () => {
    const component = (id: string, type: string) => ({ component_id: id, component_type: type, title: type, summary: "summary", source_refs: ["src_one"], content_refs: [], claim_refs: [], evidence_refs: [], asset_refs: type === "method_flow" ? ["ast_method"] : [], details: [], steps: type === "method_flow" ? [{ label: "one", description: "step", source_refs: ["src_one"] }, { label: "two", description: "step", source_refs: ["src_one"] }] : undefined, equation_refs: [], chart_data: [] });
    const components = [component("cmp_method", "method_flow"), component("cmp_equation", "equation_explorer"), component("cmp_claim", "claim_evidence_chain"), component("cmp_result", "result_chart")];
    const placements = components.map((item, index) => ({ component_id: item.component_id, column_start: index * 3 + 1, column_span: 3, row_start: 1, row_span: 3 }));
    const bundle: any = { document_ir: { source_refs: [{ source_ref_id: "src_one", source_type: "text_span", quote: "source", locator: { page: 1 } }], assets: [{ asset_id: "ast_method", asset_type: "figure", page: 3, path: "method.png", caption: "Method overview" }] }, paper_analysis: { metadata: { title: "Paper", authors: ["Author"] }, concepts: [{ concept_type: "key_insight", statement: "Insight" }], equations: [], claims: [] }, evidence_graph: { claim_assessments: [] }, poster_plan: { paper_id: "ppr_test", artifact_revision: 1, theme: { background: "#07111F", surface: "#101F33", foreground: "#F4F7FB", muted: "#9DB0C9", accent: "#46C2FF", accent_secondary: "#A78BFA", success: "#45D59B", warning: "#FFBE5C", danger: "#FF6B7A" }, components, layout_profiles: { screen_16_9: { component_layouts: placements } } }, review_result: { issues: [] } };
    render(<Poster bundle={bundle} />);
    expect(screen.getByText("method flow")).toBeInTheDocument();
    expect(screen.getByText("equation_explorer")).toBeInTheDocument();
    expect(screen.getByText("claim_evidence_chain")).toBeInTheDocument();
    expect(screen.getByText("result_chart")).toBeInTheDocument();
    expect(screen.getByAltText("Method overview")).toBeInTheDocument();
  });

  it("opens a large grounded method inspector", () => {
    const method = { component_id: "cmp_method", component_type: "method_flow", title: "Detailed method", summary: "summary", source_refs: ["src_one"], content_refs: ["mth_one"], claim_refs: [], evidence_refs: [], asset_refs: [], details: [], steps: [{ label: "1. Module", description: "Do the grounded operation", source_refs: ["src_one"] }], inspector_panels: [{ panel_id: "mip_one", method_ref: "mth_one", title: "Module", why_needed: "Avoid unreliable alignment", inputs: ["image"], outputs: ["stable mask"], equation_refs: [], experiment_refs: [], source_refs: ["src_one"], presentation_refs: [] }] };
    const bundle: any = { document_ir: { source_refs: [{ source_ref_id: "src_one", source_type: "text_span", quote: "source", locator: { page: 1 } }], assets: [] }, paper_analysis: { metadata: { title: "Paper", authors: ["Author"] }, artifact_revision: 1, methods: [{ method_id: "mth_one", steps: [{ index: 1, description: "Do the grounded operation", source_refs: ["src_one"] }] }], equations: [], claims: [] }, evidence_graph: { claim_assessments: [] }, poster_plan: { paper_id: "ppr_test", schema_version: "1.2.0", artifact_revision: 1, narrative_regions: [{ role: "problem", eyebrow: "01", headline: "Problem", body: "Problem body", source_refs: ["src_one"] }], source_presentations: [], theme: { background: "#07111F", surface: "#101F33", foreground: "#F4F7FB", muted: "#9DB0C9", accent: "#46C2FF", accent_secondary: "#A78BFA", success: "#45D59B", warning: "#FFBE5C", danger: "#FF6B7A" }, components: [method], layout_profiles: { screen_16_9: { component_layouts: [{ component_id: "cmp_method", column_start: 1, column_span: 12, row_start: 1, row_span: 10 }] } } }, review_result: { issues: [] } };
    render(<Poster bundle={bundle} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Method Inspector" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Avoid unreliable alignment")).toBeInTheDocument();
    expect(screen.getAllByText("stable mask").length).toBeGreaterThan(0);
  });

  it("shows one aligned source visual without duplicating it in the excerpt", () => {
    const method = { component_id: "cmp_method", component_type: "method_flow", title: "Method", summary: "summary", source_refs: ["src_figure"], content_refs: [], claim_refs: [], evidence_refs: [], asset_refs: ["ast_method"], details: [], steps: [] };
    const bundle: any = { document_ir: { source_refs: [{ source_ref_id: "src_figure", source_type: "figure", quote: "Figure 2 method overview", locator: { page: 3, bbox: { x0: 10, y0: 20, x1: 500, y1: 220 } } }], assets: [{ asset_id: "ast_method", asset_type: "figure", page: 3, path: "method.png", caption: "Method overview" }] }, paper_analysis: { metadata: { title: "Paper", authors: ["Author"] }, artifact_revision: 1, equations: [], claims: [] }, evidence_graph: { claim_assessments: [] }, poster_plan: { paper_id: "ppr_test", schema_version: "1.2.0", artifact_revision: 1, narrative_regions: [{ role: "problem", eyebrow: "01 · PROBLEM", headline: "Problem", body: "Problem body", source_refs: ["src_figure"], presentation_ref: "spr_method" }], source_presentations: [{ presentation_id: "spr_method", role: "method_overview", display_kind: "original_asset", title: "Method overview", page: 3, source_ref_id: "src_figure", asset_ref: "ast_method" }], theme: { background: "#07111F", surface: "#101F33", foreground: "#F4F7FB", muted: "#9DB0C9", accent: "#46C2FF", accent_secondary: "#A78BFA", success: "#45D59B", warning: "#FFBE5C", danger: "#FF6B7A" }, components: [method], layout_profiles: { screen_16_9: { component_layouts: [{ component_id: "cmp_method", column_start: 1, column_span: 12, row_start: 1, row_span: 10 }] } } }, review_result: { issues: [] } };
    render(<Poster bundle={bundle} />);
    fireEvent.click(screen.getByRole("button", { name: /Open visual explanation/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(document.querySelectorAll(".source-primary img")).toHaveLength(1);
    expect(document.querySelectorAll(".source-list .presentation-image")).toHaveLength(0);
    expect(screen.getByText(/shown at full size/)).toBeInTheDocument();
  });
});
