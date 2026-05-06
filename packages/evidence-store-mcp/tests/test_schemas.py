"""Unit tests for evidence-store-mcp Pydantic schemas."""

import pytest
from pydantic import ValidationError

from evidence_store_mcp.schemas import (
    GetEvidenceByHashInput,
    ListScanRunsInput,
    SearchEvidenceInput,
)


class TestSearchEvidenceInput:
    def test_valid_minimal(self) -> None:
        inp = SearchEvidenceInput(query="branch protection", user_id="user_abc")
        assert inp.limit == 10
        assert inp.similarity_threshold == 0.5

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SearchEvidenceInput(query="", user_id="user_abc")

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SearchEvidenceInput(query="q", user_id="u", limit=0)
        with pytest.raises(ValidationError):
            SearchEvidenceInput(query="q", user_id="u", limit=51)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SearchEvidenceInput(query="q", user_id="u", injected_field="bad")  # type: ignore[call-arg]

    def test_source_type_optional(self) -> None:
        inp = SearchEvidenceInput(query="mfa", user_id="u", source_type="github")
        assert inp.source_type == "github"


class TestGetEvidenceByHashInput:
    VALID_HASH = "a" * 64

    def test_valid(self) -> None:
        inp = GetEvidenceByHashInput(content_hash=self.VALID_HASH, user_id="u")
        assert inp.content_hash == self.VALID_HASH

    def test_short_hash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetEvidenceByHashInput(content_hash="abc", user_id="u")

    def test_long_hash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GetEvidenceByHashInput(content_hash="a" * 65, user_id="u")


class TestListScanRunsInput:
    def test_defaults(self) -> None:
        inp = ListScanRunsInput(user_id="u")
        assert inp.limit == 20

    def test_limit_cap(self) -> None:
        with pytest.raises(ValidationError):
            ListScanRunsInput(user_id="u", limit=101)


class TestJsonSchemaGeneration:
    def test_search_evidence_schema(self) -> None:
        schema = SearchEvidenceInput.model_json_schema()
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "user_id" in schema["properties"]

    def test_get_by_hash_schema(self) -> None:
        schema = GetEvidenceByHashInput.model_json_schema()
        assert "content_hash" in schema["properties"]

    def test_list_scan_runs_schema(self) -> None:
        schema = ListScanRunsInput.model_json_schema()
        assert "user_id" in schema["properties"]
