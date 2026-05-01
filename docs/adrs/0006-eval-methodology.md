# ADR-0006: Eval Methodology — Promptfoo + RAGAS + Judge Validation

**Date:** 2026-05-01
**Status:** Accepted
**Deciders:** AuditPilot maintainers
**Refs:** SRS NFR-013, NFR-015; PRD §4.3; PLAN.md Sprint 10

---

## Context and Problem Statement

AuditPilot makes AI-generated claims about a company's SOC 2 readiness posture: "CC6.1 is PASSING," "your Incident Response Plan covers the required controls," "this SIG-Lite answer is correct." These claims have real consequences — a false negative (calling a gap PASSING) could leave a real security weakness undetected; a false positive (calling a PASSING control FAILING) creates unnecessary remediation work.

Commercial compliance tools make the same AI claims without publishing any quality metrics. No TPR, no TNR, no eval harness. Their quality is unverifiable.

The question: how do we validate the quality of AuditPilot's AI outputs, block regressions in CI, and publish verifiable metrics that differentiate AuditPilot from the black-box commercial competition?

---

## Decision

**Three-layer eval stack: Promptfoo (100-case gold set with LLM-as-judge) + RAGAS (RAG-specific metrics for compliance-kb retrieval) + judge validation script (TPR/TNR/Cohen's kappa on 50 hand-labeled cases).**

The 100-case gold set is hand-labeled by the project owner. The judge validation script runs independently to verify that the LLM judge itself is reliable. CI blocks merge on any regression greater than 2% in any eval category.

---

## Rationale

### Why eval quality matters more in compliance than in general chat

General chat assistants have high fault tolerance — a wrong answer is corrected in the next turn. In a compliance context:
- A false negative on CC6.1 (logical access controls) means a gap goes undetected before a real readiness review
- A hallucinated policy citation means a user files a policy with incorrect control references
- A wrong SIG-Lite answer means a vendor questionnaire with factual errors is submitted

The cost of undetected quality regressions is higher than in a consumer chatbot. The eval gate must block regression, not just report it.

### Why Promptfoo (not DeepEval, not LangSmith eval, not Braintrust)

**Promptfoo:**
- YAML configs stored in the repo — readable by any reviewer without running code
- GitHub Actions native integration — CI gate with zero configuration
- Langfuse integration via `langfuse://` provider — evals link back to traces
- Case types: control mapping (40), citation faithfulness (30), policy structure (20), questionnaire judge (10)
- LLM-as-judge with a deterministic rubric in the YAML; the rubric itself is versioned and reviewable

**DeepEval** (rejected): pytest-style fixtures are less legible in a code review than YAML configs sitting next to the prompts they evaluate. Functionally equivalent; legibility under review is the tiebreaker.

**LangSmith eval** (rejected): requires LangSmith subscription above free tier. Our $0/month constraint (SRS CON-005) rules it out. We use Langfuse-compatible patterns that interoperate without LangSmith.

**Braintrust** (rejected): closed source and paid. For an open-source reference architecture, the eval harness must be runnable by any fork without a vendor account.

### Why judge validation (the rare move)

Most teams that use LLM-as-judge never validate whether the judge itself is accurate. If the judge's "PASS" call is wrong 30% of the time, the eval gate is noise. The judge validation script:
1. Takes 50 hand-labeled cases (ground truth: human-decided PASS/FAIL)
2. Runs the LLM judge on the same 50 cases
3. Computes TPR (true positive rate: of real FAILs, how many did the judge catch?)
4. Computes TNR (true negative rate: of real PASSes, how many did the judge correctly pass?)
5. Computes Cohen's kappa (inter-rater agreement correcting for chance)

Thresholds: TPR ≥ 0.85, TNR ≥ 0.85, kappa ≥ 0.70. If the judge falls below any threshold, the rubric is fixed before the judge is used to gate CI. This loop — validate the validator — is what separates senior eval practitioners from teams that just plug in `gpt-4o-as-judge` and ship.

Results published to `docs/evals/judge-validation.md` with the full confusion matrix. Any external reviewer can read the methodology and the numbers.

### Why RAGAS in addition to Promptfoo

Promptfoo's LLM-as-judge is good at "did the answer make sense and cite correctly" but is a weak detector of retrieval-level failures: the retrieved chunk was correct, the answer is coherent, but the retrieved chunk was from the wrong control. RAGAS provides four metrics that are specifically designed for retrieval-augmented generation:

| RAGAS metric | What it catches |
|---|---|
| Faithfulness | Generated answer contradicts the retrieved context |
| Answer relevancy | Generated answer addresses the question but does not use the context |
| Context precision | Retrieved chunks include irrelevant controls that dilute the signal |
| Context recall | The correct chunk was not retrieved at all |

Thresholds: each metric ≥ 0.80. These run on the compliance-kb retrieval path specifically. Free, Apache 2.0, integrates with Langfuse.

### Gold set construction discipline

The 100-case Promptfoo gold set is hand-labeled by the project owner during Sprint 10. Labeling rules:
- Cases are constructed from real SOC 2 TSC control descriptions and real GitHub evidence patterns
- No case is generated by the same LLM that will be evaluated
- Each case has a human-written expected output or a deterministic assertion
- The gold set is frozen before any model or prompt change; regressions are relative to the frozen set
- The gold set lives in `docs/evals/gold/` and is never modified by any automated process

The `eval-runner` sub-agent can execute evals but is explicitly blocked from editing any file in `docs/evals/gold/`. Only the project owner hand-labels new cases.

---

## Consequences

### Positive
- CI gate blocks any merge that regresses control-mapping accuracy, citation faithfulness, policy structure, or questionnaire quality by more than 2%
- Published TPR/TNR/kappa numbers are verifiable by any reader — a rare differentiator vs. commercial tools that make unverifiable AI quality claims
- Promptfoo YAML configs are readable by any reviewer without running code
- RAGAS catches retrieval-layer failures that LLM-as-judge misses
- Judge validation loop means the CI gate itself is trustworthy

### Negative
- 150 hand-labeled cases (100 gold set + 50 judge validation) is significant human time during Sprint 10
- Promptfoo eval suite adds ~5–10 minutes to CI runtime on PRs that touch prompts/agents/MCPs
- Eval suite must be maintained when prompts change; stale evals are worse than no evals (they produce false confidence)
- The "X% control-mapping accuracy" metric cannot be reported until Sprint 10; all prior docs use `X%` as a placeholder

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **DeepEval** | pytest over YAML; less readable in portfolio review. Functionally equivalent. Portfolio legibility is the tiebreaker. |
| **Braintrust** | Closed source, paid. Violates $0/month constraint (SRS CON-005). |
| **LangSmith eval** | Requires paid LangSmith subscription above free tier. Violates $0/month constraint. |
| **TruLens** | Snowflake-flavored; no Snowflake in our stack. Less momentum than RAGAS for RAG evaluation. |
| **No eval (manual QA only)** | Unacceptable for a compliance use case where false negatives have real consequences. A CI gate without evals is indistinguishable from no CI gate for prompt quality. |
| **LLM-as-judge without judge validation** | Common but insecure. If the judge is wrong 30% of the time, the CI gate is noise. Judge validation is the rare move that makes the gate trustworthy. |

---

