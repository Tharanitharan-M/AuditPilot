"""Pydantic v2 schema for a prompt YAML file.

One file per prompt per version:
``apps/api/agents/prompts/<name>/<label_or_version>.yaml``.

The canonical deployed version lives at ``<name>/production.yaml`` and is
what the runtime loader falls back to on a Langfuse outage.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PromptGuardrails(BaseModel):
    """Hard caps enforced by the agent harness, not the LLM.

    See ADR-0011 "Schema for a prompt YAML file" and ADR-0002 Budget.
    """

    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(default=10, ge=1, le=100)
    cost_cap_usd: float = Field(default=0.10, ge=0.0)
    delimiter_evidence: bool = True


class PromptDefinition(BaseModel):
    """Versioned prompt — the single artifact pushed to Langfuse."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    system: str = Field(min_length=1, description="Block-scalar system prompt.")
    user_template: str | None = Field(
        default=None,
        description="Optional user-message template with {{var}} placeholders.",
    )
    guardrails: PromptGuardrails = Field(default_factory=PromptGuardrails)
    metadata: dict[str, str] = Field(default_factory=dict)

    def format_system(self, variables: dict[str, str] | None = None) -> str:
        """Render the ``system`` prompt with ``{{var}}`` substitutions.

        Uses Langfuse's ``{{variable}}`` convention so the same prompt
        body round-trips cleanly between Langfuse and the local YAML.
        """

        return _render(self.system, variables or {})

    def format_user(self, variables: dict[str, str] | None = None) -> str | None:
        if not self.user_template:
            return None
        return _render(self.user_template, variables or {})


def _render(template: str, variables: dict[str, str]) -> str:
    out = template
    for key, value in variables.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out
