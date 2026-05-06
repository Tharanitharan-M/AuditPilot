# compliance-kb-mcp

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![PyPI](https://img.shields.io/pypi/v/compliance-kb-mcp)](https://pypi.org/project/compliance-kb-mcp/)
[![npm](https://img.shields.io/npm/v/@auditpilot/compliance-kb-mcp)](https://www.npmjs.com/package/@auditpilot/compliance-kb-mcp)

`compliance-kb-mcp` is a typed MCP server that exposes the canonical
**NIST Special Publication 800-53 Revision 5** control catalog (324 base
controls across 20 families) over stdio transport. Each control is annotated
with the SOC 2 Trust Services Criteria identifiers it helps satisfy, derived
from publicly available crosswalks.

This package is part of the AuditPilot SOC 2 readiness reference architecture
and is designed to be easy to fork for other control catalogs.

## Why NIST 800-53?

- **Public domain.** NIST 800-53 is a U.S. federal government work and is in
  the public domain (17 U.S.C. 105). The full canonical control text can be
  redistributed without licensing concerns.
- **Machine-readable canonical source.** NIST publishes the catalog in OSCAL
  JSON, XML, and YAML at
  [usnistgov/oscal-content](https://github.com/usnistgov/oscal-content).
- **Well-mapped to SOC 2.** The AICPA publishes a TSC to 800-53 mapping
  (registration required); supplementary public crosswalks like the
  [Open Security Architecture project](https://opensecurityarchitecture.org/frameworks/soc2-tsc)
  make the relationship transparent.

## Positioning

> AuditPilot maps your environment to NIST 800-53 controls and shows which
> SOC 2 Trust Services Criteria are satisfied by your 800-53 coverage. The
> included `compliance-kb-mcp` ships with NIST 800-53 Rev 5 (public domain)
> and curated SOC 2 TSC mappings. For canonical SOC 2 TSC text, refer to
> AICPA-CIMA's published 2017 Trust Services Criteria -- that text is
> copyright-protected and is not redistributed in this package.

## Features

- Strict Pydantic v2 schemas with `extra="forbid"`.
- 324 NIST 800-53 Rev 5 base controls with parameter-substituted statements.
- Curated SOC 2 TSC to 800-53 mapping covering Common Criteria, Availability,
  Confidentiality, Processing Integrity, and Privacy clauses.
- Four MCP tools: `lookup_control`, `lookup_by_soc2_tsc`, `search_controls`,
  `list_controls`.
- Naive BM25 ranking for lexical search across statement, guidance, title, and
  family text.
- Zero external runtime dependencies beyond `mcp>=1.0` and `pydantic>=2.0`.

## Installation

### Python (for running the stdio MCP server)

```bash
pip install compliance-kb-mcp
```

Or with uv:

```bash
uv add compliance-kb-mcp
```

### npm / Node.js (thin shim that delegates to the Python server)

```bash
npm install -g @auditpilot/compliance-kb-mcp
```

Or run without installation via npx:

```bash
npx @auditpilot/compliance-kb-mcp
```

## MCP Client Configuration

Add the server to your MCP client config (e.g. Claude Desktop's
`claude_desktop_config.json`, or your project's `.mcp.json`).

**Using the installed Python package (recommended):**

```json
{
  "mcpServers": {
    "compliance-kb": {
      "command": "compliance-kb-mcp"
    }
  }
}
```

**Using uvx (no global install required):**

```json
{
  "mcpServers": {
    "compliance-kb": {
      "command": "uvx",
      "args": ["compliance-kb-mcp"]
    }
  }
}
```

**Using npx (Node shim delegates to Python):**

```json
{
  "mcpServers": {
    "compliance-kb": {
      "command": "npx",
      "args": ["-y", "@auditpilot/compliance-kb-mcp"]
    }
  }
}
```

> Note: The npx shim requires Python to be available on PATH. It spawns
> `python -m compliance_kb_mcp.server` using the `PYTHON` env var if set,
> otherwise falls back to `python`.

## Tool Reference

### `lookup_control`

- **Input:** `control_id: str` -- NIST 800-53 base identifier, e.g. `"AC-1"`
- **Output:** `Control | None`
- **Behavior:** Returns the canonical 800-53 control payload (title,
  statement, guidance, assessment objectives, SOC 2 TSC mappings, citation).
  Returns `null` if the identifier is not found.

### `lookup_by_soc2_tsc`

- **Input:** `tsc_id: str` -- SOC 2 TSC identifier, e.g. `"CC6.1"`, `"A1.2"`
- **Output:** `list[Control]`
- **Behavior:** Returns all 800-53 controls mapped to the given SOC 2 TSC.

### `search_controls`

- **Input:** `query: str`, `k: int` (1-20, default 5)
- **Output:** `list[Control]`
- **Behavior:** Returns top `k` BM25-ranked controls matching the query terms.

### `list_controls`

- **Input:** `family_id: str | None` -- e.g. `"ac"`, `"sc"`, `"ia"`
- **Output:** `list[ControlSummary]`
- **Behavior:** Lists all 324 controls (or scoped to a single family) as
  lightweight summaries including id, title, and SOC 2 TSC mappings.

## Local Development

```bash
# Install the package in editable mode with dev dependencies
uv sync --directory packages/compliance-kb-mcp

# Run tests
uv run --directory packages/compliance-kb-mcp pytest tests/

# Run the server locally (stdio transport)
uv run --directory packages/compliance-kb-mcp python -m compliance_kb_mcp
```

## Data Sources

- **Control catalog:** NIST Special Publication 800-53 Revision 5
  ([DOI 10.6028/NIST.SP.800-53r5](https://doi.org/10.6028/NIST.SP.800-53r5))
  via the OSCAL JSON catalog at
  [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content/blob/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json).
- **License:** Public domain (17 U.S.C. 105).
- **SOC 2 TSC mapping:** Curated from the AICPA-published
  [Mapping: 2017 Trust Services Criteria to NIST 800-53](https://www.aicpa-cima.com/resources/download/mapping-2017-trust-services-criteria-to-nist-800-53)
  (registration required) and the publicly available
  [Open Security Architecture SOC 2 TSC to SP 800-53 crosswalk](https://opensecurityarchitecture.org/frameworks/soc2-tsc).
- **SOC 2 TSC text:** Copyright AICPA. **Not redistributed in this package.**
  Refer to the AICPA-CIMA-published
  [2017 Trust Services Criteria (with revised points of focus - 2022)](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022)
  for canonical SOC 2 TSC criteria text.

### How to Refresh the Dataset When NIST Republishes the Catalog

1. Pull the latest catalog from `usnistgov/oscal-content`:
   ```bash
   curl -sL https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json \
       -o /tmp/nist_catalog.json
   ```
2. Regenerate the dataset:
   ```bash
   python scripts/build_dataset.py --oscal-source /tmp/nist_catalog.json
   ```
3. Re-run the test suite:
   ```bash
   uv run --directory packages/compliance-kb-mcp pytest tests/
   ```
4. Update `CHANGELOG.md` and the source citation `oscal_last_modified` line in
   the resulting JSON.

## How To Fork For Another Catalog

1. Copy `packages/compliance-kb-mcp` to a new package folder (for example
   `packages/iso-27001-kb-mcp` or `packages/cmmc-kb-mcp`).
2. Rename the Python package and npm metadata.
3. Replace `src/compliance_kb_mcp/data/nist_800_53_rev5_controls.json` with
   the new catalog (matching the `Control` Pydantic schema).
4. Update `Control.framework` literals and validation patterns in `schemas.py`.
5. Keep the tool signatures unchanged so existing LangGraph integrations
   continue to work.
6. Run tests and dry-run packaging:
   - `pytest tests/`
   - `npm pack --dry-run`
   - `uv build`

## License

Apache-2.0. See [LICENSE](./LICENSE).
