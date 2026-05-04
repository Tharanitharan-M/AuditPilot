"""Build the NIST 800-53 Rev 5 dataset for compliance-kb-mcp.

Reads the official NIST OSCAL JSON catalog, extracts each base control
(parameter substitution applied), attaches a curated SOC 2 TSC mapping,
and writes the result to ``src/compliance_kb_mcp/data/nist_800_53_rev5_controls.json``.

Run:
    python scripts/build_dataset.py \
        --oscal-source path/to/NIST_SP-800-53_rev5_catalog.json

The OSCAL catalog is published at:
    https://github.com/usnistgov/oscal-content/blob/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json

This script is idempotent: every run reproduces the same output for the
same input. Re-run after updating ``--oscal-source`` to refresh the dataset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "src" / "compliance_kb_mcp" / "data" / "nist_800_53_rev5_controls.json"

NIST_OSCAL_REPO_URL = "https://github.com/usnistgov/oscal-content"
NIST_OSCAL_FILE_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/"
    "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
NIST_PUBLICATION_URL = "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final"
NIST_PUBLICATION_DOI = "https://doi.org/10.6028/NIST.SP.800-53r5"


SOC2_TO_800_53: dict[str, list[str]] = {
    "CC1.1": ["PS-1", "PS-6", "PS-8"],
    "CC1.2": ["PS-1", "AT-1"],
    "CC1.3": ["PS-1", "PS-2", "PS-9"],
    "CC1.4": ["AT-1", "AT-2", "AT-3", "AT-4", "PS-6"],
    "CC1.5": ["PS-1", "PS-7", "PS-8"],
    "CC2.1": ["AT-2", "AT-3", "PL-2"],
    "CC2.2": ["AT-1", "AT-2", "AT-3", "PL-4", "SI-12"],
    "CC2.3": ["IR-6", "PM-15", "SR-8"],
    "CC3.1": ["PM-9", "RA-3", "RA-5"],
    "CC3.2": ["RA-3", "RA-5", "PM-9"],
    "CC3.3": ["RA-3", "PM-12"],
    "CC3.4": ["CA-7", "PL-2", "RA-3"],
    "CC4.1": ["CA-2", "CA-7", "PM-14"],
    "CC4.2": ["CA-5", "CA-7", "PM-4"],
    "CC5.1": ["AC-5", "PL-2", "PM-1", "RA-7"],
    "CC5.2": ["CM-2", "CM-6", "CM-7", "SA-3", "SA-4", "SA-9"],
    "CC5.3": ["AC-1", "AT-1", "CM-1", "PL-1", "PL-4"],
    "CC6.1": [
        "AC-2", "AC-3", "AC-4", "AC-6", "AC-7", "AC-17",
        "IA-2", "IA-3", "IA-4", "IA-5", "IA-8",
        "SC-7", "SC-8", "SC-12", "SC-13", "SC-28",
    ],
    "CC6.2": ["AC-2", "IA-2", "IA-4", "IA-5", "PS-4", "PS-5"],
    "CC6.3": ["AC-2", "AC-3", "AC-5", "AC-6", "PS-4", "PS-5"],
    "CC6.4": ["PE-2", "PE-3", "PE-4", "PE-5", "PE-6", "PE-8"],
    "CC6.5": ["MP-6", "SR-12"],
    "CC6.6": ["AC-2", "AC-3", "AC-4", "AC-17", "AC-20", "IA-2", "SC-5", "SC-7", "SI-4"],
    "CC6.7": ["AC-3", "AC-4", "AC-19", "AC-20", "MP-1", "MP-2", "MP-7", "PE-3", "SC-7", "SC-8"],
    "CC6.8": ["SC-18", "SI-3", "SI-7", "SI-8"],
    "CC7.1": ["CM-3", "CM-4", "RA-5", "SI-2", "SI-4", "SI-5"],
    "CC7.2": ["AU-2", "AU-3", "AU-6", "AU-12", "CA-7", "SI-4"],
    "CC7.3": ["AU-6", "IR-4", "IR-5", "SI-4"],
    "CC7.4": ["IR-1", "IR-4", "IR-5", "IR-6", "IR-7", "IR-8"],
    "CC7.5": ["CP-2", "CP-10", "IR-4", "IR-6", "IR-8"],
    "CC8.1": ["CM-3", "CM-4", "CM-5", "SA-10", "SA-11"],
    "CC9.1": ["CP-2", "CP-4", "PM-9", "RA-3", "SI-2"],
    "CC9.2": ["SR-1", "SR-2", "SR-3", "SR-5", "SR-6", "SR-8", "SR-11"],
    "A1.1": ["CP-2", "CM-8", "SA-2", "SC-5", "SC-6"],
    "A1.2": [
        "CP-2", "CP-4", "CP-6", "CP-7", "CP-8", "CP-9",
        "PE-9", "PE-11", "PE-13", "PE-14", "PE-15",
    ],
    "A1.3": ["CP-3", "CP-4"],
    "C1.1": ["MP-1", "SC-8", "SC-12", "SC-13", "SC-28"],
    "C1.2": ["AU-11", "MP-6", "SI-12"],
    "PI1.1": ["PL-2", "SA-3", "SI-10"],
    "PI1.2": ["SA-11", "SI-10"],
    "PI1.3": ["AU-2", "AU-12", "SI-10"],
    "PI1.4": ["AU-2", "AU-3", "SI-10", "SI-11"],
    "PI1.5": ["AU-11", "MP-6", "SC-28", "SI-12"],
    "P1.1": ["PT-1", "PT-3", "PT-5"],
    "P1.2": ["PT-2", "PT-4"],
    "P1.3": ["PT-2", "PT-3", "PT-4", "PT-6"],
    "P1.4": ["PT-2", "PT-3"],
    "P1.5": ["AU-11", "SI-12"],
    "P1.6": ["MP-6", "SI-12"],
    "P1.7": ["PT-6", "PT-7"],
    "P1.8": ["PT-3", "SI-18"],
    "P1.9": ["SI-18"],
}


PARAM_PATTERN = re.compile(r"\{\{\s*insert:\s*param,\s*([a-z0-9._-]+)\s*\}\}", re.IGNORECASE)


def _index_params(control: dict[str, Any]) -> dict[str, str]:
    index: dict[str, str] = {}
    for param in control.get("params", []) or []:
        param_id = param.get("id")
        if not param_id:
            continue
        label = (param.get("label") or "").strip()
        if label:
            stripped = label
            for prefix in ("organization-defined ", "organization defined "):
                if stripped.lower().startswith(prefix):
                    stripped = stripped[len(prefix):]
                    break
            index[param_id] = f"[Assignment: organization-defined {stripped}]"
            continue
        select = param.get("select")
        if select:
            choices = select.get("choice", [])
            joined = "; ".join(choices)
            how = select.get("how-many", "one")
            index[param_id] = f"[Selection ({how}): {joined}]"
            continue
        index[param_id] = "[Assignment: organization-defined value]"
    return index


def _substitute_params(text: str, params: dict[str, str]) -> str:
    """Substitute ``{{ insert: param, X }}`` markers, iterating until stable.

    OSCAL ``select.choice`` strings may themselves embed nested ``insert: param``
    markers (e.g. AC-20's selection choices reference ``ac-20_odp.02``/``.03``).
    A single ``re.sub`` pass expands the outer marker but leaves the nested ones
    intact. Iterate to a fixed point, capped at a small number of passes to
    defend against any future pathological self-referential definition.
    """

    def repl(match: re.Match[str]) -> str:
        return params.get(match.group(1), match.group(0))

    for _ in range(8):
        substituted = PARAM_PATTERN.sub(repl, text)
        if substituted == text:
            return substituted
        text = substituted
    return text


def _part_label(part: dict[str, Any]) -> str | None:
    for prop in part.get("props", []) or []:
        if prop.get("name") == "label":
            value = (prop.get("value") or "").strip()
            return value or None
    return None


def _flatten_part(part: dict[str, Any], params: dict[str, str], depth: int = 0) -> list[str]:
    lines: list[str] = []
    prose = part.get("prose")
    if prose:
        prose = _substitute_params(prose, params).strip()
        if prose:
            indent = "  " * max(depth - 1, 0)
            label = _part_label(part) if depth > 0 else None
            prefix = f"{label} " if label else ""
            lines.append(f"{indent}{prefix}{prose}".rstrip())
    for child in part.get("parts", []) or []:
        lines.extend(_flatten_part(child, params, depth + 1))
    return lines


def _statement_text(control: dict[str, Any], params: dict[str, str]) -> str:
    parts = control.get("parts", []) or []
    statement_part = next((p for p in parts if p.get("name") == "statement"), None)
    if not statement_part:
        return ""
    lines = _flatten_part(statement_part, params, depth=0)
    return "\n".join(lines).strip()


def _guidance_text(control: dict[str, Any], params: dict[str, str]) -> str:
    parts = control.get("parts", []) or []
    guidance_part = next((p for p in parts if p.get("name") == "guidance"), None)
    if not guidance_part or not guidance_part.get("prose"):
        return ""
    return _substitute_params(guidance_part["prose"], params).strip()


def _assessment_objectives(control: dict[str, Any], params: dict[str, str]) -> list[str]:
    objectives: list[str] = []
    for part in control.get("parts", []) or []:
        if part.get("name") != "assessment-objective":
            continue
        for line in _flatten_part(part, params, depth=0):
            stripped = line.strip()
            if stripped:
                objectives.append(stripped)
    return objectives


def _normalize_control_id(raw_id: str) -> str:
    family, _, suffix = raw_id.partition("-")
    return f"{family.upper()}-{suffix}".strip("-").upper()


def build_reverse_mapping(forward: dict[str, list[str]]) -> dict[str, list[str]]:
    reverse: dict[str, set[str]] = {}
    for tsc, ctrls in forward.items():
        for ctrl in ctrls:
            reverse.setdefault(ctrl, set()).add(tsc)
    return {ctrl: sorted(tscs) for ctrl, tscs in reverse.items()}


def build_dataset(oscal_path: Path) -> list[dict[str, Any]]:
    raw = json.loads(oscal_path.read_text(encoding="utf-8"))
    catalog = raw["catalog"]
    metadata = catalog.get("metadata", {})
    catalog_version = metadata.get("version", "5.2.0")
    catalog_last_modified = metadata.get("last-modified", "")
    oscal_version = metadata.get("oscal-version", "")

    reverse_mapping = build_reverse_mapping(SOC2_TO_800_53)

    rows: list[dict[str, Any]] = []
    for group in catalog.get("groups", []):
        family_id = (group.get("id") or "").lower()
        family_name = group.get("title", "")
        for control in group.get("controls", []):
            params = _index_params(control)
            control_id = _normalize_control_id(control["id"])
            statement = _statement_text(control, params)
            guidance = _guidance_text(control, params)
            objectives = _assessment_objectives(control, params)
            mapped_tsc = reverse_mapping.get(control_id, [])

            rows.append(
                {
                    "id": control_id,
                    "framework": "nist_800_53_rev5",
                    "family_id": family_id,
                    "family_name": family_name,
                    "title": control.get("title", "").strip(),
                    "statement": statement,
                    "guidance": guidance or None,
                    "assessment_objectives": objectives,
                    "soc2_tsc_mappings": mapped_tsc,
                    "source_citation": {
                        "publication": "NIST Special Publication 800-53 Revision 5",
                        "publication_version": catalog_version,
                        "publication_doi": NIST_PUBLICATION_DOI,
                        "publication_url": NIST_PUBLICATION_URL,
                        "oscal_repository": NIST_OSCAL_REPO_URL,
                        "oscal_source_file": NIST_OSCAL_FILE_URL,
                        "oscal_version": oscal_version,
                        "oscal_last_modified": catalog_last_modified,
                        "license": (
                            "Public domain (work of the U.S. federal government, "
                            "17 U.S.C.  105)"
                        ),
                        "soc2_mapping_source": (
                            "Curated from the AICPA-published "
                            "'Mapping: 2017 Trust Services Criteria to NIST 800-53' "
                            "(https://www.aicpa-cima.com/resources/download/"
                            "mapping-2017-trust-services-criteria-to-nist-800-53) "
                            "and the publicly available Open Security Architecture "
                            "SOC 2 \u2194 SP 800-53 crosswalk "
                            "(https://opensecurityarchitecture.org/frameworks/soc2-tsc). "
                            "The mapping is informational; consult the AICPA "
                            "publication for canonical guidance."
                        ),
                    },
                }
            )
    rows.sort(key=lambda row: (row["family_id"], _sort_key(row["id"])))
    return rows


_NUMERIC = re.compile(r"(\d+)")


def _sort_key(control_id: str) -> tuple[Any, ...]:
    parts: list[int | str] = []
    for token in _NUMERIC.split(control_id):
        if not token:
            continue
        if token.isdigit():
            parts.append(int(token))
        else:
            parts.append(token)
    return tuple(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oscal-source",
        type=Path,
        required=True,
        help="Path to NIST_SP-800-53_rev5_catalog.json from usnistgov/oscal-content.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Where to write the JSON dataset.",
    )
    args = parser.parse_args()

    if not args.oscal_source.exists():
        print(f"OSCAL source not found: {args.oscal_source}", file=sys.stderr)
        return 2

    rows = build_dataset(args.oscal_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    families = sorted({row["family_id"] for row in rows})
    print(f"Wrote {len(rows)} controls across {len(families)} families to {args.output}")
    print("Families:", ", ".join(families))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
