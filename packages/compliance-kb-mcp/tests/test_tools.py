"""Tool behavior tests for compliance-kb-mcp."""

from __future__ import annotations

from compliance_kb_mcp.data import CONTROLS
from compliance_kb_mcp.tools import (
    list_controls,
    lookup_by_soc2_tsc,
    lookup_control,
    search_controls,
)


def test_lookup_control_hit_returns_canonical_text() -> None:
    control = lookup_control("AC-1")
    assert control is not None
    assert control.id == "AC-1"
    assert control.title == "Policy and Procedures"
    assert "access control policy" in control.statement.lower()
    assert control.family_id == "ac"
    assert control.family_name == "Access Control"


def test_lookup_control_hit_uppercases_input() -> None:
    control = lookup_control("ac-1")
    assert control is not None
    assert control.id == "AC-1"


def test_lookup_control_miss() -> None:
    assert lookup_control("ZZ-99") is None
    assert lookup_control("AC-9999") is None


def test_lookup_sc7_text_matches_published_nist() -> None:
    control = lookup_control("SC-7")
    assert control is not None
    assert control.title == "Boundary Protection"
    assert "managed interface" in control.statement.lower()
    assert "CC6.6" in control.soc2_tsc_mappings


def test_lookup_ia2_text_matches_published_nist() -> None:
    control = lookup_control("IA-2")
    assert control is not None
    assert control.title.startswith("Identification and Authentication")
    assert "uniquely identify" in control.statement.lower()
    assert "CC6.1" in control.soc2_tsc_mappings


def test_lookup_by_soc2_tsc_returns_expected_controls() -> None:
    cc61 = lookup_by_soc2_tsc("CC6.1")
    cc61_ids = {c.id for c in cc61}
    assert {"AC-2", "AC-3", "IA-2", "SC-7"}.issubset(cc61_ids)

    cc66 = lookup_by_soc2_tsc("CC6.6")
    cc66_ids = {c.id for c in cc66}
    assert "SC-7" in cc66_ids


def test_lookup_by_soc2_tsc_unknown_returns_empty_list() -> None:
    assert lookup_by_soc2_tsc("CC9.9") == []


def test_search_controls_returns_relevant_hits_for_encryption() -> None:
    top_controls = search_controls("encryption at rest", k=5)
    assert top_controls
    top_ids = [control.id for control in top_controls]
    assert any(cid in top_ids for cid in {"SC-12", "SC-13", "SC-28", "MP-5"})


def test_search_controls_returns_relevant_hits_for_boundary() -> None:
    top_controls = search_controls("boundary protection firewall", k=5)
    top_ids = [control.id for control in top_controls]
    assert "SC-7" in top_ids


def test_search_controls_query_with_no_matches_is_empty() -> None:
    assert search_controls("zzzqqq fzzbar wkkkstring qpwoeiruty", k=3) == []


def test_list_controls_returns_full_catalog_when_unfiltered() -> None:
    summaries = list_controls()
    assert len(summaries) == len(CONTROLS) == 324
    assert summaries[0].id.startswith("AC-")


def test_list_controls_filters_by_family() -> None:
    summaries = list_controls(family_id="ac")
    assert len(summaries) == 25
    assert all(s.family_id == "ac" for s in summaries)
    assert summaries[0].id == "AC-1"


def test_list_controls_returns_empty_on_unknown_family() -> None:
    assert list_controls(family_id="zz") == []


def test_controls_no_longer_use_legacy_soc2_framework_id() -> None:
    for control in CONTROLS:
        assert control.framework == "nist_800_53_rev5"
        assert control.id != "CC1.1"


def test_no_unsubstituted_oscal_param_placeholders() -> None:
    import re

    pattern = re.compile(r"\{\{\s*insert:\s*param", re.IGNORECASE)
    offenders: list[tuple[str, str]] = []
    for control in CONTROLS:
        fields: dict[str, str] = {
            "statement": control.statement,
            "guidance": control.guidance or "",
        }
        for index, objective in enumerate(control.assessment_objectives):
            fields[f"assessment_objectives[{index}]"] = objective
        for field_name, text in fields.items():
            if pattern.search(text):
                offenders.append((control.id, field_name))
    assert not offenders, (
        "Unsubstituted '{{ insert: param ... }}' placeholders remain in the "
        "NIST 800-53 dataset; rerun scripts/build_dataset.py and confirm "
        "_substitute_params iterates to a fixed point. "
        f"Offenders ({len(offenders)} total, first 10): {offenders[:10]}"
    )
