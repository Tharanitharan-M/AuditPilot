"""
Evidence → SOC 2 TSC mapping (KEYSTONE — Sprint 4 chunk 4.5)
============================================================
For each :class:`Evidence` row collected upstream, derive the SOC 2
Trust Services Criteria clauses it helps satisfy and surface them as
:class:`ControlAssessment` records keyed by TSC id. Each assessment
records the supporting NIST SP 800-53 Rev 5 base controls in
``nist_800_53_refs`` (per ADR-0013 — NIST is the underlying catalog,
SOC 2 TSC is the presentation framework).

This is the first eval-measured node in the system. Sprint 10 chunks
10.1-10.5 will wire Promptfoo + RAGAS gold-set scoring on top of
``map_evidence_to_controls`` and the underlying ``compliance-kb-mcp``
retrieval.

Algorithm (Sprint 4 — deterministic, no LLM call)
-------------------------------------------------
For every evidence row:

1. Look up the curated source-type → TSC seed (``_SOURCE_TSC_SEEDS``).
   For Sprint-4 stub evidence and Sprint-5 GitHub evidence the seed
   anchors the assessment in the CC6.* (Logical and Physical Access)
   and CC7.* (System Operations) clauses that GitHub controls map to
   under ADR-0013.
2. Run BM25 over the NIST 800-53 catalog via
   ``compliance_kb_mcp.search_controls`` for the evidence's natural
   language description. The top-k results contribute additional TSC
   clauses through their ``soc2_tsc_mappings`` field.
3. For every (TSC, NIST-control, evidence) triple, accumulate into a
   single :class:`ControlAssessment` per TSC. Confidence = the maximum
   normalised BM25 score across contributing controls; minimum from the
   curated seed is 0.5 so the seed is always above the
   ``unknown → partial`` threshold.
4. Status starts at ``partial`` for any TSC with at least one supporting
   evidence row. Sprint-5 introduces real ``passing``/``failing``
   semantics once the evidence content is parsed (e.g. branch
   protection actually-enabled vs disabled).

Sprint 10 will introduce the LLM-judgment pass for low-confidence
matches. Sprint 5 will add the content-hash cache so identical evidence
never re-evaluates.

Refs: PLAN.md Sprint 4 chunk 4.5; ADR-0013; system-design.md 3.2, 12.5;
US-006.
"""

from __future__ import annotations

import logging
from typing import Final

from compliance_kb_mcp.schemas import Control
from compliance_kb_mcp.tools import lookup_by_soc2_tsc, search_controls

from apps.api.state import ControlAssessment, Evidence

logger = logging.getLogger(__name__)


# Top-k controls to retrieve per evidence row. 5 is a deliberate trade:
# fewer misses noisy multi-clause TSC matches; more dilutes the
# confidence signal. Sprint 10 evals will tune this.
_BM25_K: Final[int] = 5

# Minimum confidence for a curated-seed match. Anchors Sprint-4 stub
# evidence above the 0.5 ``partial`` threshold even when the BM25 path
# returns nothing useful (the stub's English is intentionally generic).
_SEED_CONFIDENCE: Final[float] = 0.6

# Curated seed map: source_type → list of TSC ids known to be in scope
# for that evidence kind. Comes from ADR-0013 + system-design §13.2 +
# the curated SOC 2 TSC mappings shipped in ``compliance-kb-mcp``. The
# seed is a SAFETY NET — the BM25 retrieval often surfaces the same TSC
# clauses, but the seed guarantees a control_map is non-empty even when
# the evidence's English is sparse (Sprint-4 stub).
_SOURCE_TSC_SEEDS: Final[dict[str, tuple[str, ...]]] = {
    "github": (
        "CC6.1",  # Logical and physical access controls
        "CC6.2",  # User access provisioning
        "CC6.6",  # Logical access boundaries
        "CC6.7",  # Restricted access
        "CC7.1",  # Detection of system-component changes
        "CC7.2",  # Monitoring of system components
        "CC8.1",  # Authorisation, design, development of system changes
    ),
    "mock": (
        "CC6.1",
        "CC6.2",
        "CC7.1",
    ),
    "clerk": (
        "CC6.1",
        "CC6.2",
        "CC6.3",
    ),
    "manual": (),
}


