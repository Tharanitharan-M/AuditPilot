# evidence-store-mcp

MCP server for the AuditPilot evidence store. Exposes three tools for semantic and keyword search over collected evidence rows persisted in Neon Postgres with pgvector.

## Tools

| Tool | Description |
|---|---|
| `search_evidence` | Hybrid vector + BM25 search over collected evidence rows |
| `get_evidence_by_hash` | Exact lookup by SHA-256 content hash (cache key) |
| `list_scan_runs` | Most-recent scan runs with evidence counts |

## Prerequisites

- Python 3.11+
- Neon Postgres with `vector` extension (migration `0005_evidence.sql`)
- Optional: `GEMINI_API_KEY` for semantic vector search

## Installation

```bash
pip install evidence-store-mcp
```

## Usage

```bash
DATABASE_URL=postgresql://... GEMINI_API_KEY=... evidence-store-mcp
```

Or as a subprocess-launched MCP server in a `pydantic_ai.mcp.MCPServerStdio` context.

## Development

```bash
cd packages/evidence-store-mcp
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
