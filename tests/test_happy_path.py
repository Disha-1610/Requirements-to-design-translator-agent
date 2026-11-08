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


# ---------------------------------------------------------------------------
# Promote hash-verification tests
# ---------------------------------------------------------------------------

def test_promote_blocked_when_design_file_edited_after_validation(happy_run, tmp_path):
    """Editing a design file after Stage 8 must block promotion."""
    out = tmp_path / "out"
    # Tamper with a design file *after* the run (which recorded hashes).
    arch_file = happy_run.run_dir / "design" / "architecture.md"
    arch_file.write_text(arch_file.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(Stop) as info:
        promote(happy_run.run_dir, out, "v1.0", "Disha")
    assert "modified after Stage 8" in info.value.message
    assert "architecture.md" in info.value.message


def test_stage8_report_contains_output_hashes(happy_run):
    """stage8_report.json must contain hashes for all six output files."""
    from design_agent.constants import OUTPUT_FILES
    report = load(happy_run.run_dir / "stage8_report.json")
    assert "output_sha256" in report
    assert set(report["output_sha256"].keys()) == set(OUTPUT_FILES)
    for name, digest in report["output_sha256"].items():
        assert len(digest) == 64, f"bad digest for {name}"


def test_promote_reads_report_with_utf8_encoding(happy_run, tmp_path):
    """promote() must not raise on Windows where the default encoding might not be UTF-8."""
    out = tmp_path / "out"
    # This just asserts the happy path goes through; the encoding fix is in the impl.
    target = promote(happy_run.run_dir, out, "v2.0", "Bot")
    assert (target / "promotion.json").is_file()


# ---------------------------------------------------------------------------
# --llm record mode tests
# ---------------------------------------------------------------------------

def test_record_client_writes_replay_folder(tmp_path, replay):
    """RecordClient must write one JSON file per stage that ReplayClient can replay."""
    from design_agent.llm import RecordClient, ReplayClient

    record_dir = tmp_path / "recorded"

    class _PassThrough:
        """Wraps the ReplayClient so RecordClient thinks it's an AnthropicClient."""
        name = "anthropic"
        model = "claude-test"
        temperature = 0.0
        last_usage: dict = {}

        def complete_json(self, **kw):
            return replay.complete_json(**kw)

    recorder = RecordClient(_PassThrough(), record_dir)
    assert recorder.name == "record"
    assert recorder.model == "claude-test"

    from design_agent.runner import run as da_run
    result = da_run(HAPPY_INPUT, tmp_path / "out", recorder)
    assert result.status == "complete"

    # The recorded directory must work as a replay fixture.
    from tests.conftest import REPLAY_DIR
    for stage_file in REPLAY_DIR.glob("*.json"):
        assert (record_dir / stage_file.name).is_file(), f"Missing recorded file: {stage_file.name}"


def test_cli_record_requires_record_dir(tmp_path, capsys):
    """--llm record without --record-dir must exit 2 with a helpful message."""
    import shutil
    dst = tmp_path / "in"
    shutil.copytree(HAPPY_INPUT, dst)
    code = main(["run", str(dst), "--out", str(tmp_path / "out"), "--llm", "record"])
    assert code == 2
    assert "--record-dir" in capsys.readouterr().err
