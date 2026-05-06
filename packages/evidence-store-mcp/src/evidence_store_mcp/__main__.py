"""Entry point for `python -m evidence_store_mcp` and the CLI script.

The MCP Python SDK exposes stdio transport via the
``mcp.server.stdio.stdio_server()`` async context manager rather than a
``Server.run_stdio_async`` shortcut. We open that context, hand the read /
write streams to ``Server.run``, and pass ``create_initialization_options()``
so the version + instructions set in ``server.py`` reach the handshake.
"""

import asyncio
import os

from mcp.server.stdio import stdio_server

from evidence_store_mcp.server import create_server


async def _run() -> None:
    server = create_server(
        db_url=os.environ["DATABASE_URL"],
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
