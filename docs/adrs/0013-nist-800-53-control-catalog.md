# ADR-0013: NIST 800-53 Rev 5 as the Underlying Control Catalog

**Date:** 2026-05-02
**Status:** Accepted (supersedes the SOC 2 TSC dataset choice in ADR-0005 §"Context and Problem Statement")
**Deciders:** AuditPilot maintainers
**Refs:** ADR-0004, ADR-0005, PRD §1, §5, §6.1, system-design §2.2, §4, §12.5, PLAN.md Sprints 1, 4, 9

---

## Context and Problem Statement

`compliance-kb-mcp` v0.1.0 shipped with a SOC 2 Trust Services Criteria (TSC) dataset transcribed from `getprobo/probo` (MIT license, pinned commit `1d08760d3b7b2625cefe1ec874d504e4b439a6c2`). Sixty-one criteria were carried forward, each annotated with a `TODO:` placeholder for the canonical AICPA points-of-focus prose because that text is copyright-protected.

Three problems with that v0.1.0 choice surfaced before any external consumer used the package:

1. **Forks would treat the abridged text as ground truth.** The Probo dataset is a hand-summarised projection of the 2017 TSC criteria. Each control description was a single line that sometimes elided the AICPA-language verbatim test case. Anyone forking AuditPilot to build a HIPAA, ISO 27001, or PCI-DSS variant would copy the schema and fill it with the same shape of summary text — perpetuating an inaccuracy. A reference architecture must publish a dataset that is faithful to the underlying authority, not a paraphrase of it.
2. **Sprint 10 evals would measure against truncated content.** The Promptfoo gold set, RAGAS faithfulness metric, and judge validation script all consume `compliance-kb-mcp` results during retrieval and generation. If the underlying control text is abridged, the eval compares model output against an abridged target — measuring fidelity to a paraphrase rather than the canonical control. That makes the published TPR/TNR/Cohen's kappa numbers misleading even when they pass the threshold.


A second-order signal: the AICPA's Uniform Accountancy Act (UPAct) shield codified in ADR-0004 already restricts AuditPilot to the language of *readiness* rather than *attestation*. Pairing that shield with a dataset that quietly redistributes a copyrighted vendor's interpretation would create one obvious challenge for any reviewer (legal or maintainer) who looked carefully at the source material.

---

## Decision

**Replace the abridged AICPA-derived SOC 2 TSC dataset with the canonical NIST Special Publication 800-53 Revision 5 control catalog as the primary control authority shipped in `compliance-kb-mcp`.**

The package now redistributes:

- **NIST 800-53 Rev 5 base controls (324 controls across 20 families)**, with parameter substitution applied so each statement is human-readable. The catalog is sourced from the official NIST OSCAL JSON published at [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content/blob/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json).
- **Curated SOC 2 TSC ↔ NIST 800-53 mappings** stored as `Control.soc2_tsc_mappings: list[str]`. The mappings are derived from the AICPA-published *Mapping: 2017 Trust Services Criteria to NIST 800-53* document (registration required for the canonical XLSX) and the publicly available [Open Security Architecture SOC 2 ↔ SP 800-53 crosswalk](https://opensecurityarchitecture.org/frameworks/soc2-tsc).
- **No SOC 2 TSC prose.** TSC clause identifiers (e.g. `CC6.1`, `A1.2`) are reproduced because identifiers are not copyrightable. The narrative text of each TSC clause remains an AICPA-CIMA copyrighted publication and is referenced by URL only.

The orchestrator, drift watcher, eval harness, and policy drafter all continue to think in SOC 2 TSC terms because that is what users are asked about ("Do you have SOC 2?"). The catalog underlying the answers shifts from a paraphrase to a public-domain authority that is *mapped* into the SOC 2 vocabulary.

---

## Repositioning Statement (canonical, use this everywhere)

> AuditPilot maps your environment to NIST 800-53 controls and shows which SOC 2 Trust Services Criteria are satisfied by your 800-53 coverage. The included `compliance-kb-mcp` ships with NIST 800-53 Rev 5 (public domain) and curated SOC 2 TSC mappings. For canonical SOC 2 TSC text, refer to AICPA-CIMA's published 2017 Trust Services Criteria — that text is copyright-protected and is not redistributed in this package.

---

## Rationale

### NIST 800-53 is public domain and machine-readable

NIST Special Publication 800-53 is a work of the U.S. federal government and is in the public domain under [17 U.S.C. § 105](https://www.law.cornell.edu/uscode/text/17/105). NIST publishes the catalog in OSCAL JSON, XML, and YAML at [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content), making it the only major control catalog that ships canonical text alongside a stable machine-readable schema. The package now contains the full 800-53 statement text, the full discussion / guidance text, and assessment-objective references — not a paraphrase.

### NIST publishes mappings to SOC 2 TSC

Two public mapping artefacts substantiate the SOC 2 ↔ 800-53 relationship:

1. The AICPA's own [*Mapping: 2017 Trust Services Criteria to NIST 800-53*](https://www.aicpa-cima.com/resources/download/mapping-2017-trust-services-criteria-to-nist-800-53). Registration is free; the spreadsheet is the authoritative cross-reference.
2. The [Open Security Architecture project's SOC 2 ↔ SP 800-53 crosswalk](https://opensecurityarchitecture.org/frameworks/soc2-tsc), available without registration, which preserves the same 122-clause / ~580-mapping structure.

Combining the two yields a curated mapping the package can ship without redistributing AICPA prose. Each control payload cites both sources in `source_citation.soc2_mapping_source`.

### The product story stays the same; the foundation gets stronger

A founding engineer using AuditPilot still asks "Do you have SOC 2?" and still receives a Pending Action backed by SOC 2 TSC vocabulary. What changes:

- Behind the SOC 2 TSC label, the orchestrator now retrieves the canonical NIST 800-53 control statement, discussion, and assessment objective.
- A `lookup_by_soc2_tsc(tsc_id)` tool returns the set of 800-53 controls that satisfy a given TSC clause.
- A `lookup_control(control_id)` tool answers "what does AC-1 say?" with the public-domain canonical text.
- The eval suite measures retrieval and generation against a redistributable, faithful corpus.

### Aligns with the read-only / draft-only posture

ADR-0004 commits AuditPilot to draft outputs and human-applied fixes. Pairing that posture with a canonical, public-domain control catalog removes any remaining surface where the package might be challenged for redistributing copyrighted text. The legal posture is now consistent end-to-end.

---

## Consequences

### Positive

- The redistributed dataset is **324 base controls** with full canonical text — a 5x increase in source fidelity over the v0.1.0 abridged dataset (61 paraphrases).
- Sprint 10 evals measure faithfulness against the public-domain canonical text. Published TPR / TNR / Cohen's kappa numbers describe a meaningful target, not a paraphrase.
- Forks for HIPAA, PCI-DSS, ISO 27001, or CMMC have a precedent for sourcing the canonical authority and shipping mappings to a presentation framework — rather than copying a vendor's summary.
- Public domain license eliminates all redistribution friction for the dataset itself.
- The architecture story becomes "we ground our SOC 2 readiness recommendations in the NIST control catalog the federal government publishes" — a stronger story than "we redistribute a vendor's MIT-licensed paraphrase of an AICPA publication."

### Negative

- The dataset is now ~10× larger (324 controls vs 61). BM25 ranking on the in-memory dataset still completes in under 100 ms, but pgvector embedding generation in Sprint 5 (`evidence-store-mcp`) needs to embed 324 control records; this raises one-off embedding cost from $0.01 to ~$0.03 (Gemini text-embedding-004). Negligible.
- The SOC 2 mapping is curated rather than authoritative. The AICPA XLSX is the canonical mapping; the curated set in this package is a reasonable proxy that cites both sources but is not AICPA-blessed. Users who need the authoritative cross-reference must consult the AICPA publication. We document this in `Control.source_citation.soc2_mapping_source`.
- Existing references in PRD, system-design, SRS, and `data` repositories that say "64 controls" need updating to either "324 NIST 800-53 base controls (with SOC 2 TSC mappings)" or "the SOC 2 TSC clauses (~64 common-criteria + privacy/availability/confidentiality/processing-integrity points-of-focus)" depending on context. ADR-0013 acceptance triggers a coordinated edit pass.

### Neutral

- The product positioning ("SOC 2 readiness reference architecture") is unchanged. The underlying catalog choice is an implementation detail surfaced in the README, system-design, and CHANGELOG, but does not change the user's mental model.

---

## Implementation Notes

- The dataset lives at `packages/compliance-kb-mcp/src/compliance_kb_mcp/data/nist_800_53_rev5_controls.json` and is regenerated by `packages/compliance-kb-mcp/scripts/build_dataset.py` from the OSCAL source. The script is idempotent.
- `Control.id` now matches NIST 800-53 base identifiers (e.g. `AC-1`, `SC-7`, `IA-2`); `Control.framework` is `nist_800_53_rev5`.
- `Control.soc2_tsc_mappings: list[str]` carries the curated TSC IDs; the package never carries TSC prose.
- Tool surface:
  - `lookup_control(control_id)` — by 800-53 base ID
  - `lookup_by_soc2_tsc(tsc_id)` — TSC ID → list of 800-53 controls
  - `search_controls(query, k)` — BM25 over the full corpus
  - `list_controls(family_id?)` — family-scoped or full catalog summaries
- `compliance-kb-mcp` version bumped from `0.1.0` to `0.2.0` with full CHANGELOG note marking the breaking schema change.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| **Keep the abridged Probo dataset and add canonical AICPA TSC text as a manual addition.** | AICPA copyright forbids redistribution. Even with permission, the asymmetry between authoritative TSC text and abridged paraphrase across other frameworks would persist. |
| **Keep the abridged dataset and label it explicitly as "summary only."** | Forks would still copy the schema. Sprint 10 evals would still measure against abridged text. The legal posture would still rely on a "fair use" argument for the AICPA-derived projection. |
| **Use the Open Security Architecture crosswalk as the catalog.** | OSA does not publish canonical control text — only the crosswalk identifiers. The catalog itself would still need to come from somewhere authoritative. NIST OSCAL is the authoritative source OSA points to. |
| **Use ISO 27001:2022 as the underlying catalog.** | ISO standards are copyright-protected and cost ~$200 per copy to redistribute. Public domain is not available. Same legal problem as redistributing AICPA TSC text. |
| **Adopt the [grcwarlock/compliance-frameworks](https://github.com/grcwarlock/compliance-frameworks) YAML catalog wholesale.** | Useful as a cross-reference (we use it to validate parts of the SOC 2 mapping), but it is one contributor's curation rather than the authoritative NIST source. We prefer to redistribute the canonical NIST text and cite the curated mapping sources. |
| **Drop the local catalog and call NIST CSRC at runtime.** | Adds a network dependency on every retrieval, defeating the offline-friendly stdio MCP server pattern. The OSCAL catalog is small (10 MB JSON) and ships well as a redistributed file. |

---

## Citations and Sources

- NIST Special Publication 800-53 Revision 5. DOI: [10.6028/NIST.SP.800-53r5](https://doi.org/10.6028/NIST.SP.800-53r5). Public domain (17 U.S.C. § 105).
- NIST OSCAL content repository: [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content).
- AICPA *Mapping: 2017 Trust Services Criteria to NIST 800-53*: [aicpa-cima.com/resources/download/mapping-2017-trust-services-criteria-to-nist-800-53](https://www.aicpa-cima.com/resources/download/mapping-2017-trust-services-criteria-to-nist-800-53). Free registration required.
- AICPA-CIMA *2017 Trust Services Criteria (with revised points of focus — 2022)*: [aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022). Copyrighted, not redistributed in this package.
- Open Security Architecture SOC 2 TSC crosswalk: [opensecurityarchitecture.org/frameworks/soc2-tsc](https://opensecurityarchitecture.org/frameworks/soc2-tsc).
