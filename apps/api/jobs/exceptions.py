"""Error types handlers raise to drive the retry-vs-DLQ decision.

The ``JobQueue.handle`` loop catches these:

- :class:`RetryableError` → back off and requeue (up to N attempts, then DLQ).
- :class:`FatalError` → move to the DLQ immediately, no retry.
- :class:`BudgetExceededError` → specialised fatal, the cost cap was hit
  (see ADR-0002 Budget). Surfaced separately so ops can alert on it.
- Any other ``Exception`` → treated as ``RetryableError`` (preserves the
  existing traceback in the stored failure reason).
"""

from __future__ import annotations


class JobError(Exception):
    """Base class for job-handler failures carried through the queue."""


class RetryableError(JobError):
    """Transient failure (429, 5xx, network blip). Queue will retry."""


class FatalError(JobError):
    """Permanent failure (400, 401, 403, 404). Queue parks in DLQ, no retry."""


class BudgetExceededError(FatalError):
    """The per-session or per-job cost cap was hit. Fatal, no retry."""
