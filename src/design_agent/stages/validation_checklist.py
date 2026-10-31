"""Stage 7 (code): validation_checklist.json from frd error_ids + ui_spec links.

`has_validation: false` is an honest record, not a failure. Error codes are
taken from frd.json only; none is ever invented to fill a gap. When the UI spec
did not place a stated error on a field, screen/field stay null: the gap is visible.
"""

from __future__ import annotations

from ..constants import F_RE
from ..index import CanonicalIndex

NUMBER, NAME, FILE = 7, "validation_checklist", "validation_checklist.json"


def build(index: CanonicalIndex, ui: dict) -> dict:
    checks: list[dict] = []
    for rid, rec in index.requirements.items():
        if not F_RE.fullmatch(rid):
            continue
        if not rec["error_ids"]:
            checks.append(
                {
                    "requirement_id": rid,
                    "has_validation": False,
                    "error_id": None,
                    "screen": None,
                    "field": None,
                }
            )
            continue
        for eid in rec["error_ids"]:
            placed = [
                (s["screen"], f["name"])
                for s in ui["screens"]
                if rid in s["satisfies"]
                for f in s["fields"]
                if eid in f["error_ids"]
            ]
            for screen, fld in placed or [(None, None)]:
                checks.append(
                    {
                        "requirement_id": rid,
                        "has_validation": True,
                        "error_id": eid,
                        "screen": screen,
                        "field": fld,
                    }
                )
    return {"schema_version": "1", "checks": checks}
