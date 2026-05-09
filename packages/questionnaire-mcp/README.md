# questionnaire-mcp

MCP server for parsing and assembling security questionnaires (SIG-Lite v2026 and similar XLSX forms) for AuditPilot. Used by the orchestrator to clusterize questions by domain, retrieve evidence per cluster, and write back drafted answers with citation comments.

## Tools

| Tool | Description |
|---|---|
| `parse_xlsx` | Parse a SIG-Lite or custom XLSX into a typed `ParsedQuestionnaire` |
| `cluster_questions` | Group parsed questions by SIG-Lite domain (12 plus or minus 2 clusters per FR-031) |
| `extract_question_metadata` | Project per-question metadata: section, domain, expected answer type |
| `assemble_filled_xlsx` | Write answers back as inline strings with citation comments and `Flagged` markers |

## Prerequisites

- Python 3.11+
- `openpyxl` for XLSX I/O
- No database, no network — all tools operate on local file paths

## Installation

```bash
pip install questionnaire-mcp
```

## Usage

```bash
questionnaire-mcp
```

Or as a subprocess-launched MCP server in a `pydantic_ai.mcp.MCPServerStdio` context.

```python
from pydantic_ai.mcp import MCPServerStdio

server = MCPServerStdio(
    command="python",
    args=["-m", "questionnaire_mcp"],
    id="questionnaire_mcp",
)
```

## Tool semantics

### `parse_xlsx(file_uri)`

- Detects `sig-lite` vs `custom` format from sheet names.
- A SIG-Lite v2026 fixture parses to exactly 128 questions (FR-030).
- Each question gets a stable id (`sheet!RxCy`), section, domain, and inferred answer type.

### `cluster_questions(parsed)`

- Groups by SIG-Lite domain (`access_control`, `data_handling`, etc.).
- A SIG-Lite v2026 fixture clusters into 12 plus or minus 2 groups (FR-031).

### `extract_question_metadata(parsed)`

- One `QuestionMetadata` per question: id, section, domain, answer type.

### `assemble_filled_xlsx(answers, source_uri, output_uri)`

- Always writes inline strings (`xl_inline_string`); never a formula. A leading `=` is neutralized with a leading space.
- Each citation evidence id is attached to the cell as a comment.
- Cells with `confidence < 0.70` get a `Flagged` mark in the adjacent column.
- Original formatting and column widths are preserved by openpyxl when the workbook is loaded read-write.

## Development

```bash
cd packages/questionnaire-mcp
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
