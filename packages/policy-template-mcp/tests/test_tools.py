"""Tool tests for policy-template-mcp (Sprint 6 chunks 6.4-6.8).

Covers:
  - get_template hit + miss paths
  - list_templates returns all 4
  - render_template fills citation slots correctly
  - render_template preserves defaults for unfilled slots
"""

from __future__ import annotations

import pytest

from policy_template_mcp.tools import (
    get_template,
    list_templates,
    render_template,
    render_template_full,
)


class TestGetTemplate:
    def test_irp_hit(self):
        t = get_template("irp")
        assert t is not None
        assert t.id == "irp"
        assert t.policy_type == "irp"
        assert t.title == "Incident Response Plan"
        assert "CC7" in " ".join(t.soc2_tsc_refs)
        assert len(t.content) > 100

    def test_access_control_hit(self):
        t = get_template("access_control")
        assert t is not None
        assert t.policy_type == "access_control"
        assert "CC6" in " ".join(t.soc2_tsc_refs)

    def test_change_management_hit(self):
        t = get_template("change_management")
        assert t is not None
        assert t.policy_type == "change_management"
        assert "CC8.1" in t.soc2_tsc_refs

    def test_vendor_management_hit(self):
        t = get_template("vendor_management")
        assert t is not None
        assert t.policy_type == "vendor_management"
        assert "CC9.1" in t.soc2_tsc_refs

    def test_miss_returns_none(self):
        assert get_template("nonexistent") is None

    def test_empty_string_returns_none(self):
        assert get_template("") is None


class TestListTemplates:
    def test_returns_four_templates(self):
        templates = list_templates()
        assert len(templates) == 4

    def test_all_types_present(self):
        templates = list_templates()
        types = {t.policy_type for t in templates}
        assert types == {"irp", "access_control", "change_management", "vendor_management"}

    def test_summaries_have_descriptions(self):
        for t in list_templates():
            assert t.description, f"Template {t.id} has empty description"


class TestRenderTemplate:
    def test_fills_citation_slot(self):
        rendered = render_template("irp", {
            "CC7_1": "CC7.1 (passing, confidence 0.92) — NIST refs: IR-4, IR-5",
        })
        assert "CC7.1 (passing" in rendered
        assert "IR-4" in rendered

    def test_unfilled_slots_keep_defaults(self):
        rendered = render_template("irp", {})
        assert "not yet assessed" in rendered

    def test_unknown_template_returns_empty(self):
        rendered = render_template("nonexistent", {})
        assert rendered == ""

    def test_multiple_slots_filled(self):
        ctx = {
            "CC6_1": "CC6.1 (passing)",
            "CC6_2": "CC6.2 (failing)",
            "CC6_3": "CC6.3 (partial)",
        }
        rendered = render_template("access_control", ctx)
        assert "CC6.1 (passing)" in rendered
        assert "CC6.2 (failing)" in rendered
        assert "CC6.3 (partial)" in rendered


class TestRenderTemplateFull:
    def test_returns_structured_result(self):
        result = render_template_full("irp", {})
        assert result.template_id == "irp"
        assert len(result.rendered_content) > 100
        assert len(result.unfilled_slots) > 0

    def test_filled_slots_reduce_unfilled_count(self):
        empty = render_template_full("irp", {})
        filled = render_template_full("irp", {
            "CC7_1": "CC7.1 (passing)",
            "CC7_2": "CC7.2 (passing)",
            "CC7_3": "CC7.3 (passing)",
            "CC7_4": "CC7.4 (passing)",
        })
        assert len(filled.unfilled_slots) < len(empty.unfilled_slots)
