# Changelog

All notable changes to `evidence-store-mcp` are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-05-06

### Added
- `search_evidence` tool: hybrid Gemini vector + BM25 full-text search over evidence rows
- `get_evidence_by_hash` tool: exact SHA-256 content-hash lookup (cache key for control-mapping)
- `list_scan_runs` tool: most-recent scan runs with evidence row counts
- Pydantic v2 input/output schemas with `extra="forbid"` on all models
- JSON Schema export from Pydantic models used as MCP tool `inputSchema`
- RLS enforcement via `set_config('app.current_user_id', ...)` on every query
- OTel span on every tool call
- stdio transport via `mcp.Server`
- `psycopg_pool.AsyncConnectionPool` lazy init on first tool call
