"""Each of the 12 Stage 8 checks must fire on a targeted mutation of a valid package."""

import pytest

from design_agent.runner import prepare
from design_agent.validate import validate_dir

from .conftest import HAPPY_INPUT, load, save


@pytest.fixture
def index():
    return prepare(HAPPY_INPUT)[0]


def checks_fired(design, index) -> set[int]:
    return {f.check for f in validate_dir(design, index)}


def test_baseline_package_is_clean(design_copy, index):
    assert validate_dir(design_copy, index) == []


def test_check1_missing_file(design_copy, index):
    (design_copy / "ui_spec.json").unlink()
    assert checks_fired(design_copy, index) == {1}


def test_check1_invalid_json(design_copy, index):
    (design_copy / "api_contracts.json").write_text("{ nope")
    assert checks_fired(design_copy, index) == {1}


def test_check2_required_field_missing(design_copy, index):
    p = design_copy / "api_contracts.json"
    data = load(p)
    del data["apis"][0]["auth"]
    save(p, data)
    assert checks_fired(design_copy, index) == {2}


def test_check3_case_mismatch_is_flagged(design_copy, index):
    p = design_copy / "user_flows.json"
    data = load(p)
    data["flows"][2]["satisfies"] = ["f2"]
    save(p, data)
    failures = validate_dir(design_copy, index)
    assert any(f.check == 3 and "case mismatch" in f.reason for f in failures)


def test_check4_unknown_error_code(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][2]["fields"][1]["error_ids"].append("ERR-777")
    save(p, data)
    assert 4 in checks_fired(design_copy, index)


def test_check5_module_mismatch(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][1]["module"] = "Auth"
    save(p, data)
    assert checks_fired(design_copy, index) == {5}


def test_check6_invented_field(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][0]["fields"].append(
        {"name": "nickname", "type": "string", "required": "n", "error_ids": []}
    )
    save(p, data)
    assert checks_fired(design_copy, index) == {6}


def test_check6_never_strips_no_num_code(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][1]["fields"][0]["name"] = "account_no"  # spec has account_id
    save(p, data)
    assert 6 in checks_fired(design_copy, index)


def test_check6_suffix_stripping_allows_hash_and_id(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][0]["fields"][1]["name"] = "passwordHash"
    data["screens"][1]["fields"][0]["name"] = "account"
    save(p, data)
    assert validate_dir(design_copy, index) == []


def test_check7_unknown_entity(design_copy, index):
    p = design_copy / "data_model.json"
    data = load(p)
    data["entities"][0]["name"] = "Ledger"
    save(p, data)
    assert 7 in checks_fired(design_copy, index)


def test_check8_golden_thread_gap(design_copy, index):
    for name, key in (("ui_spec.json", "screens"), ("api_contracts.json", "apis")):
        p = design_copy / name
        data = load(p)
        for item in data[key]:
            item["satisfies"] = [i for i in item["satisfies"] if i != "NF1"]
        save(p, data)
    failures = validate_dir(design_copy, index)
    assert [f.ident for f in failures if f.check == 8] == ["NF1"]


def test_check9_architecture_item_missing_downstream(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"] = [s for s in data["screens"] if s["screen"] != "Transfer"]
    save(p, data)
    assert 9 in checks_fired(design_copy, index)


def test_check10_dangling_foreign_key(design_copy, index):
    p = design_copy / "data_model.json"
    data = load(p)
    data["entities"][2]["foreign_keys"][0]["references"] = "Ghost.id"
    save(p, data)
    assert checks_fired(design_copy, index) == {10}


def test_split_ownership_detected(design_copy, index):
    p = design_copy / "architecture.md"
    text = p.read_text().replace("screens: Balance;", "screens: Balance, Login;")
    p.write_text(text)
    assert 5 in checks_fired(design_copy, index)


def test_stop_line_format(design_copy, index):
    p = design_copy / "ui_spec.json"
    data = load(p)
    data["screens"][0]["fields"][0]["name"] = "nickname"
    save(p, data)
    line = validate_dir(design_copy, index)[0].stop_line()
    assert line.startswith("STOP: Stage 8 — check 6 (")
    assert "ui_spec.json — Login.nickname —" in line
