"""Build the source-adjudicated ppr_dev_003 semantic gold artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis


ROOT = Path(__file__).resolve().parent / "papers" / "ppr_dev_003" / "annotations"


def equation(
    number: int,
    latex: str,
    role: str,
    variables: list[tuple[str, str]],
    method: str,
    experiment: str,
) -> dict:
    page = 3 if number <= 2 else 4 if number <= 10 else 5
    source_index = {1: 4, 2: 5, 3: 1, 4: 2, 5: 5, 6: 6, 7: 7, 8: 3, 9: 8, 10: 9}.get(number, number - 10)
    source_id = f"seq_p{page:03d}_{source_index:03d}"
    return {
        "equation_id": f"eq_{number:02d}",
        "source_equation_id": source_id,
        "label": str(number),
        "latex_original": latex,
        "semantic_role": role,
        "variables": [
            {"symbol": symbol, "meaning": meaning, "unit": None, "domain": None}
            for symbol, meaning in variables
        ],
        "computation_steps": [
            "Read the inputs using the paper's original notation.",
            "Apply the displayed operation to produce the quantity used by the next stage.",
        ],
        "method_refs": [method],
        "experiment_refs": [experiment],
        "source_refs": [f"src_{source_id}"],
    }


def sufficiency(statuses: dict[str, str], source_refs: list[str]) -> list[dict]:
    rationales = {
        "directness": "The cited result or visualization addresses the stated claim directly within its evaluated scope.",
        "scope_match": "The claim is limited to the reported source-target tasks and Dice metric.",
        "baseline_adequacy": "The paper compares ERM, generic DG, and recent SSDG methods using a shared protocol.",
        "ablation_support": "Controlled removals test whether the named method element contributes.",
        "robustness": "Evidence spans the task directions explicitly named by the claim.",
        "statistical_support": "The paper reports point estimates without repeated-run uncertainty or significance tests.",
    }
    return [
        {
            "dimension": dimension,
            "status": statuses.get(dimension, "unknown"),
            "rationale": rationales[dimension],
            "source_refs": source_refs if statuses.get(dimension) in {"passed", "failed"} else [],
        }
        for dimension in rationales
    ]


def main() -> None:
    document = DocumentIR.model_validate_json((ROOT / "document_ir.gold.json").read_text())
    analysis_payload = {
        "schema_version": "1.2.0",
        "artifact_revision": 1,
        "paper_id": "ppr_dev_003",
        "source_revision": document.artifact_revision,
        "metadata": {"title": document.metadata.title, "authors": [], "language": "en"},
        "concepts": [
            {
                "concept_id": "cpt_problem",
                "concept_type": "problem",
                "statement": "Uniform consistency treats every perturbed region as equally reliable even though strong appearance shifts can destabilize boundaries, background, and semantically critical anatomy.",
                "importance": "critical",
                "source_refs": ["src_p001_b0013", "src_ast_figure_001"],
            },
            {
                "concept_id": "cpt_motivation",
                "concept_type": "motivation",
                "statement": "SSDG needs diverse perturbations, but it also needs a way to decide where the resulting supervision remains trustworthy.",
                "importance": "critical",
                "source_refs": ["src_p002_b0025", "src_p002_b0033"],
            },
            {
                "concept_id": "cpt_insight",
                "concept_type": "key_insight",
                "statement": "Estimate repeatable semantics across anchor, base, and strong views, then align only stable foreground support with confidence-dependent strength.",
                "importance": "critical",
                "source_refs": ["src_p002_b0033", "src_ast_figure_002"],
            },
            {
                "concept_id": "cpt_conclusion",
                "concept_type": "conclusion",
                "statement": "For this evaluated medical SSDG setting, reliable alignment depends on identifying stable semantic information instead of enforcing unconditional invariance.",
                "importance": "high",
                "source_refs": ["src_p008_b0086"],
            },
        ],
        "narrative_frame": {
            "problem": {
                "concept_ref": "cpt_problem",
                "context": "Single-source medical segmentation must generalize to unseen acquisition shifts without target data.",
                "conventional_assumption": "Uniform consistency assumes every perturbed region is equally trustworthy.",
                "failure_mechanism": "Strong perturbations make boundaries, background, and subtle anatomy disagree across views.",
                "consequence": "Aligning those unstable responses can turn noise into supervision and limit generalization.",
                "source_refs": ["src_p001_b0013", "src_ast_figure_001"],
            },
            "motivation": {
                "concept_ref": "cpt_motivation",
                "observation": "Useful augmentation and safe consistency are not the same thing.",
                "limitation": "Input diversity alone does not reveal which local semantics survive a perturbation.",
                "design_requirement": "The model must estimate reliability before deciding where and how strongly to align.",
                "source_refs": ["src_p002_b0025", "src_p002_b0033"],
            },
            "insight": {
                "concept_ref": "cpt_insight",
                "principle": "Align repeatable semantics, not every response.",
                "operationalization": "Use tri-view agreement to select stable foreground regions and convert stability into an alignment weight.",
                "expected_effect": "The constraint concentrates on reliable anatomy while avoiding unstable boundary and background responses.",
                "source_refs": ["src_ast_figure_002", "src_ast_figure_011"],
            },
        },
        "claims": [
            {
                "claim_id": "clm_selective_alignment",
                "statement": "Stability-guided selective alignment is a better-motivated constraint than uniform alignment when strong perturbations create spatially unreliable responses.",
                "claim_type": "main",
                "scope": "The paper's single-source medical segmentation formulation and evaluated perturbation pipeline.",
                "qualifiers": ["mechanistic support is qualitative and ablation-based", "no repeated-run uncertainty is reported"],
                "importance": "critical",
                "source_refs": ["src_p001_b0013", "src_p008_b0030"],
            },
            {
                "claim_id": "clm_benchmark_performance",
                "statement": "SAA reports the best average Dice among the compared non-supervised methods on all four evaluated transfer tasks.",
                "claim_type": "main",
                "scope": "BTCV-CHAOS MRI↔CT and MS-CMRSeg LGE↔bSSFP under the paper's shared U-Net protocol.",
                "qualifiers": ["point estimates only", "does not imply performance beyond these datasets or transfer directions"],
                "importance": "critical",
                "source_refs": ["src_ast_table_004", "src_p005_b0075", "src_p005_b0092"],
            },
            {
                "claim_id": "clm_saam_contribution",
                "statement": "SAAM is the strongest single-module contributor, while the full RCCS+CGSD+SAAM configuration performs best on every reported task.",
                "claim_type": "supporting",
                "scope": "Component ablations in Tables 2 and 3 across the four reported transfer tasks.",
                "qualifiers": ["components are evaluated within this implementation"],
                "importance": "high",
                "source_refs": ["src_p007_b0045", "src_ast_table_006", "src_ast_table_007"],
            },
            {
                "claim_id": "clm_mechanism_visualization",
                "statement": "The mechanism visualization shows more organ-centered stable support and smoother anatomy-focused alignment weights for SAA than for the baseline example.",
                "claim_type": "supporting",
                "scope": "The representative case visualized in Figure 6.",
                "qualifiers": ["qualitative example", "not a population-level statistical result"],
                "importance": "medium",
                "source_refs": ["src_ast_figure_011", "src_p008_b0030"],
            },
        ],
        "methods": [
            {
                "method_id": "mth_tri_view",
                "name": "Tri-View Construction",
                "purpose": "Create anchor, mild base, and stronger semantic-preserving views so cross-view repeatability can be measured rather than assumed.",
                "inputs": ["source image x", "source label y"],
                "outputs": ["anchor x^(0)", "base x^(1)", "strong x^(2)"],
                "steps": [
                    {"index": 1, "description": "Keep the anchor unchanged as the semantic reference.", "source_refs": ["src_p003_b0113"]},
                    {"index": 2, "description": "Apply global intensity perturbation for a moderate base view.", "source_refs": ["src_p003_b0113", "src_seq_p003_004"]},
                    {"index": 3, "description": "Build the strong view with class-conditional perturbation, saliency fusion, and random-convolution candidate selection.", "source_refs": ["src_p003_b0121", "src_p004_b0009"]},
                ],
                "assumptions": ["The selected perturbations should preserve task-relevant anatomy sufficiently for cross-view comparison."],
                "equation_refs": ["eq_01", "eq_02", "eq_03", "eq_04"],
                "claim_refs": ["clm_selective_alignment", "clm_saam_contribution"],
                "source_refs": ["src_p003_b0102", "src_p003_b0113", "src_p004_b0009"],
            },
            {
                "method_id": "mth_cgsd",
                "name": "Channel-Gated Structure-Style Decoupling",
                "purpose": "Suppress shallow appearance-sensitive channels before estimating spatial stability from deeper features.",
                "inputs": ["tri-view shallow features", "shared channel gate g"],
                "outputs": ["structure-weighted features", "CGSD regularization"],
                "steps": [
                    {"index": 1, "description": "Convert a shared gate into complementary structure and style channel weights.", "source_refs": ["src_p004_b0034", "src_seq_p004_005", "src_seq_p004_006"]},
                    {"index": 2, "description": "Forward structure-weighted features and suppress style-weighted responses.", "source_refs": ["src_p004_b0045", "src_seq_p004_007"]},
                    {"index": 3, "description": "Regularize base/strong structure embeddings against the complementary style allocation.", "source_refs": ["src_p004_b0082", "src_seq_p004_003"]},
                ],
                "assumptions": ["Cross-view channel discrepancy is informative about structure-dominant versus appearance-sensitive responses."],
                "equation_refs": ["eq_05", "eq_06", "eq_07", "eq_08"],
                "claim_refs": ["clm_selective_alignment", "clm_saam_contribution"],
                "source_refs": ["src_p004_b0034", "src_ast_figure_003", "src_p004_b0084"],
            },
            {
                "method_id": "mth_saam",
                "name": "Stability-Aware Alignment Module",
                "purpose": "Estimate spatial reliability across views, retain stable foreground support, and weight anchor-centered feature alignment by confidence.",
                "inputs": ["deep features F^(0), F^(1), F^(2)", "label/prediction foreground support"],
                "outputs": ["stability d_stab", "stable mask Omega", "alignment weight A", "L_saam"],
                "steps": [
                    {"index": 1, "description": "Average pairwise cosine dissimilarity to estimate cross-view stability.", "source_refs": ["src_seq_p004_008", "src_seq_p004_009"]},
                    {"index": 2, "description": "Select Top-rho stable locations and convert distance into a reliability gate.", "source_refs": ["src_p005_b0002", "src_seq_p005_001", "src_seq_p005_002"]},
                    {"index": 3, "description": "Restrict the gate to foreground support and align projected anchor features to base and strong views.", "source_refs": ["src_p005_b0017", "src_p005_b0043", "src_seq_p005_007"]},
                ],
                "assumptions": ["Lower cross-view feature dissimilarity indicates more reliable semantic support for alignment."],
                "equation_refs": [f"eq_{index:02d}" for index in range(9, 18)],
                "claim_refs": ["clm_selective_alignment", "clm_saam_contribution", "clm_mechanism_visualization"],
                "source_refs": ["src_p004_b0089", "src_p005_b0002", "src_p005_b0043", "src_ast_figure_011"],
            },
        ],
        "equations": [
            equation(1, r"x^{(1)}=\alpha F(x)+\beta", "update_rule", [(r"x", "source image"), (r"\alpha,\beta", "sampled intensity scale and shift")], "mth_tri_view", "exp_tri_view"),
            equation(2, r"x^{\mathrm{clp}}=\sum_{c=1}^{C}(\alpha_c x_c+\beta_c m_c)", "update_rule", [(r"m_c", "binary mask for semantic class c"), (r"\alpha_c,\beta_c", "class-wise intensity parameters")], "mth_tri_view", "exp_tri_view"),
            equation(3, r"\tilde{x}^{(2)}=S\odot x^{(1)}+(1-S)\odot x^{\mathrm{clp}}", "update_rule", [(r"S", "saliency map"), (r"\odot", "element-wise multiplication")], "mth_tri_view", "exp_tri_view"),
            equation(4, r"x^{(2)}=\arg\min_{\hat{x}\in\{\hat{x}_1,\ldots,\hat{x}_K\}}\mathcal{D}\!\left(f_\theta(\hat{x}),f_\theta(x^{(0)})\right)", "constraint", [(r"\hat{x}_k", "random-convolution candidate"), (r"\mathcal{D}", "cosine distance")], "mth_tri_view", "exp_tri_view"),
            equation(5, r"\mathbf{w}^{\mathrm{str}}=\sigma(\mathbf{g}),\quad \mathbf{w}^{\mathrm{str}}\in(0,1)^C", "definition", [(r"\mathbf{g}", "shared learnable channel gate"), (r"\mathbf{w}^{\mathrm{str}}", "structure channel weights")], "mth_cgsd", "exp_component_ablation"),
            equation(6, r"\mathbf{w}^{\mathrm{sty}}=\mathbf{1}-\mathbf{w}^{\mathrm{str}}", "definition", [(r"\mathbf{w}^{\mathrm{sty}}", "complementary style channel weights")], "mth_cgsd", "exp_component_ablation"),
            equation(7, r"f_{\mathrm{str}}^{(k)}=f^{(k)}\odot\mathbf{w}^{\mathrm{str}},\quad f_{\mathrm{sty}}^{(k)}=f^{(k)}\odot\mathbf{w}^{\mathrm{sty}}", "update_rule", [(r"f^{(k)}", "shallow feature map for view k"), (r"k", "view index")], "mth_cgsd", "exp_component_ablation"),
            equation(8, r"\mathcal{L}_{\mathrm{cgsd}}=d\!\left(\phi(f_{\mathrm{str}}^{(1)}),\phi(f_{\mathrm{str}}^{(2)})\right)-d\!\left(\phi(f_{\mathrm{sty}}^{(1)}),\phi(f_{\mathrm{sty}}^{(2)})\right)", "objective", [(r"\phi", "lightweight projector"), (r"d", "cosine distance")], "mth_cgsd", "exp_component_ablation"),
            equation(9, r"d_{kl}(i)=1-\frac{\langle F_i^{(k)},F_i^{(l)}\rangle}{\lVert F_i^{(k)}\rVert_2\lVert F_i^{(l)}\rVert_2}", "metric", [(r"F_i^{(k)}", "deep feature vector at location i in view k"), (r"d_{kl}", "pairwise cosine dissimilarity")], "mth_saam", "exp_saam_ablation"),
            equation(10, r"d_{\mathrm{stab}}(i)=\frac{1}{3}\sum_{(k,l)}d_{kl}(i)", "metric", [(r"d_{\mathrm{stab}}", "mean cross-view dissimilarity"), (r"(k,l)", "the three view pairs")], "mth_saam", "exp_saam_ablation"),
            equation(11, r"\Omega(i)=\mathbb{I}\!\left(i\in\operatorname{TopK}_{\rho}(-d_{\mathrm{stab}})\right)", "constraint", [(r"\Omega", "stable-region selector"), (r"\rho", "selection ratio")], "mth_saam", "exp_saam_ablation"),
            equation(12, r"R(i)=\exp\!\left(-\frac{d_{\mathrm{stab}}(i)}{\tau}\right),\quad W(i)=\Omega(i)\,R(i)", "definition", [(r"\tau", "temperature"), (r"W", "low-resolution stability gate")], "mth_saam", "exp_saam_ablation"),
            equation(13, r"M(i)=\mathbb{I}\!\left((y_i\neq0)\vee(\hat y_i^{(0)}\neq0)\vee(\hat y_i^{(1)}\neq0)\vee(\hat y_i^{(2)}\neq0)\right)", "constraint", [(r"M", "foreground union prior"), (r"\hat y^{(k)}", "prediction for view k")], "mth_saam", "exp_saam_ablation"),
            equation(14, r"A(i)=\operatorname{Up}_{\mathrm{bi}}(W(i))\,M(i)", "definition", [(r"A", "final alignment weight"), (r"\operatorname{Up}_{\mathrm{bi}}", "bilinear upsampling")], "mth_saam", "exp_saam_ablation"),
            equation(15, r"q^{(k)}=g_{\phi}(F^{(k)}),\quad q^{(k)}\in\mathbb{R}^{C_q\times H_q\times W_q}", "update_rule", [(r"g_\phi", "shared projection head"), (r"q^{(k)}", "compact feature embedding")], "mth_saam", "exp_saam_ablation"),
            equation(16, r"\hat q^{(k)}=\operatorname{Up}_{\mathrm{bi}}(q^{(k)}),\quad \hat q^{(k)}\in\mathbb{R}^{C_q\times H\times W}", "update_rule", [(r"\hat q^{(k)}", "upsampled embedding at alignment resolution")], "mth_saam", "exp_saam_ablation"),
            equation(17, r"\mathcal{L}_{\mathrm{saam}}=\frac{\sum_i A(i)\left[d(\hat q_i^{(0)},\hat q_i^{(1)})+d(\hat q_i^{(0)},\hat q_i^{(2)})\right]}{\sum_i A(i)+\epsilon}", "objective", [(r"\mathcal{L}_{\mathrm{saam}}", "weighted anchor-centered alignment loss"), (r"\epsilon", "numerical stabilizer")], "mth_saam", "exp_saam_ablation"),
        ],
        "experiments": [
            {
                "experiment_id": "exp_main_benchmark",
                "question": "Does SAA outperform the strongest compared non-supervised method across all four benchmark directions?",
                "setup": "Shared U-Net protocol on BTCV-CHAOS cross-modality and MS-CMRSeg cross-sequence SSDG tasks; Dice is the metric.",
                "datasets": ["BTCV-CHAOS", "MS-CMRSeg"],
                "metrics": ["Average Dice (%)"],
                "baselines": ["ERM", "Cutout", "RSC", "MixStyle", "AdvBias", "RandConv", "CSDG", "SLAug", "S2S2", "DCON"],
                "results": [
                    {"result_id": "res_mri_ct", "metric": "MRI→CT", "value": "84.45% vs 85.55%", "comparison": "DCON vs SAA", "source_refs": ["src_p006_b0014", "src_p006_b0015", "src_ast_table_004"]},
                    {"result_id": "res_ct_mri", "metric": "CT→MRI", "value": "88.63% vs 89.20%", "comparison": "SLAug vs SAA", "source_refs": ["src_p006_b0027", "src_p006_b0028", "src_ast_table_004"]},
                    {"result_id": "res_lge_bssfp", "metric": "LGE→bSSFP", "value": "88.06% vs 88.12%", "comparison": "DCON vs SAA", "source_refs": ["src_p006_b0014", "src_p006_b0015", "src_ast_table_004"]},
                    {"result_id": "res_bssfp_lge", "metric": "bSSFP→LGE", "value": "86.69% vs 87.33%", "comparison": "SLAug vs SAA", "source_refs": ["src_p006_b0027", "src_p006_b0028", "src_ast_table_004"]},
                ],
                "limitations": ["Only point estimates are reported; no repeated-run variance or significance test is provided."],
                "claim_refs": ["clm_benchmark_performance"],
                "source_refs": ["src_ast_table_004", "src_p005_b0069", "src_p005_b0075", "src_p005_b0092"],
            },
            {
                "experiment_id": "exp_component_ablation",
                "question": "Which top-level modules account for the reported gains?",
                "setup": "Baseline plus RCCS, CGSD, or SAAM individually, compared with the full configuration on all four tasks.",
                "datasets": ["BTCV-CHAOS", "MS-CMRSeg"],
                "metrics": ["Average Dice (%)"],
                "baselines": ["Baseline", "+RCCS", "+CGSD", "+SAAM", "Full"],
                "results": [
                    {"result_id": "res_component_mri_ct", "metric": "MRI→CT component ablation", "value": "82.77% vs 85.55%", "comparison": "Baseline vs Full", "source_refs": ["src_p007_b0012", "src_p007_b0045"]},
                    {"result_id": "res_component_lge_bssfp", "metric": "LGE→bSSFP component ablation", "value": "86.54% vs 88.12%", "comparison": "Baseline vs Full", "source_refs": ["src_p007_b0012", "src_p007_b0045"]},
                    {"result_id": "res_component_ct_mri", "metric": "CT→MRI component ablation", "value": "87.24% vs 89.20%", "comparison": "Baseline vs Full", "source_refs": ["src_p007_b0026", "src_p007_b0045"]},
                    {"result_id": "res_component_bssfp_lge", "metric": "bSSFP→LGE component ablation", "value": "85.55% vs 87.33%", "comparison": "Baseline vs Full", "source_refs": ["src_p007_b0026", "src_p007_b0045"]},
                ],
                "limitations": ["The ablation isolates configured modules, not every internal perturbation choice."],
                "claim_refs": ["clm_saam_contribution", "clm_selective_alignment"],
                "source_refs": ["src_ast_table_006", "src_ast_table_007", "src_p007_b0045"],
            },
            {
                "experiment_id": "exp_saam_ablation",
                "question": "Do stable-region selection, distance weighting, and the alignment term each contribute?",
                "setup": "Remove Ω, W, or the alignment term while keeping the remaining SAA configuration fixed.",
                "datasets": ["BTCV-CHAOS", "MS-CMRSeg"],
                "metrics": ["Overall average Dice (%)"],
                "baselines": ["Full", "w/o Ω", "w/o W", "w/o align"],
                "results": [
                    {"result_id": "res_saam_selector", "metric": "Stable-region selector", "value": "86.70% vs 87.55%", "comparison": "w/o Ω vs Full", "source_refs": ["src_p007_b0055", "src_p007_b0046"]},
                    {"result_id": "res_saam_weight", "metric": "Distance weighting", "value": "86.98% vs 87.55%", "comparison": "w/o W vs Full", "source_refs": ["src_p007_b0055", "src_p007_b0046"]},
                    {"result_id": "res_saam_align", "metric": "Alignment objective", "value": "86.30% vs 87.55%", "comparison": "w/o align vs Full", "source_refs": ["src_p007_b0055", "src_p007_b0046"]},
                ],
                "limitations": ["The experiment reports deterministic point estimates without uncertainty."],
                "claim_refs": ["clm_selective_alignment", "clm_saam_contribution"],
                "source_refs": ["src_ast_table_008", "src_ast_table_009", "src_p007_b0046"],
            },
            {
                "experiment_id": "exp_tri_view",
                "question": "Does the full anchor-base-strong hierarchy outperform isolated view combinations?",
                "setup": "Tri-view alternatives on MRI→CT with CGSD and SAAM fixed.",
                "datasets": ["BTCV-CHAOS MRI→CT"],
                "metrics": ["Dice (%)"],
                "baselines": ["Anchor", "A+B", "A+S", "A+B+S", "S-w/o-L", "S-w/o-T"],
                "results": [{"result_id": "res_tri_view", "metric": "Tri-view hierarchy", "value": "64.14% vs 85.55%", "comparison": "Anchor vs A+B+S", "source_refs": ["src_p007_b0095", "src_p007_b0113", "src_p007_b0079"]}],
                "limitations": ["The isolated tri-view analysis is shown on MRI→CT only."],
                "claim_refs": ["clm_selective_alignment", "clm_saam_contribution"],
                "source_refs": ["src_ast_figure_010", "src_p007_b0079"],
            },
        ],
        "understanding_path": [
            {"step_id": "step_problem", "role": "problem", "object_refs": ["cpt_problem"], "transition": "The failure is spatially selective, so reliability must be estimated locally."},
            {"step_id": "step_motivation", "role": "motivation", "object_refs": ["cpt_motivation"], "transition": "Cross-view repeatability provides a usable reliability signal."},
            {"step_id": "step_key_insight", "role": "key_insight", "object_refs": ["cpt_insight"], "transition": "Three modules operationalize the insight."},
            {"step_id": "step_method", "role": "method", "object_refs": ["mth_tri_view", "mth_cgsd", "mth_saam"], "transition": "Benchmarks and controlled removals test the scoped claims."},
            {"step_id": "step_evidence", "role": "evidence", "object_refs": ["clm_benchmark_performance", "clm_saam_contribution", "exp_main_benchmark", "exp_component_ablation", "exp_saam_ablation"], "transition": "The conclusion remains bounded to the demonstrated settings."},
            {"step_id": "step_conclusion", "role": "conclusion", "object_refs": ["cpt_conclusion"], "transition": None},
        ],
        "analysis_warnings": ["Anthropic review paused on 2026-07-17 because the configured API credential returned HTTP 401; source-adjudicated gold was completed locally."],
    }
    analysis = PaperAnalysis.model_validate(analysis_payload)

    evidence_payload = {
        "schema_version": "1.2.0",
        "artifact_revision": 1,
        "paper_id": "ppr_dev_003",
        "analysis_revision": 1,
        "evidence": [
            {"evidence_id": "ev_benchmark", "evidence_type": "table", "summary": "Table 1 reports the strongest compared average Dice for SAA in all four transfer directions.", "object_refs": ["exp_main_benchmark", "ast_table_004"], "source_refs": ["src_ast_table_004", "src_p005_b0075", "src_p005_b0092"]},
            {"evidence_id": "ev_component_ablation", "evidence_type": "table", "summary": "Tables 2–3 show SAAM as the strongest single component and the full configuration as best on each task.", "object_refs": ["exp_component_ablation", "ast_table_006", "ast_table_007"], "source_refs": ["src_ast_table_006", "src_ast_table_007", "src_p007_b0045"]},
            {"evidence_id": "ev_saam_ablation", "evidence_type": "table", "summary": "Removing Ω, W, or the alignment term reduces the reported overall average Dice.", "object_refs": ["exp_saam_ablation", "ast_table_008"], "source_refs": ["src_ast_table_008", "src_p007_b0046"]},
            {"evidence_id": "ev_mechanism", "evidence_type": "figure", "summary": "Figure 6 visualizes a representative change from diffuse stability to compact organ-centered support and smoother alignment weights.", "object_refs": ["ast_figure_011", "mth_saam"], "source_refs": ["src_ast_figure_011", "src_p008_b0030"]},
        ],
        "edges": [
            {"edge_id": "edge_mechanism_to_selective", "from_evidence": "ev_mechanism", "to_claim": "clm_selective_alignment", "relation": "partially_supports", "strength": 0.65, "rationale": "The visualization and SAAM ablation support the intended mechanism, but do not directly establish a general causal safety claim.", "qualifiers": ["representative visualization"]},
            {"edge_id": "edge_saam_to_selective", "from_evidence": "ev_saam_ablation", "to_claim": "clm_selective_alignment", "relation": "partially_supports", "strength": 0.75, "rationale": "Controlled removal shows the selector, weight, and alignment term each contribute within the evaluated system.", "qualifiers": ["point estimates"]},
            {"edge_id": "edge_benchmark", "from_evidence": "ev_benchmark", "to_claim": "clm_benchmark_performance", "relation": "supports", "strength": 0.95, "rationale": "The full comparison table directly contains the four scoped best-average results.", "qualifiers": ["evaluated methods and protocol only"]},
            {"edge_id": "edge_components", "from_evidence": "ev_component_ablation", "to_claim": "clm_saam_contribution", "relation": "supports", "strength": 0.9, "rationale": "Four-task component ablations directly compare each single module and the full system.", "qualifiers": ["configured implementation"]},
            {"edge_id": "edge_mechanism_visual", "from_evidence": "ev_mechanism", "to_claim": "clm_mechanism_visualization", "relation": "supports", "strength": 0.85, "rationale": "The claim is explicitly limited to what is visible in the representative figure.", "qualifiers": ["qualitative example"]},
        ],
        "claim_assessments": [
            {"claim_id": "clm_selective_alignment", "status": "partially_supported", "supporting_edges": ["edge_mechanism_to_selective", "edge_saam_to_selective"], "sufficiency_checks": sufficiency({"directness": "passed", "scope_match": "passed", "baseline_adequacy": "passed", "ablation_support": "passed", "robustness": "unknown", "statistical_support": "unknown"}, ["src_p007_b0046", "src_p008_b0030"]), "limitations": ["The paper does not directly quantify alignment noise or provide repeated-run uncertainty."], "rationale": "The design is supported by controlled removals and mechanism visualization, but the broader safety rationale remains indirect."},
            {"claim_id": "clm_benchmark_performance", "status": "supported", "supporting_edges": ["edge_benchmark"], "sufficiency_checks": sufficiency({"directness": "passed", "scope_match": "passed", "baseline_adequacy": "passed", "ablation_support": "not_applicable", "robustness": "passed", "statistical_support": "unknown"}, ["src_ast_table_004", "src_p005_b0075", "src_p005_b0092"]), "limitations": ["No variance or significance tests are reported."], "rationale": "The narrowly scoped ranking claim is directly supported across all four tabled transfer directions."},
            {"claim_id": "clm_saam_contribution", "status": "supported", "supporting_edges": ["edge_components"], "sufficiency_checks": sufficiency({"directness": "passed", "scope_match": "passed", "baseline_adequacy": "passed", "ablation_support": "passed", "robustness": "passed", "statistical_support": "unknown"}, ["src_p007_b0045", "src_ast_table_006", "src_ast_table_007"]), "limitations": ["The conclusion is bounded to the four configured ablation tasks."], "rationale": "The component tables directly support both parts of the claim on every reported task."},
            {"claim_id": "clm_mechanism_visualization", "status": "partially_supported", "supporting_edges": ["edge_mechanism_visual"], "sufficiency_checks": sufficiency({"directness": "passed", "scope_match": "passed", "baseline_adequacy": "passed", "ablation_support": "passed", "robustness": "unknown", "statistical_support": "unknown"}, ["src_ast_figure_011", "src_p008_b0030"]), "limitations": ["One representative case cannot establish population-level behavior."], "rationale": "The visual description is faithful to Figure 6, but generalization of that mechanism is not statistically established."},
        ],
        "orphan_claims": [],
        "orphan_evidence": [],
    }
    evidence = EvidenceGraph.model_validate(evidence_payload)
    for name, value in (("paper_analysis.gold.json", analysis), ("evidence_graph.gold.json", evidence)):
        (ROOT / name).write_text(json.dumps(value.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "poster_expectations.json").write_text(json.dumps({
        "paper_id": "ppr_dev_003",
        "required_narrative_roles": ["problem", "motivation", "key_insight"],
        "required_method_refs": ["mth_tri_view", "mth_cgsd", "mth_saam"],
        "core_equation_labels": [str(index) for index in range(9, 18)],
        "required_result_refs": ["res_mri_ct", "res_ct_mri", "res_lge_bssfp", "res_bssfp_lge"],
        "preferred_asset_refs": ["ast_figure_001", "ast_figure_002", "ast_figure_011", "ast_table_004", "ast_figure_005"],
        "main_area_ratio": {"narrative": 0.28, "method_equations": 0.52, "results_evidence": 0.20},
        "forbidden_presentations": ["raw flattened table text", "raw PDF formula text", "unqualified claims beyond the evaluated tasks"]
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "annotation_audit.json").write_text(json.dumps({
        "schema_version": "1.2.0", "paper_id": "ppr_dev_003", "annotator_id": "codex_primary",
        "annotation_revision": 1, "status": "source_adjudicated",
        "reviewed_on": "2026-07-17", "model_review": "paused_invalid_credential",
        "formula_review": {"status": "passed_visual_crop_and_manual_transcription", "equation_labels_checked": [str(index) for index in range(1, 18)], "rendered_pages_checked": [3, 4, 5]},
        "numeric_review": {"status": "passed", "rendered_pages_checked": [6, 7, 8]},
        "notes": ["All formulas retain the paper's symbols and a PDF crop fallback.", "Benchmark claims are bounded to the four reported transfer directions.", "Claude Opus 4.8 returned HTTP 401 before token use; no provider output was stored."]
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
