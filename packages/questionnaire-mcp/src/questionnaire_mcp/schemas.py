"""Pydantic v2 schemas for questionnaire-mcp (Sprint 7 chunk 7.1).

Every schema uses ``extra="forbid"`` so ``model_json_schema()`` produces
``additionalProperties: false`` — required by the mcp-server-validator.

Refs: PLAN.md chunks 7.1-7.5; ADR-0005; system-design 3.4.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionnaireFormat = Literal["sig-lite", "custom"]
"""Supported questionnaire formats. SIG-Lite is the v2026 industry-standard form."""

QuestionDomain = Literal[
    "access_control",
    "asset_management",
    "business_resiliency",
    "compliance",
    "data_handling",
    "endpoint_security",
    "human_resources",
    "incident_response",
    "network_security",
    "operations_management",
    "risk_management",
    "third_party_management",
    "training_and_awareness",
    "uncategorized",
]
"""SIG-Lite domain taxonomy. Maps to the 12-19 domains in v2026."""

AnswerType = Literal[
    "yes_no",
    "yes_no_partial",
    "free_text",
    "multi_select",
    "numeric",
    "date",
    "unknown",
]
"""Expected answer type for a questionnaire cell."""


class Question(BaseModel):
    """A single parsed questionnaire question."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable question id (e.g. SIG-Lite cell ref like 'A.1.1').")
    sheet: str = Field(description="Worksheet name in the source XLSX.")
    row: int = Field(ge=1, description="1-based row index in the source sheet.")
    column: int = Field(ge=1, description="1-based column index where the answer goes.")
    section: str = Field(default="", description="Section heading the question appears under.")
    domain: QuestionDomain = Field(
        default="uncategorized",
        description="SIG-Lite domain classification.",
    )
    text: str = Field(description="The question text as parsed.")
    answer_type: AnswerType = Field(
        default="unknown", description="Expected answer type for this cell."
    )


class ParsedQuestionnaire(BaseModel):
    """Result of ``parse_xlsx``."""

    model_config = ConfigDict(extra="forbid")

    file_uri: str = Field(description="Source URI (file path or R2 key).")
    format: QuestionnaireFormat = Field(description="Detected questionnaire format.")
    sheet_count: int = Field(ge=0, description="Number of sheets parsed.")
    question_count: int = Field(ge=0, description="Total questions extracted.")
    questions: list[Question] = Field(default_factory=list)


class Cluster(BaseModel):
    """A group of related questions that share retrieval context."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable cluster id, e.g. 'cluster_access_control'.")
    domain: QuestionDomain
    label: str = Field(description="Human-readable cluster label.")
    question_ids: list[str] = Field(
        default_factory=list, description="IDs of the questions in this cluster."
    )
    size: int = Field(ge=0, description="Number of questions in the cluster.")


class ClusterResult(BaseModel):
    """Result of ``cluster_questions``."""

    model_config = ConfigDict(extra="forbid")

    cluster_count: int = Field(ge=0)
    clusters: list[Cluster] = Field(default_factory=list)


class QuestionMetadata(BaseModel):
    """Metadata about one parsed question, used by retrieval and drafting."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    section: str = ""
    domain: QuestionDomain = "uncategorized"
    answer_type: AnswerType = "unknown"


class MetadataResult(BaseModel):
    """Result of ``extract_question_metadata``."""

    model_config = ConfigDict(extra="forbid")

    metadata_count: int = Field(ge=0)
    items: list[QuestionMetadata] = Field(default_factory=list)


class Citation(BaseModel):
    """Citation attached to an answer cell as a comment."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(description="Stable evidence row id (UUID or hash).")
    snippet: str = Field(default="", description="Optional short context snippet.")
    source_uri: str = Field(default="", description="Optional source URI for the evidence.")


class Answer(BaseModel):
    """An answer to a single question, with confidence and citations."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    sheet: str = Field(description="Worksheet name.")
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    text: str = Field(description="The drafted answer text.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Drafter confidence in [0, 1]. Cells with < 0.70 are flagged.",
    )
    citations: list[Citation] = Field(default_factory=list)


class AssembleResult(BaseModel):
    """Result of ``assemble_filled_xlsx``."""

    model_config = ConfigDict(extra="forbid")

    output_uri: str = Field(description="Local file path or R2 key for the assembled XLSX.")
    answers_written: int = Field(ge=0)
    flagged_count: int = Field(
        ge=0, description="Count of cells written but flagged (confidence < 0.70)."
    )
    sheet_count: int = Field(ge=0)


__all__ = [
    "Answer",
    "AnswerType",
    "AssembleResult",
    "Citation",
    "Cluster",
    "ClusterResult",
    "MetadataResult",
    "ParsedQuestionnaire",
    "Question",
    "QuestionDomain",
    "QuestionMetadata",
    "QuestionnaireFormat",
]
