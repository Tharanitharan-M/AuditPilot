# Changelog

All notable changes to `questionnaire-mcp` are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-05-07

### Added
- `parse_xlsx` tool: SIG-Lite or custom XLSX parsed into typed `ParsedQuestionnaire`
- `cluster_questions` tool: domain-based clustering (12 plus or minus 2 clusters on SIG-Lite v2026 fixture)
- `extract_question_metadata` tool: section + domain + answer-type projection
- `assemble_filled_xlsx` tool: inline-string write-back with citation comments, formula neutralization, and `Flagged` markers for confidence below 0.70
- Pydantic v2 input/output schemas with `extra="forbid"` on every model
- JSON Schema export from Pydantic models used as MCP tool `inputSchema`
- stdio transport via `fastmcp.FastMCP`
