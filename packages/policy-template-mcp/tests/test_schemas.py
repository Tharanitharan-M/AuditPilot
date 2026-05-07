"""Schema tests for policy-template-mcp (Sprint 6 chunk 6.4).

Verifies Pydantic v2 schemas produce ``additionalProperties: false``
in JSON Schema output, and that all four policy types are registered.
"""

from __future__ import annotations

import pytest

from policy_template_mcp.schemas import (
    POLICY_TYPE_TITLES,
    PolicyTemplate,
    PolicyTemplateSummary,
    RenderResult,
)


def test_policy_template_json_schema_extra_forbid():
    schema = PolicyTemplate.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_policy_template_summary_json_schema_extra_forbid():
    schema = PolicyTemplateSummary.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_render_result_json_schema_extra_forbid():
    schema = RenderResult.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_all_four_policy_types_in_titles():
    assert "irp" in POLICY_TYPE_TITLES
    assert "access_control" in POLICY_TYPE_TITLES
    assert "change_management" in POLICY_TYPE_TITLES
    assert "vendor_management" in POLICY_TYPE_TITLES
    assert len(POLICY_TYPE_TITLES) == 4


def test_policy_template_round_trip():
    t = PolicyTemplate(
        id="irp",
        policy_type="irp",
        title="Incident Response Plan",
        content="# IRP\n\nBody text.",
        soc2_tsc_refs=["CC7.1", "CC7.2"],
    )
    dumped = t.model_dump(mode="json")
    restored = PolicyTemplate.model_validate(dumped)
    assert restored.id == "irp"
    assert restored.soc2_tsc_refs == ["CC7.1", "CC7.2"]


def test_policy_template_rejects_extra_fields():
    with pytest.raises(Exception):
        PolicyTemplate(
            id="irp",
            policy_type="irp",
            title="IRP",
            content="x",
            extra_field="not_allowed",
        )
