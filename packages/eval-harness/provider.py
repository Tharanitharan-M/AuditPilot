"""Hermetic Python provider for Sprint 2 smoke evals.

Dispatches on a colon-delimited test name (e.g. ``lookup_control:AC-1``) to
the matching ``compliance_kb_mcp`` tool and prints a single-line string to
stdout that Promptfoo's ``exec`` provider captures verbatim.

No external LLM calls — the Sprint 2 gate only validates that the static
NIST 800-53 catalogue is correctly wired through the tool surface.

Usage:
    python3 packages/eval-harness/provider.py "lookup_control:AC-1"
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COMPLIANCE_KB_SRC = _PROJECT_ROOT / "packages" / "compliance-kb-mcp" / "src"
if str(_COMPLIANCE_KB_SRC) not in sys.path:
    sys.path.insert(0, str(_COMPLIANCE_KB_SRC))

from compliance_kb_mcp.tools import (  # noqa: E402 — path setup above
    list_controls,
    lookup_by_soc2_tsc,
    lookup_control,
    search_controls,
)


def _handle(prompt: str) -> str:
    if ":" not in prompt:
        return f"ERROR: malformed test case '{prompt}', expected 'tool:arg'"

    tool, _, argument = prompt.partition(":")
    tool = tool.strip()
    argument = argument.strip()

    if tool == "lookup_control":
        control = lookup_control(argument)
        if control is None:
            return "NONE"
        return f"id={control.id} title={control.title}"

    if tool == "lookup_by_soc2_tsc":
        controls = lookup_by_soc2_tsc(argument)
        ids = ",".join(c.id for c in controls)
        return f"count={len(controls)} ids={ids}"

    if tool == "search_controls":
        results = search_controls(argument, k=5)
        ids = ",".join(c.id for c in results)
        return f"top5={ids}"

    if tool == "list_controls":
        family = argument or None
        summaries = list_controls(family)
        return f"count={len(summaries)}"

    return f"ERROR: unknown tool '{tool}'"


def main() -> int:
    if len(sys.argv) < 2:
        print("ERROR: provider expects a single prompt argument", file=sys.stderr)
        return 2
    prompt = sys.argv[1]
    sys.stdout.write(_handle(prompt))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
