"""Schemas contract: JobMessage / JobType / JobResult (chunk 2.10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.jobs.schemas import JobMessage, JobResult, JobStatus, JobType


def test_job_type_enum_values_match_adr_0010() -> None:
    """ADR-0010 Job types lists five exact strings on the wire."""

    assert {t.value for t in JobType} == {
        "questionnaire.fill",
        "policy.finalize",
        "mock_audit.run",
        "drift.scan",
        "evidence.compact",
    }


def test_job_message_round_trips_via_model_dump() -> None:
    msg = JobMessage(
        type=JobType.QUESTIONNAIRE_FILL,
        user_id="user_abc",
        idempotency_key="sha:deadbeef",
        payload={"filename": "sig-lite.xlsx", "question_count": 128},
    )

    dumped = msg.model_dump()
    assert dumped["type"] == "questionnaire.fill"
    assert dumped["attempt"] == 1

    revived = JobMessage.model_validate(dumped)
    assert revived.type == JobType.QUESTIONNAIRE_FILL
    assert revived.payload["question_count"] == 128


def test_job_message_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JobMessage.model_validate(
            {
                "type": "drift.scan",
                "user_id": "u1",
                "idempotency_key": "k1",
                "attempt": 1,
                "payload": {},
                "secret": "oops",  # extra
            }
        )
    assert "secret" in str(exc_info.value)


def test_job_message_requires_non_empty_user_id_and_key() -> None:
    with pytest.raises(ValidationError):
        JobMessage(
            type=JobType.DRIFT_SCAN,
            user_id="",
            idempotency_key="k1",
        )
    with pytest.raises(ValidationError):
        JobMessage(
            type=JobType.DRIFT_SCAN,
            user_id="u1",
            idempotency_key="",
        )


def test_job_result_deduplicated_flag_defaults_false() -> None:
    result = JobResult(message_id="1-0")
    assert result.deduplicated is False


def test_job_status_enum_values() -> None:
    assert JobStatus.QUEUED.value == "queued"
    assert JobStatus.DEAD_LETTERED.value == "dead_lettered"
