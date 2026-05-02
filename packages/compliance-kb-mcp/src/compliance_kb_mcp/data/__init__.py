"""Static control catalog for compliance-kb-mcp."""

from __future__ import annotations

import json
from importlib import resources

from compliance_kb_mcp.schemas import Control, Framework

NIST_FRAMEWORK = Framework(
    id="nist_800_53_rev5",
    name="NIST SP 800-53 Rev 5",
    version="5.2.0",
    description=(
        "Canonical public-domain catalog of NIST Special Publication 800-53 "
        "Revision 5 security and privacy controls. Each control is annotated "
        "with the SOC 2 Trust Services Criteria it helps satisfy, derived from "
        "publicly available crosswalks. The AICPA Trust Services Criteria "
        "publication is the authoritative source for SOC 2 TSC text and "
        "is not redistributed in this package."
    ),
)

FRAMEWORKS: dict[str, Framework] = {NIST_FRAMEWORK.id: NIST_FRAMEWORK}

_DATASET_RESOURCE = resources.files(__package__).joinpath("nist_800_53_rev5_controls.json")


def _load_controls() -> list[Control]:
    payloads = json.loads(_DATASET_RESOURCE.read_text(encoding="utf-8"))
    controls = [Control.model_validate(payload) for payload in payloads]

    if len({control.id for control in controls}) != len(controls):
        raise ValueError("Duplicate control IDs found in NIST 800-53 dataset")

    return controls


CONTROLS: list[Control] = _load_controls()
CONTROLS_BY_ID: dict[str, Control] = {control.id: control for control in CONTROLS}

CONTROLS_BY_TSC: dict[str, list[Control]] = {}
for _control in CONTROLS:
    for _tsc in _control.soc2_tsc_mappings:
        CONTROLS_BY_TSC.setdefault(_tsc, []).append(_control)

CONTROLS_BY_FAMILY: dict[str, list[Control]] = {}
for _control in CONTROLS:
    CONTROLS_BY_FAMILY.setdefault(_control.family_id, []).append(_control)
