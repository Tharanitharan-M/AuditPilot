"""FastMCP server for compliance-kb-mcp."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from compliance_kb_mcp.schemas import (
    Control,
    ControlSummary,
    ListControlsInput,
    LookupBySoc2TscInput,
    LookupControlInput,
    SearchControlsInput,
)
from compliance_kb_mcp.tools import (
    list_controls as list_controls_impl,
)
from compliance_kb_mcp.tools import (
    lookup_by_soc2_tsc as lookup_by_soc2_tsc_impl,
)
from compliance_kb_mcp.tools import (
    lookup_control as lookup_control_impl,
)
from compliance_kb_mcp.tools import (
    search_controls as search_controls_impl,
)

mcp = FastMCP("compliance-kb-mcp")


@mcp.tool()
async def lookup_control(
    control_id: Annotated[
        str,
        Field(
            pattern=r"^[A-Z]{2}-\d+$",
            description="NIST 800-53 base control identifier, for example 'AC-1' or 'SC-7'.",
        ),
    ],
) -> Control | None:
    """Look up a NIST 800-53 Rev 5 control by its base identifier."""

    payload = LookupControlInput(control_id=control_id)
    return lookup_control_impl(payload.control_id)


@mcp.tool()
async def lookup_by_soc2_tsc(
    tsc_id: Annotated[
        str,
        Field(
            pattern=r"^(?:CC|A|C|PI|P)\d+\.\d+$",
            description=(
                "SOC 2 Trust Services Criteria identifier, for example 'CC6.1', "
                "'A1.2', 'C1.1', 'PI1.4', or 'P1.1'."
            ),
        ),
    ],
) -> list[Control]:
    """Return the NIST 800-53 controls mapped to a SOC 2 Trust Services Criteria identifier."""

    payload = LookupBySoc2TscInput(tsc_id=tsc_id)
    return lookup_by_soc2_tsc_impl(payload.tsc_id)


@mcp.tool()
async def search_controls(
    query: Annotated[
        str,
        Field(
            min_length=1,
            description="Lexical query used for BM25 search over NIST 800-53 control text.",
        ),
    ],
    k: Annotated[int, Field(ge=1, le=20, description="Maximum number of controls to return.")] = 5,
) -> list[Control]:
    """Search NIST 800-53 controls with naive BM25 lexical ranking."""

    payload = SearchControlsInput(query=query, k=k)
    return search_controls_impl(payload.query, payload.k)


@mcp.tool()
async def list_controls(
    family_id: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^[a-z]{2}$",
            description="Optional NIST 800-53 family filter, for example 'ac', 'sc', 'ia'.",
        ),
    ] = None,
) -> list[ControlSummary]:
    """List NIST 800-53 controls as summaries; optionally filter by family identifier."""

    payload = ListControlsInput(family_id=family_id)
    return list_controls_impl(payload.family_id)


def main() -> None:
    """Run the server over stdio transport."""

    mcp.run()


if __name__ == "__main__":
    main()
