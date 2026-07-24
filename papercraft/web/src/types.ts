export type SourceRef = {
  source_ref_id: string;
  source_type: string;
  quote: string;
  locator: { page: number; bbox?: { x0: number; y0: number; x1: number; y1: number } };
};

export type PosterComponent = {
  component_id: string;
  component_type: "method_flow" | "equation_explorer" | "claim_evidence_chain" | "result_chart" | "visual_gallery";
  title: string;
  summary: string;
  source_refs: string[];
  content_refs: string[];
  claim_refs: string[];
  evidence_refs: string[];
  asset_refs: string[];
  details: string[];
  steps?: { label: string; description: string; source_refs: string[] }[];
  inspector_panels?: any[];
  equation_refs?: string[];
  equation_groups?: any[];
  experiment_refs?: string[];
  result_refs?: string[];
  chart_type?: string;
  chart_data?: { label: string; value: number; display_value: string; series: string }[];
  presentation_refs?: string[];
};

export type Bundle = {
  document_ir: any;
  paper_analysis: any;
  evidence_graph: any;
  poster_plan: any;
  review_result: any;
  asset_base?: string;
  profile?: "screen_16_9" | "print_a0_landscape";
};

declare global {
  interface Window {
    __PAPERCRAFT_POSTER__?: Bundle | null;
    __PAPERCRAFT_BOOTED__?: boolean;
  }
}
