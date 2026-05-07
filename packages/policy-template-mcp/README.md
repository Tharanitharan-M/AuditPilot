# policy-template-mcp

MCP server for SOC 2 readiness policy template rendering. Part of the [AuditPilot](https://github.com/Tharanitharan-M/auditpilot) reference architecture.

## What it does

Provides three MCP tools that let an LLM agent list, inspect, and render policy templates with live compliance control citations:

- **list_templates** — returns summaries of all available policy templates
- **get_template** — retrieves a single template by policy type
- **render_template** — fills Jinja2 citation slots (`{{ controls.CC7_1 }}`) with control assessment data and returns the rendered Markdown plus a list of unfilled slots

## Supported policy types

| Type | Title | SOC 2 TSC refs |
|------|-------|---------------|
| `irp` | Incident Response Plan | CC7.1 -- CC7.4 |
| `access_control` | Access Control Policy | CC6.1 -- CC6.8 |
| `change_management` | Change Management Policy | CC8.1 |
| `vendor_management` | Vendor Management Policy | CC9.1 -- CC9.2 |

## Installation

```bash
pip install policy-template-mcp
```

Or from source (development):

```bash
cd packages/policy-template-mcp
pip install -e ".[dev]"
```

## Usage

### As an MCP server (stdio transport)

```bash
policy-template-mcp
```

### As a Python library (in-process)

```python
from policy_template_mcp.tools import get_template, render_template, list_templates

templates = list_templates()

rendered = render_template("irp", {
    "CC7_1": "CC7.1 (passing, confidence 0.92) -- NIST refs: IR-4, IR-5",
})
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## Architecture

- **Pydantic v2 schemas** with `extra="forbid"` for strict MCP tool input/output validation
- **Jinja2 templates** with `KeepUndefined` so unfilled citation slots show default text instead of raising errors
- **FastMCP** server with stdio transport (MCP spec 2025-11-25)

## License

Apache-2.0. See [LICENSE](../../LICENSE).
