"""Shared constants. Output contract and normalization rules live here."""

import re

REQUIRED_INPUTS = ("BRD.md", "frd.json", "data_spec.json", "error_catalogue.json")
OUTPUT_FILES = (
    "architecture.md",
    "user_flows.json",
    "ui_spec.json",
    "api_contracts.json",
    "data_model.json",
    "validation_checklist.json",
)
BASELINE_FILE = "baseline.json"

FRD_FIELDS = (
    "requirement_id",
    "official_id",
    "title",
    "statement",
    "epic",
    "source_ids",
    "roles",
    "preconditions",
    "postconditions",
    "error_ids",
    "assumptions",
    "open_question_ids",
    "priority",
    "status",
    "version",
)

BRD_SECTIONS = {
    1: "Introduction",
    2: "Project Drivers",
    3: "Constraints, Assumptions and Dependencies",
    4: "Current State",
    5: "Scope of Work",
    6: "Business Rules",
    7: "Requirements",
    8: "Business Implementation Requirements",
    9: "Issues",
    10: "Handover",
}

BR_RE = re.compile(r"\bBR-\d{3,}\b")
F_RE = re.compile(r"^F\d+$")
NF_RE = re.compile(r"^NF\d+$")
ERR_RE = re.compile(r"^ERR-\d{3,}$")

# Check 6: only these suffixes are stripped. `_no`, `_num`, `_code` are NEVER added:
# they collapse distinct concepts (account_no vs account_id).
SAFE_SUFFIXES = ("_hash", "_id", "_at", "_flag")

# Check 6: fields that legitimately appear in UI/API without a data_spec origin.
# Normalized form (lowercase, no separators).
DERIVED_FIELDS = frozenset(
    {
        "token",
        "accesstoken",
        "refreshtoken",
        "status",
        "statuscode",
        "httpstatus",
        "total",
        "totalcount",
        "count",
        "message",
        "success",
    }
)
