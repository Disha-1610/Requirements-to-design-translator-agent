"""Regenerate examples/negative/* and examples/happy-path/input/baseline.json.

Each case mutates the happy-path inputs, then freezes the (defective) result, so
Stage 0's baseline check passes and the intended gate is the one that fires.

    python examples/make_negative.py
"""

from __future__ import annotations

import copy
import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from design_agent.baseline import freeze

HERE = Path(__file__).parent
HAPPY = HERE / "happy-path" / "input"
OUT = HERE / "negative"
FILES = ("BRD.md", "frd.json", "data_spec.json", "error_catalogue.json")

Docs = dict[str, str]


def _json(docs: Docs, name: str) -> dict:
    return json.loads(docs[name])


def _dump(docs: Docs, name: str, data: dict) -> None:
    docs[name] = json.dumps(data, indent=2) + "\n"


def drop(name: str) -> Callable[[Docs], None]:
    return lambda d: d.pop(name)


def inc01(d: Docs) -> None:
    d["BRD.md"] = re.sub(r"## 7\. Requirements.*?## 9\. Issues", "## 9. Issues", d["BRD.md"], flags=re.S)


def inc02(d: Docs) -> None:
    frd = _json(d, "frd.json")
    for r in frd["requirements"]:
        r.pop("error_ids")
        r.pop("source_ids")
    _dump(d, "frd.json", frd)


def inc03(d: Docs) -> None:
    spec = _json(d, "data_spec.json")
    spec.pop("state_transitions")
    _dump(d, "data_spec.json", spec)


def inc04(d: Docs) -> None:
    cat = _json(d, "error_catalogue.json")
    for e in cat["errors"][:2]:
        e.pop("user_message")
        e.pop("http_status")
    _dump(d, "error_catalogue.json", cat)


def cont01(d: Docs) -> None:
    frd = _json(d, "frd.json")
    frd["requirements"][1]["error_ids"].append("ERR-999")
    _dump(d, "frd.json", frd)


def cont02(d: Docs) -> None:
    spec = _json(d, "data_spec.json")
    for f in spec["fields"]:
        if f["entity"] == "Transaction" and f["name"] == "account_id":
            f["foreign_key"] = "AccountX.account_id"
    _dump(d, "data_spec.json", spec)


def cont03(d: Docs) -> None:
    frd = _json(d, "frd.json")
    rec = copy.deepcopy(frd["requirements"][0])
    rec.update(
        requirement_id="F4",
        official_id="FR-004",
        title="Cryptocurrency trading",
        statement="A customer can buy and sell cryptocurrency.",
        error_ids=[],
    )
    frd["requirements"].append(rec)
    _dump(d, "frd.json", frd)


def cont04(d: Docs) -> None:
    spec = _json(d, "data_spec.json")
    spec["state_transitions"]["Account"][0]["fixtures"] = ["CUST-999"]
    _dump(d, "data_spec.json", spec)


def malf01(d: Docs) -> None:
    d["frd.json"] = d["frd.json"].rstrip().removesuffix("}").removesuffix("]").rstrip() + ",\n"


def malf02(d: Docs) -> None:
    spec = _json(d, "data_spec.json")
    spec["fields"][0]["type"] = {"nested": {"unparsable": ["string", {"x": None}]}}
    _dump(d, "data_spec.json", spec)


CASES: list[tuple[str, str, str, str, str, Callable[[Docs], None]]] = [
    ("TC-MISS-01", "MISSING_DOCUMENT", "Stage 0", "STOP: Missing input — BRD.md", "Omit BRD.md.", drop("BRD.md")),
    ("TC-MISS-02", "MISSING_DOCUMENT", "Stage 0", "STOP: Missing input — frd.json", "Omit frd.json.", drop("frd.json")),
    ("TC-MISS-03", "MISSING_DOCUMENT", "Stage 0", "STOP: Missing input — data_spec.json", "Omit data_spec.json.", drop("data_spec.json")),
    ("TC-MISS-04", "MISSING_DOCUMENT", "Stage 0", "STOP: Missing input — error_catalogue.json", "Omit error_catalogue.json.", drop("error_catalogue.json")),
    ("TC-INC-01", "INCOMPLETE_SECTIONS", "Stage 1", "STOP: Incomplete input — BRD.md missing Section 7", "Remove Sections 7 and 8 from BRD.md.", inc01),
    ("TC-INC-02", "INCOMPLETE_SECTIONS", "Stage 1", "STOP: Incomplete input — frd.json — F1 missing", "Strip error_ids and source_ids from every requirement.", inc02),
    ("TC-INC-03", "INCOMPLETE_SECTIONS", "Stage 1", "STOP: Incomplete input — data_spec.json missing state_transitions", "Remove the state_transitions block.", inc03),
    ("TC-INC-04", "INCOMPLETE_SECTIONS", "Stage 1", "STOP: Incomplete input — error_catalogue.json — ERR-001 missing", "Delete user_message and http_status from two errors.", inc04),
    ("TC-CONT-01", "CONTRADICTORY_DATA", "Stage 8 (check 4, pre-LLM)", "STOP: Stage 8 — check 4", "frd.json F2 references ERR-999, absent from the catalogue.", cont01),
    ("TC-CONT-02", "CONTRADICTORY_DATA", "Stage 8 (check 10, pre-LLM)", "STOP: Stage 8 — check 10", "Transaction.account_id foreign key points to AccountX.account_id.", cont02),
    ("TC-CONT-03", "CONTRADICTORY_DATA", "Stage 8 (check 11, pre-LLM)", "STOP: Stage 8 — check 11", "frd.json adds Cryptocurrency trading, listed Out of Scope in BRD 5.2.", cont03),
    ("TC-CONT-04", "CONTRADICTORY_DATA", "Stage 8 (check 12, pre-LLM)", "STOP: Stage 8 — check 12", "A state transition cites fixture CUST-999, not in fixtures.", cont04),
    ("TC-MALF-01", "MALFORMED_SYNTAX", "Stage 0", "STOP: Malformed input — frd.json —", "frd.json ends with a trailing comma and an unclosed bracket.", malf01),
    ("TC-MALF-02", "MALFORMED_SYNTAX", "Stage 0", "STOP: Malformed input — data_spec.json —", "A field type is replaced by a nested unparsable structure.", malf02),
]


def main() -> None:
    base: Docs = {n: (HAPPY / n).read_text(encoding="utf-8") for n in FILES}
    if OUT.exists():
        shutil.rmtree(OUT)
    for tc, category, stage, prefix, description, mutate in CASES:
        docs = dict(base)
        mutate(docs)
        case_dir = OUT / tc
        inp = case_dir / "input"
        inp.mkdir(parents=True)
        for name, text in docs.items():
            (inp / name).write_text(text, encoding="utf-8")
        freeze(inp, version="test", approved_by="make_negative.py")
        (case_dir / "expected.json").write_text(
            json.dumps(
                {
                    "test_case_id": tc,
                    "category": category,
                    "expected_failure_stage": stage,
                    "expected_stop_prefix": prefix,
                    "description": description,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    freeze(HAPPY, version="happy-1", approved_by="make_negative.py")
    print(f"Generated {len(CASES)} negative cases + happy-path baseline")


if __name__ == "__main__":
    main()
