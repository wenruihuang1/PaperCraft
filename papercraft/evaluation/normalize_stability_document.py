"""Normalize the visually verified equation regions in ppr_dev_003 DocumentIR 1.0."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from papercraft.models import DocumentIR


ROOT = Path(__file__).resolve().parent / "papers" / "ppr_dev_003" / "annotations"


EQUATIONS = [
    ("seq_p003_004", 3, "1", "x^(1) = alpha F(x) + beta", (406.0, 474.0, 559.0, 492.0)),
    ("seq_p003_005", 3, "2", "x^clp = sum_(c=1)^C (alpha_c x_c + beta_c m_c)", (390.0, 680.0, 560.0, 714.0)),
    ("seq_p004_001", 4, "3", "x_tilde^(2) = S odot x^(1) + (1-S) odot x^clp", (112.0, 168.0, 296.0, 188.0)),
    ("seq_p004_002", 4, "4", "x^(2) = argmin_(x_hat in {x_hat_1,...,x_hat_K}) D(f_theta(x_hat), f_theta(x^(0)))", (102.0, 296.0, 296.0, 324.0)),
    ("seq_p004_005", 4, "5", "w^str = sigma(g), w^str in (0,1)^C", (112.0, 556.0, 296.0, 583.0)),
    ("seq_p004_006", 4, "6", "w^sty = 1 - w^str", (112.0, 588.0, 296.0, 612.0)),
    ("seq_p004_007", 4, "7", "f_str^(k) = f^(k) odot w^str, f_sty^(k) = f^(k) odot w^sty", (52.0, 618.0, 296.0, 651.0)),
    ("seq_p004_003", 4, "8", "L_cgsd = d(phi(f_str^(1)),phi(f_str^(2))) - d(phi(f_sty^(1)),phi(f_sty^(2)))", (315.0, 352.0, 560.0, 416.0)),
    ("seq_p004_008", 4, "9", "d_kl(i) = 1 - <F_i^(k),F_i^(l)> / (||F_i^(k)||_2 ||F_i^(l)||_2)", (322.0, 635.0, 560.0, 673.0)),
    ("seq_p004_009", 4, "10", "d_stab(i) = (1/3) sum_((k,l)) d_kl(i)", (390.0, 682.0, 560.0, 714.0)),
    ("seq_p005_001", 5, "11", "Omega(i) = I(i in TopK_rho(-d_stab))", (118.0, 108.0, 296.0, 128.0)),
    ("seq_p005_002", 5, "12", "R(i) = exp(-d_stab(i)/tau), W(i) = Omega(i) R(i)", (84.0, 150.0, 296.0, 180.0)),
    ("seq_p005_003", 5, "13", "M(i) = I((y_i != 0) or (yhat_i^(0) != 0) or (yhat_i^(1) != 0) or (yhat_i^(2) != 0))", (60.0, 226.0, 296.0, 248.0)),
    ("seq_p005_004", 5, "14", "A(i) = Up_bi(W(i)) M(i)", (122.0, 266.0, 296.0, 292.0)),
    ("seq_p005_005", 5, "15", "q^(k) = g_phi(F^(k)), q^(k) in R^(C_q x H_q x W_q)", (96.0, 335.0, 296.0, 357.0)),
    ("seq_p005_006", 5, "16", "qhat^(k) = Up_bi(q^(k)), qhat^(k) in R^(C_q x H x W)", (96.0, 374.0, 296.0, 398.0)),
    ("seq_p005_007", 5, "17", "L_saam = sum_i A(i)(d(qhat_i^(0),qhat_i^(1)) + d(qhat_i^(0),qhat_i^(2))) / (sum_i A(i) + epsilon)", (84.0, 425.0, 296.0, 466.0)),
]


def main() -> None:
    path = ROOT / "document_ir.gold.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["equations"] = []
    equation_ref_ids = {f"src_{item[0]}" for item in EQUATIONS}
    payload["source_refs"] = [
        item
        for item in payload["source_refs"]
        if item["source_type"] != "equation" or item["source_ref_id"] in equation_ref_ids
    ]
    ref_by_id = {item["source_ref_id"]: item for item in payload["source_refs"]}
    for source_id, page, label, raw_text, (x0, y0, x1, y1) in EQUATIONS:
        bbox = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
        payload["equations"].append(
            {
                "source_equation_id": source_id,
                "page": page,
                "label": label,
                "representation": "pdf_text",
                "raw_text": raw_text,
                "latex": None,
                "bbox": bbox,
            }
        )
        ref_id = f"src_{source_id}"
        ref_by_id[ref_id].update(
            {
                "source_type": "equation",
                "locator": {
                    "page": page,
                    "block_id": None,
                    "source_equation_id": source_id,
                    "asset_id": None,
                    "char_start": None,
                    "char_end": None,
                    "bbox": bbox,
                },
                "quote": raw_text,
                "checksum": "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            }
        )
    payload["source_refs"] = list(ref_by_id.values())
    abstract = payload["metadata"].get("abstract") or ""
    marker = abstract.find("CCS Concepts")
    if marker > 0:
        payload["metadata"]["abstract"] = abstract[:marker].strip()
    document = DocumentIR.model_validate(payload)
    path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