def map_evidence_to_controls(
    evidence_list: list[Evidence],
) -> dict[str, ControlAssessment]:
    """Map a list of Evidence rows to SOC 2 TSC ControlAssessment records.

    Pure function — does no I/O beyond the ``compliance-kb-mcp`` lookups
    (which are pure in-process Python over the static catalog). Returns
    a fresh dict; the caller (graph node) merges into ``state.control_map``.
    """

    if not evidence_list:
        return {}

    accumulator: dict[str, _Accumulator] = {}

    for evidence in evidence_list:
        # 1. Curated seed (always-on safety net).
        for tsc_id in _SOURCE_TSC_SEEDS.get(evidence.source_type, ()):
            controls = lookup_by_soc2_tsc(tsc_id)
            for control in controls:
                _accumulate(
                    accumulator,
                    tsc_id=tsc_id,
                    control=control,
                    evidence=evidence,
                    confidence=_SEED_CONFIDENCE,
                    rationale=f"Seeded from source_type={evidence.source_type!r}.",
                )

        # 2. BM25 retrieval over the natural-language evidence text.
        query = _evidence_to_query(evidence)
        if query.strip():
            try:
                candidates = search_controls(query, k=_BM25_K)
            except Exception as exc:  # noqa: BLE001
                # Defensive — search_controls is a pure function over
                # an in-process catalog so this should not fire, but
                # we never want a single bad query to abort the whole
                # mapping run.
                logger.warning(
                    "control_mapping.search_failed evidence_id=%s err=%r",
                    evidence.id,
                    exc,
                )
                candidates = []
            for rank, control in enumerate(candidates):
                bm25_confidence = _bm25_rank_to_confidence(rank, len(candidates))
                for tsc_id in control.soc2_tsc_mappings:
                    _accumulate(
                        accumulator,
                        tsc_id=tsc_id,
                        control=control,
                        evidence=evidence,
                        confidence=bm25_confidence,
                        rationale=(
                            f"BM25 rank {rank + 1}/{len(candidates)} on "
                            f"query '{query[:60]}'."
                        ),
                    )

    # Materialise the accumulators into ControlAssessment instances.
    return {tsc_id: acc.to_assessment() for tsc_id, acc in accumulator.items()}


def _evidence_to_query(evidence: Evidence) -> str:
    """Distil an Evidence row into a BM25 query string.

    Strategy: source_type + the evidence's ``raw`` payload's text-y
    fields. The Sprint-4 stub stores ``kind`` and ``note``; Sprint-5
    GitHub evidence will store branch-protection / MFA / scanning
    fields the BM25 corpus naturally indexes.
    """

    parts: list[str] = [evidence.source_type]
    raw = evidence.raw or {}
    for key in ("kind", "note", "title", "description"):
        value = raw.get(key)
        if isinstance(value, str):
            parts.append(value)
    # Final fallback: include the full string repr of `raw` so any
    # field name in there contributes to the BM25 score.
    parts.append(" ".join(str(v) for v in raw.values() if isinstance(v, str)))
    return " ".join(parts)


def _bm25_rank_to_confidence(rank: int, total: int) -> float:
    """Map a BM25 result rank to a [0, 1] confidence score.

    Linear decay over the top-k, with the worst rank floored at 0.3 so
    even a borderline match is above the ``unknown`` threshold.
    Confidence is informational (Sprint 4) — Sprint 10 evals will
    measure whether this transformation is well-calibrated.
    """

    if total <= 0:
        return 0.0
    fraction = (total - rank) / total
    return max(0.3, min(1.0, fraction))


# ── Internal accumulator ────────────────────────────────────────────────────


class _Accumulator:
    """Mutable workspace for a single (TSC) → ControlAssessment build.

    Avoids re-allocating ControlAssessment in the inner loop; one
    accumulator per TSC. ``to_assessment()`` produces the immutable
    ControlAssessment the graph node returns.
    """

    __slots__ = (
        "tsc_id",
        "nist_refs",
        "evidence_ids",
        "best_confidence",
        "rationale",
    )

    def __init__(self, tsc_id: str) -> None:
        self.tsc_id = tsc_id
        self.nist_refs: list[str] = []
        self.evidence_ids: list[str] = []
        self.best_confidence: float = 0.0
        self.rationale: str | None = None

    def add(
        self,
        *,
        nist_id: str,
        evidence_id: str,
        confidence: float,
        rationale: str,
    ) -> None:
        if nist_id not in self.nist_refs:
            self.nist_refs.append(nist_id)
        if evidence_id not in self.evidence_ids:
            self.evidence_ids.append(evidence_id)
        if confidence > self.best_confidence:
            self.best_confidence = confidence
            self.rationale = rationale

    def to_assessment(self) -> ControlAssessment:
        # Status: any evidence at all → partial; Sprint 5 will
        # promote to passing/failing once evidence content is parsed.
        status = "partial" if self.evidence_ids else "unknown"
        return ControlAssessment(
            tsc_id=self.tsc_id,
            status=status,
            confidence=round(self.best_confidence, 3),
            nist_800_53_refs=list(self.nist_refs),
            evidence_ids=list(self.evidence_ids),
            rationale=self.rationale,
        )


def _accumulate(
    accumulator: dict[str, _Accumulator],
    *,
    tsc_id: str,
    control: Control,
    evidence: Evidence,
    confidence: float,
    rationale: str,
) -> None:
    """Add one (TSC, control, evidence) triple to the accumulator."""

    acc = accumulator.setdefault(tsc_id, _Accumulator(tsc_id))
    acc.add(
        nist_id=control.id,
        evidence_id=evidence.id,
        confidence=confidence,
        rationale=rationale,
    )


__all__ = ["map_evidence_to_controls"]
