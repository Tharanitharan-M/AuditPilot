"""Cross-cutting services consumed by the LangGraph nodes.

Sprint 4 introduces:
  - ``evidence_collector`` — per-repo evidence-fetch coroutine
    contract used by the ``collect_evidence`` graph node (chunk 4.4b).
  - ``control_mapping`` — evidence → SOC 2 TSC mapping used by the
    ``map_controls`` graph node (chunk 4.5).

Sprint 5 will add:
  - ``cache`` — content-hash cache for the per-evidence control map
    (system-design §13.2).
  - ``drift`` — normalised projection + flap protection
    (system-design §13.3).

Refs: PLAN.md Sprint 4 chunks 4.4b, 4.5; ADR-0013 (NIST 800-53 catalog,
SOC 2 TSC presentation).
"""

from __future__ import annotations

__all__: list[str] = []
