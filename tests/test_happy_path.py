import json

import pytest

from design_agent.cli import main
from design_agent.constants import OUTPUT_FILES
from design_agent.errors import Stop
from design_agent.runner import promote, run
from design_agent.validate import validate_dir

from .conftest import HAPPY_INPUT, load


def test_run_produces_six_files_and_diagrams(happy_run):
    run_dir = happy_run.run_dir
    for name in OUTPUT_FILES:
        assert (run_dir / "design" / name).is_file(), name
    for name in ("architecture", "user_flow"):
        assert (run_dir / "diagrams" / f"{name}.html").is_file()
    assert load(run_dir / "stage8_report.json")["passed"] is True
    meta = load(run_dir / "run_metadata.json")
    assert meta["status"] == "complete"
    assert meta["llm"]["provider"] == "replay"
    assert set(meta["inputs_sha256"]) == {
        "BRD.md",
        "frd.json",
        "data_spec.json",
        "error_catalogue.json",
    }


def test_runs_never_overwrite(tmp_path, replay):
    a = run(HAPPY_INPUT, tmp_path, replay)
    b = run(HAPPY_INPUT, tmp_path, replay)
    assert a.run_dir != b.run_dir
    assert a.run_dir.name.endswith("-01") and b.run_dir.name.endswith("-02")


def test_stage_6_and_7_are_mechanical(happy_run):
    design = happy_run.run_dir / "design"
    dm = load(design / "data_model.json")
    account = next(e for e in dm["entities"] if e["name"] == "Account")
    assert account["module"] == "Accounts"
    assert account["primary_key"] == ["account_id"]
    assert account["foreign_keys"] == [{"field": "customer_id", "references": "Customer.customer_id"}]
    balance = next(f for f in account["fields"] if f["name"] == "balance")
    assert balance["db_type"] == "NUMERIC"

    checks = load(design / "validation_checklist.json")["checks"]
    assert {(c["requirement_id"], c["error_id"], c["screen"], c["field"]) for c in checks} == {
        ("F1", "ERR-003", "Balance", "account_id"),
        ("F2", "ERR-001", "Transfer", "amount"),
        ("F2", "ERR-002", "Transfer", "amount"),
        ("F3", "ERR-004", "Login", "password"),
    }


def test_diagram_labels_reuse_exact_names(happy_run):
    mmd = (happy_run.run_dir / "diagrams" / "architecture.mmd").read_text()
    for name in ("Login", "POST /auth/login", "Customer", "Transfers", "GET /accounts/{account_id}/balance"):
        assert f'"{name}"' in mmd
    flow = (happy_run.run_dir / "diagrams" / "user_flow.mmd").read_text()
    assert '"F2"' in flow and '"Submit transfer"' in flow


def test_validate_command_passes_on_run(happy_run, capsys):
    code = main(["validate", str(happy_run.run_dir / "design"), "--input", str(HAPPY_INPUT)])
    assert code == 0
    assert "Stage 8 PASS" in capsys.readouterr().out


def test_promote_is_human_gated_and_never_overwrites(happy_run, tmp_path):
    out = tmp_path / "approved_root"
    target = promote(happy_run.run_dir, out, "v1.0", "Disha")
    assert (target / "architecture.md").is_file()
    assert json.loads((target / "promotion.json").read_text())["approved_by"] == "Disha"
    with pytest.raises(Stop):
        promote(happy_run.run_dir, out, "v1.0", "Disha")


def test_package_validates_independently(happy_run):
    from design_agent.runner import prepare

    index, _ = prepare(HAPPY_INPUT)
    assert validate_dir(happy_run.run_dir / "design", index) == []
