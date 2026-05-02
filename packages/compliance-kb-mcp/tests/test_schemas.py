"""Schema tests for compliance-kb-mcp."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compliance_kb_mcp.data import (
    CONTROLS,
    CONTROLS_BY_FAMILY,
    CONTROLS_BY_TSC,
    FRAMEWORKS,
)
from compliance_kb_mcp.schemas import (
    Control,
    Framework,
    LookupBySoc2TscInput,
    LookupControlInput,
)

EXPECTED_FAMILIES = {
    "ac",
    "at",
    "au",
    "ca",
    "cm",
    "cp",
    "ia",
    "ir",
    "ma",
    "mp",
    "pe",
    "pl",
    "pm",
    "ps",
    "pt",
    "ra",
    "sa",
    "sc",
    "si",
    "sr",
}


def test_control_schema_is_locked_down() -> None:
    schema = Control.model_json_schema()
    assert schema["additionalProperties"] is False


def test_framework_schema_is_locked_down() -> None:
    schema = Framework.model_json_schema()
    assert schema["additionalProperties"] is False


def test_lookup_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LookupControlInput(control_id="AC-1", extra_field="nope")


def test_lookup_by_tsc_input_validates_tsc_pattern() -> None:
    LookupBySoc2TscInput(tsc_id="CC6.1")
    LookupBySoc2TscInput(tsc_id="A1.2")
    LookupBySoc2TscInput(tsc_id="PI1.4")
    LookupBySoc2TscInput(tsc_id="P1.1")
    with pytest.raises(ValidationError):
        LookupBySoc2TscInput(tsc_id="lowercase")


def test_control_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Control(
            id="AC-1",
            framework="nist_800_53_rev5",
            family_id="ac",
            family_name="Access Control",
            title="Policy and Procedures",
            statement="...",
            guidance=None,
            assessment_objectives=[],
            soc2_tsc_mappings=["CC5.3"],
            source_citation={
                "publication": "NIST SP 800-53 Rev 5",
                "publication_version": "5.2.0",
                "publication_doi": "https://doi.org/10.6028/NIST.SP.800-53r5",
                "publication_url": "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final",
                "oscal_repository": "https://github.com/usnistgov/oscal-content",
                "oscal_source_file": "https://example.com/catalog.json",
                "oscal_version": "1.1.3",
                "oscal_last_modified": "2025-08-26T14:33:16.00000-00:00",
                "license": "Public domain (federal government work)",
                "soc2_mapping_source": "Curated from publicly available crosswalks.",
            },
            extra_field="nope",
        )


def test_framework_registry_and_control_count() -> None:
    assert "nist_800_53_rev5" in FRAMEWORKS
    assert len(CONTROLS) == 324


def test_lookup_input_accepts_nist_identifiers() -> None:
    LookupControlInput(control_id="AC-1")
    LookupControlInput(control_id="SC-7")
    LookupControlInput(control_id="IA-2")
    LookupControlInput(control_id="PT-1")


def test_all_controls_have_complete_source_citations() -> None:
    for control in CONTROLS:
        citation = control.source_citation
        assert citation.publication.startswith("NIST")
        assert citation.publication_doi.startswith("https://doi.org/")
        assert citation.license.lower().startswith("public domain")
        assert citation.oscal_source_file.startswith("https://")


def test_every_family_has_at_least_one_control() -> None:
    families_present = set(CONTROLS_BY_FAMILY.keys())
    assert families_present == EXPECTED_FAMILIES


def test_soc2_mappings_cover_core_common_criteria() -> None:
    for tsc_id in ["CC6.1", "CC6.6", "CC7.2", "CC7.4", "A1.2", "C1.1"]:
        assert tsc_id in CONTROLS_BY_TSC
        assert CONTROLS_BY_TSC[tsc_id], f"Expected at least one control mapped to {tsc_id}"
