"""Policy template tools (Sprint 6 chunk 6.4).

Pure-function tools consumed by the MCP server and by the orchestrator's
``draft_policy_node`` via direct import. No network calls, no state — all
data lives in the ``templates/`` directory shipped with the package.

Refs: PLAN.md chunk 6.4; ADR-0005; system-design 3.3.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources

from jinja2 import BaseLoader, Environment, TemplateSyntaxError, Undefined

from policy_template_mcp.schemas import (
    PolicyTemplate,
    PolicyTemplateSummary,
    RenderResult,
)

_TEMPLATE_REGISTRY: dict[str, dict] = {
    "irp": {
        "policy_type": "irp",
        "title": "Incident Response Plan",
        "description": (
            "Procedures for identifying, containing, "
            "and recovering from security incidents."
        ),
        "version": "1.0",
        "soc2_tsc_refs": ["CC7.1", "CC7.2", "CC7.3", "CC7.4"],
        "file": "irp.md",
    },
    "access_control": {
        "policy_type": "access_control",
        "title": "Access Control Policy",
        "description": (
            "Requirements for controlling logical and "
            "physical access to information systems."
        ),
        "version": "1.0",
        "soc2_tsc_refs": ["CC6.1", "CC6.2", "CC6.3", "CC6.6", "CC6.7", "CC6.8"],
        "file": "access_control.md",
    },
    "change_management": {
        "policy_type": "change_management",
        "title": "Change Management Policy",
        "description": (
            "Requirements for managing changes to "
            "information systems and infrastructure."
        ),
        "version": "1.0",
        "soc2_tsc_refs": ["CC8.1"],
        "file": "change_management.md",
    },
    "vendor_management": {
        "policy_type": "vendor_management",
        "title": "Vendor Management Policy",
        "description": (
            "Requirements for evaluating, monitoring, "
            "and offboarding third-party vendors."
        ),
        "version": "1.0",
        "soc2_tsc_refs": ["CC9.1", "CC9.2"],
        "file": "vendor_management.md",
    },
}


@lru_cache(maxsize=4)
def _load_template_content(template_id: str) -> str:
    """Read a template file from the package's ``templates/`` directory."""

    entry = _TEMPLATE_REGISTRY.get(template_id)
    if entry is None:
        return ""
    filename = entry["file"]
    try:
        pkg = resources.files("policy_template_mcp") / "templates" / filename
        return pkg.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def get_template(policy_type: str) -> PolicyTemplate | None:
    """Look up a policy template by type. Returns None on miss."""

    entry = _TEMPLATE_REGISTRY.get(policy_type)
    if entry is None:
        return None
    content = _load_template_content(policy_type)
    return PolicyTemplate(
        id=policy_type,
        policy_type=entry["policy_type"],
        title=entry["title"],
        description=entry["description"],
        content=content,
        version=entry["version"],
        soc2_tsc_refs=entry["soc2_tsc_refs"],
    )


def list_templates() -> list[PolicyTemplateSummary]:
    """Return summaries of all available policy templates."""

    return [
        PolicyTemplateSummary(
            id=tid,
            policy_type=entry["policy_type"],
            title=entry["title"],
            description=entry["description"],
            version=entry["version"],
            soc2_tsc_refs=entry["soc2_tsc_refs"],
        )
        for tid, entry in _TEMPLATE_REGISTRY.items()
    ]


def render_template(template_id: str, context: dict[str, str] | None = None) -> str:
    """Render a policy template with the given context values.

    Context keys map to Jinja2 slot names. For example::

        context = {"CC7_1": "CC7.1 (passing, confidence 0.85) — NIST refs: IR-4, IR-5"}

    fills ``{{ controls.CC7_1 }}`` in the template.

    Returns the rendered Markdown string. Unfilled slots keep their
    default values (e.g. ``[CC7.1 — not yet assessed]``).
    """

    raw_content = _load_template_content(template_id)
    if not raw_content:
        return ""

    ctx = context or {}
    # Wrap flat context into a ``controls`` namespace so templates
    # can use ``{{ controls.CC7_1 }}`` syntax.
    controls_ns: dict[str, str] = {}
    for key, value in ctx.items():
        controls_ns[key] = value

    jinja_ctx = {
        "controls": controls_ns,
        "version": ctx.get("version", "1.0"),
        "date": ctx.get("date", ""),
        "owner": ctx.get("owner", ""),
    }

    try:
        env = Environment(loader=BaseLoader(), undefined=_KeepUndefined)
        tmpl = env.from_string(raw_content)
        return tmpl.render(**jinja_ctx)
    except TemplateSyntaxError:
        return raw_content


class _KeepUndefined(Undefined):
    """Jinja2 undefined that preserves the default filter value.

    When a slot like ``{{ controls.CC7_1 | default("[CC7.1]") }}`` has no
    matching context key, Jinja2's default ``Undefined`` raises. This
    subclass silently returns an empty string so the ``| default(...)``
    filter can supply the fallback text.
    """

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False

    def _fail_with_undefined_error(self, *args, **kwargs):
        return ""

    def __getattr__(self, name: str) -> _KeepUndefined:
        if name.startswith("_"):
            raise AttributeError(name)
        return _KeepUndefined(name=name)


def render_template_full(template_id: str, context: dict[str, str] | None = None) -> RenderResult:
    """Render and return a structured result with unfilled slot tracking."""

    raw_content = _load_template_content(template_id)
    if not raw_content:
        return RenderResult(template_id=template_id, rendered_content="", unfilled_slots=[])

    rendered = render_template(template_id, context)

    # Detect unfilled slots by finding remaining default markers.
    unfilled = re.findall(r"\[([A-Z]{2}\d\.\d) — not yet assessed\]", rendered)

    return RenderResult(
        template_id=template_id,
        rendered_content=rendered,
        unfilled_slots=unfilled,
    )


__all__ = [
    "get_template",
    "list_templates",
    "render_template",
    "render_template_full",
]
