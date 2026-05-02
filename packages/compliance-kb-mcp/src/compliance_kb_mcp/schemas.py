"""Pydantic schemas for compliance-kb-mcp."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FrameworkId = Literal["nist_800_53_rev5"]
ControlIdPattern = r"^[A-Z]{2}-\d+$"
TscIdPattern = r"^(?:CC|A|C|PI|P)\d+\.\d+$"
FamilyIdPattern = r"^[a-z]{2}$"


class StrictModel(BaseModel):
    """Base model that forbids unknown fields."""

    model_config = ConfigDict(extra="forbid")


class Framework(StrictModel):
    """Framework descriptor for the catalog."""

    id: FrameworkId
    name: str
    version: str
    description: str


class SourceCitation(StrictModel):
    """Traceable source attribution for a control payload."""

    publication: str = Field(description="Canonical publication name.")
    publication_version: str = Field(description="Catalog version reported in OSCAL metadata.")
    publication_doi: str = Field(description="DOI for the canonical NIST publication.")
    publication_url: str = Field(description="URL for the canonical NIST publication.")
    oscal_repository: str = Field(description="OSCAL content repository URL.")
    oscal_source_file: str = Field(description="OSCAL JSON source file URL.")
    oscal_version: str = Field(description="OSCAL spec version reported in source metadata.")
    oscal_last_modified: str = Field(description="OSCAL last-modified timestamp from source.")
    license: str = Field(description="Licensing terms of the source publication.")
    soc2_mapping_source: str = Field(
        description="Citation for the SOC 2 TSC mapping data attached to the control."
    )


class Control(StrictModel):
    """A normalized NIST 800-53 control record with SOC 2 TSC mappings."""

    id: str = Field(
        pattern=ControlIdPattern,
        description="NIST 800-53 base control identifier, for example 'AC-1', 'SC-7', 'IA-2'.",
    )
    framework: FrameworkId = Field(description="Framework identifier. Value: 'nist_800_53_rev5'.")
    family_id: str = Field(
        pattern=FamilyIdPattern,
        description="Lowercase NIST 800-53 family identifier, for example 'ac', 'sc', 'ia'.",
    )
    family_name: str = Field(description="NIST 800-53 family display name.")
    title: str = Field(description="Canonical NIST 800-53 control title.")
    statement: str = Field(description="Canonical NIST 800-53 control statement text.")
    guidance: str | None = Field(
        default=None,
        description="Canonical NIST 800-53 control discussion / guidance text.",
    )
    assessment_objectives: list[str] = Field(
        default_factory=list,
        description="Assessment objectives extracted from SP 800-53A linked content.",
    )
    soc2_tsc_mappings: list[str] = Field(
        default_factory=list,
        description=(
            "SOC 2 Trust Services Criteria identifiers (e.g. 'CC6.1', 'A1.2') "
            "that this 800-53 control helps satisfy. Mapping is informational; "
            "consult the AICPA TSC publication for canonical guidance."
        ),
    )
    source_citation: SourceCitation = Field(
        description="Attribution and citation metadata for this control payload."
    )


class ControlSummary(StrictModel):
    """UI-friendly subset of a control."""

    id: str = Field(
        pattern=ControlIdPattern,
        description="NIST 800-53 base control identifier, for example 'AC-1'.",
    )
    framework: FrameworkId = Field(description="Framework identifier. Value: 'nist_800_53_rev5'.")
    family_id: str = Field(pattern=FamilyIdPattern, description="Lowercase NIST 800-53 family id.")
    family_name: str = Field(description="NIST 800-53 family display name.")
    title: str = Field(description="Canonical NIST 800-53 control title.")
    soc2_tsc_mappings: list[str] = Field(
        default_factory=list,
        description="SOC 2 TSC identifiers satisfied (informational).",
    )


class LookupControlInput(StrictModel):
    control_id: str = Field(
        pattern=ControlIdPattern,
        description="NIST 800-53 base control identifier, for example 'AC-1' or 'SC-7'.",
    )


class SearchControlsInput(StrictModel):
    query: str = Field(
        min_length=1,
        description="Lexical search string used for BM25 scoring over control text.",
    )
    k: int = Field(default=5, ge=1, le=20, description="Maximum number of controls to return.")


class ListControlsInput(StrictModel):
    family_id: str | None = Field(
        default=None,
        pattern=FamilyIdPattern,
        description="Optional NIST 800-53 family filter, for example 'ac', 'sc', 'ia'.",
    )


class LookupBySoc2TscInput(StrictModel):
    tsc_id: str = Field(
        pattern=TscIdPattern,
        description=(
            "SOC 2 Trust Services Criteria identifier, for example 'CC6.1', "
            "'A1.2', 'C1.1', 'PI1.4', or 'P1.1'."
        ),
    )
