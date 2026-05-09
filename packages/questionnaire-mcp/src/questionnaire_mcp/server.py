"""FastMCP server for questionnaire-mcp (Sprint 7 chunk 7.1).

Exposes four tools over stdio MCP transport:

  - parse_xlsx(file_uri)              -> ParsedQuestionnaire
  - cluster_questions(parsed)         -> ClusterResult
  - extract_question_metadata(parsed) -> MetadataResult
  - assemble_filled_xlsx(answers, source_uri, output_uri) -> AssembleResult

Refs: PLAN.md chunks 7.1-7.5; ADR-0005; system-design 3.4.
"""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from questionnaire_mcp.schemas import (
    Answer,
    AssembleResult,
    ClusterResult,
    MetadataResult,
    ParsedQuestionnaire,
)
from questionnaire_mcp.tools import (
    assemble_filled_xlsx as _assemble_filled_xlsx,
)
from questionnaire_mcp.tools import (
    cluster_questions as _cluster_questions,
)
from questionnaire_mcp.tools import (
    extract_question_metadata as _extract_question_metadata,
)
from questionnaire_mcp.tools import (
    parse_xlsx as _parse_xlsx,
)

mcp = FastMCP(
    "questionnaire-mcp",
    description=(
        "Security questionnaire parser and auto-fill MCP server. "
        "Parses SIG-Lite XLSX into typed questions, clusters by SIG-Lite domain, "
        "extracts metadata for retrieval, and assembles filled XLSX with citation comments."
    ),
)


@mcp.tool()
async def parse_xlsx(file_uri: str) -> ParsedQuestionnaire:
    """Parse a SIG-Lite or custom questionnaire XLSX into a list of questions.

    The SIG-Lite v2026 fixture is expected to parse to exactly 128 questions (FR-030).
    Returns the format, sheet count, question count, and the questions array.
    """
    return await asyncio.to_thread(_parse_xlsx, file_uri)


@mcp.tool()
async def cluster_questions(parsed: ParsedQuestionnaire) -> ClusterResult:
    """Group parsed questions by SIG-Lite domain.

    The SIG-Lite v2026 fixture is expected to cluster into 12 plus or minus 2
    groups (FR-031). Each cluster contains the question ids that retrieval and
    drafting will run against in a single batch.
    """
    return await asyncio.to_thread(_cluster_questions, parsed)


@mcp.tool()
async def extract_question_metadata(parsed: ParsedQuestionnaire) -> MetadataResult:
    """Project per-question metadata: section, domain, expected answer type."""
    return await asyncio.to_thread(_extract_question_metadata, parsed)


@mcp.tool()
async def assemble_filled_xlsx(
    answers: list[Answer],
    source_uri: str,
    output_uri: str,
) -> AssembleResult:
    """Write answers back into the source XLSX as inline strings with citation comments.

    - Always writes ``xl_inline_string``, never a formula.
    - Citation evidence ids are attached as a cell comment.
    - Cells with confidence below 0.70 receive a ``Flagged`` mark in the
      adjacent column. Original formatting is preserved.
    """
    return await asyncio.to_thread(
        _assemble_filled_xlsx, answers, source_uri, output_uri
    )


def main() -> None:
    """CLI entrypoint — run the MCP server over stdio."""
    mcp.run(transport="stdio")


__all__ = ["main", "mcp"]
