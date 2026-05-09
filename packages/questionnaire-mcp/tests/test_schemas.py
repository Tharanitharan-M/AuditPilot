"""Schema tests for questionnaire-mcp."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from questionnaire_mcp.schemas import (
    Answer,
    AssembleResult,
    Citation,
    Cluster,
    ClusterResult,
    MetadataResult,
    ParsedQuestionnaire,
    Question,
    QuestionMetadata,
)


class TestQuestion:
    def test_minimal_construct(self) -> None:
        q = Question(
            id="A.1!R2C3",
            sheet="SIG-Lite",
            row=2,
            column=3,
            text="Do you require MFA?",
        )
        assert q.domain == "uncategorized"
        assert q.answer_type == "unknown"

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            Question(
                id="x",
                sheet="s",
                row=1,
                column=1,
                text="t",
                unknown="boom",  # type: ignore[call-arg]
            )

    def test_row_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Question(id="x", sheet="s", row=0, column=1, text="t")


class TestParsedQuestionnaire:
    def test_default_questions_empty(self) -> None:
        p = ParsedQuestionnaire(
            file_uri="/tmp/x.xlsx",
            format="sig-lite",
            sheet_count=1,
            question_count=0,
        )
        assert p.questions == []


class TestClusterResult:
    def test_construct(self) -> None:
        c = Cluster(
            id="cluster_access_control",
            domain="access_control",
            label="Access Control",
            question_ids=["q1", "q2"],
            size=2,
        )
        result = ClusterResult(cluster_count=1, clusters=[c])
        assert result.cluster_count == 1
        assert result.clusters[0].size == 2


class TestMetadataResult:
    def test_construct(self) -> None:
        m = QuestionMetadata(
            question_id="q1",
            section="Access Control",
            domain="access_control",
            answer_type="yes_no",
        )
        result = MetadataResult(metadata_count=1, items=[m])
        assert result.items[0].domain == "access_control"


class TestAnswer:
    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Answer(
                question_id="q1",
                sheet="s",
                row=1,
                column=2,
                text="Yes",
                confidence=1.5,
            )

    def test_with_citations(self) -> None:
        a = Answer(
            question_id="q1",
            sheet="s",
            row=1,
            column=2,
            text="Yes",
            confidence=0.9,
            citations=[Citation(evidence_id="ev_1", snippet="s", source_uri="r2://k")],
        )
        assert a.citations[0].evidence_id == "ev_1"


class TestAssembleResult:
    def test_construct(self) -> None:
        r = AssembleResult(
            output_uri="/tmp/out.xlsx",
            answers_written=10,
            flagged_count=2,
            sheet_count=1,
        )
        assert r.flagged_count == 2
