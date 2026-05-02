"""Tool implementations for compliance-kb-mcp."""

from __future__ import annotations

import math
import re
from collections import Counter

from compliance_kb_mcp.data import (
    CONTROLS,
    CONTROLS_BY_FAMILY,
    CONTROLS_BY_ID,
    CONTROLS_BY_TSC,
)
from compliance_kb_mcp.schemas import Control, ControlSummary

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _control_corpus_text(control: Control) -> str:
    parts = [
        control.id,
        control.id.replace("-", " "),
        control.title,
        control.statement,
        control.guidance or "",
        " ".join(control.soc2_tsc_mappings),
        control.family_name,
        control.family_id,
    ]
    return " ".join(parts)


def lookup_control(control_id: str) -> Control | None:
    """Look up a NIST 800-53 control by base identifier (e.g. 'AC-1')."""

    return CONTROLS_BY_ID.get(control_id.strip().upper())


def lookup_by_soc2_tsc(tsc_id: str) -> list[Control]:
    """Return the 800-53 controls mapped to a SOC 2 TSC identifier (e.g. 'CC6.1')."""

    normalized = tsc_id.strip().upper()
    return list(CONTROLS_BY_TSC.get(normalized, []))


def search_controls(query: str, k: int = 5) -> list[Control]:
    """Run naive BM25 lexical ranking over the static NIST 800-53 catalog."""

    if not CONTROLS:
        return []

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    doc_tokens: list[list[str]] = []
    doc_lengths: list[int] = []
    term_document_frequency: Counter[str] = Counter()

    for control in CONTROLS:
        tokens = _tokenize(_control_corpus_text(control))
        doc_tokens.append(tokens)
        doc_lengths.append(len(tokens))
        term_document_frequency.update(set(tokens))

    avg_doc_length = sum(doc_lengths) / max(len(doc_lengths), 1)
    k1 = 1.5
    b = 0.75

    scored_controls: list[tuple[float, Control]] = []
    corpus_size = len(CONTROLS)

    for index, control in enumerate(CONTROLS):
        tokens = doc_tokens[index]
        token_counts = Counter(tokens)
        doc_length = doc_lengths[index]
        score = 0.0

        for term in query_terms:
            if term not in token_counts:
                continue
            df = term_document_frequency.get(term, 0)
            idf = math.log(((corpus_size - df + 0.5) / (df + 0.5)) + 1.0)
            tf = token_counts[term]
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_length / max(avg_doc_length, 1)))
            score += idf * (numerator / denominator)

        if score > 0:
            scored_controls.append((score, control))

    scored_controls.sort(key=lambda item: (-item[0], item[1].id))
    limit = max(1, min(k, len(scored_controls)))
    return [control for _, control in scored_controls[:limit]]


def list_controls(family_id: str | None = None) -> list[ControlSummary]:
    """List NIST 800-53 controls as summaries; optionally filter by family identifier."""

    if family_id:
        controls = list(CONTROLS_BY_FAMILY.get(family_id.strip().lower(), []))
    else:
        controls = list(CONTROLS)

    return [
        ControlSummary(
            id=control.id,
            framework=control.framework,
            family_id=control.family_id,
            family_name=control.family_name,
            title=control.title,
            soc2_tsc_mappings=list(control.soc2_tsc_mappings),
        )
        for control in sorted(controls, key=_sort_key_control)
    ]


_NUMERIC = re.compile(r"(\d+)")


def _sort_key_control(control: Control) -> tuple[object, ...]:
    parts: list[int | str] = []
    for token in _NUMERIC.split(control.id):
        if not token:
            continue
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token)
    return (control.family_id, *parts)
