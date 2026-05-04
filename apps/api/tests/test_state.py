"""
Tests for `AuditPilotState` and its component models.

Acceptance (PLAN.md chunk 2.4):
- state.model_dump() round-trips via model_validate()
- Every component model (Evidence, ControlAssessment, Finding) enforces
  extra="forbid" and refuses unknown keys.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from apps.api.state import (
    AuditPilotState,
    ControlAssessment,
    Evidence,
    Finding,
)


def test_state_round_trips_via_model_dump_and_validate():
    original = AuditPilotState(
        messages=[
            HumanMessage(content="run a readiness scan against my github org"),
            AIMessage(content="starting scan..."),
        ],
        evidence=[
            Evidence(
                id="ev-001",
                source_type="github",
                source_uri="github://owner/repo/settings/branches",
                raw={"require_pull_request_reviews": True},
                content_hash="deadbeef",
            ),
        ],
        control_map={
            "CC6.1": ControlAssessment(
                tsc_id="CC6.1",
                status="passing",
                confidence=0.87,
                nist_800_53_refs=["AC-4", "SC-7"],
                evidence_ids=["ev-001"],
                rationale="branch protection enforces required reviews",
            ),
        },
        adversarial_findings=[
            Finding(
                severity="medium",
                tsc_id="CC6.1",
                objection="require_pull_request_reviews does not imply dismiss_stale_reviews",
                recommended_next_step="enable dismiss stale reviews and re-scan",
            ),
        ],
        rejection_reasons=["not specific enough"],
        current_step="control_mapping",
        user_id="user_abc",
        scan_run_id="run_42",
        thread_id="thread_7",
    )

    dumped = original.model_dump()
    restored = AuditPilotState.model_validate(dumped)

    assert restored.current_step == "control_mapping"
    assert restored.user_id == "user_abc"
    assert len(restored.messages) == 2
    assert restored.messages[0].content == "run a readiness scan against my github org"
    assert isinstance(restored.messages[0], HumanMessage)
    assert isinstance(restored.messages[1], AIMessage)
    assert restored.evidence[0].content_hash == "deadbeef"
    assert restored.evidence[0].raw == {"require_pull_request_reviews": True}
    assert restored.control_map["CC6.1"].nist_800_53_refs == ["AC-4", "SC-7"]
    assert restored.adversarial_findings[0].severity == "medium"


def test_default_state_is_empty_and_valid():
    s = AuditPilotState()
    assert s.messages == []
    assert s.evidence == []
    assert s.control_map == {}
    assert s.adversarial_findings == []
    assert s.current_step == "init"
    # Default dump should also round-trip
    assert AuditPilotState.model_validate(s.model_dump()).current_step == "init"


def test_evidence_model_forbids_extra_keys():
    with pytest.raises(ValidationError):
        Evidence(
            id="ev-001",
            source_type="github",
            raw={"x": 1},
            content_hash="deadbeef",
            unknown_field="should be rejected",  # type: ignore[call-arg]
        )


def test_control_assessment_confidence_is_bounded():
    with pytest.raises(ValidationError):
        ControlAssessment(tsc_id="CC6.1", status="passing", confidence=1.5)


def test_finding_severity_enum():
    with pytest.raises(ValidationError):
        Finding(severity="catastrophic", objection="...")  # type: ignore[arg-type]
