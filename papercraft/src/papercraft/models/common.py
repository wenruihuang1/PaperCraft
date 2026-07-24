"""Shared strict types used by every public artifact."""

from __future__ import annotations

from typing import Annotated, Iterable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    """Forbid silent contract drift and validate mutations in tests/tools."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


SchemaVersion = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

PaperId = Annotated[str, StringConstraints(pattern=r"^ppr_[a-z0-9_]+$")]
SourceSectionId = Annotated[str, StringConstraints(pattern=r"^srcsec_[a-z0-9_]+$")]
SourceBlockId = Annotated[str, StringConstraints(pattern=r"^srcblk_[a-z0-9_]+$")]
SourceEquationId = Annotated[str, StringConstraints(pattern=r"^seq_[a-z0-9_]+$")]
SourceAssetId = Annotated[str, StringConstraints(pattern=r"^ast_[a-z0-9_]+$")]
SourceRefId = Annotated[str, StringConstraints(pattern=r"^src_[a-z0-9_]+$")]

ConceptId = Annotated[str, StringConstraints(pattern=r"^cpt_[a-z0-9_]+$")]
ClaimId = Annotated[str, StringConstraints(pattern=r"^clm_[a-z0-9_]+$")]
MethodId = Annotated[str, StringConstraints(pattern=r"^mth_[a-z0-9_]+$")]
EquationId = Annotated[str, StringConstraints(pattern=r"^eq_[a-z0-9_]+$")]
ExperimentId = Annotated[str, StringConstraints(pattern=r"^exp_[a-z0-9_]+$")]
ResultId = Annotated[str, StringConstraints(pattern=r"^res_[a-z0-9_]+$")]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^ev_[a-z0-9_]+$")]
EdgeId = Annotated[str, StringConstraints(pattern=r"^edge_[a-z0-9_]+$")]
ComponentId = Annotated[str, StringConstraints(pattern=r"^cmp_[a-z0-9_]+$")]
ReviewId = Annotated[str, StringConstraints(pattern=r"^rev_[a-z0-9_]+$")]
IssueId = Annotated[str, StringConstraints(pattern=r"^issue_[a-z0-9_]+$")]
PatchId = Annotated[str, StringConstraints(pattern=r"^patch_[a-z0-9_]+$")]

Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


T = TypeVar("T")


def ensure_unique(values: Iterable[T], label: str) -> None:
    """Raise a model validation error when stable IDs are duplicated."""

    items = list(values)
    if len(items) != len(set(items)):
        raise ValueError(f"duplicate {label}")

