import json

import pytest

from design_agent import architecture_md
from design_agent.cli import main
from design_agent.errors import Stop
from design_agent.normalize import field_variants, norm_entity
from design_agent.stages import run_llm_stage

from .conftest import HAPPY_INPUT


def test_field_variants_strip_only_safe_suffixes():
    assert "account" in field_variants("account_id")
    assert "account" in field_variants("accountId") or "accountid" in field_variants("accountId")
    assert "password" in field_variants("password_hash")
    assert "created" in field_variants("created_at")
    assert "active" in field_variants("active_flag")
    for unsafe in ("account_no", "account_num", "country_code"):
        assert len(field_variants(unsafe)) == 1  # never stripped


def test_norm_entity():
    assert norm_entity("Account Holder") == norm_entity("account_holder") == "accountholder"


def test_architecture_md_roundtrip():
    arch = {
        "system_boundary": "b",
        "frontend_backend_split": "s",
        "modules": [
            {"name": "A", "screens": ["S1"], "apis": [], "entities": ["E"], "boundary_note": "x | y"}
        ],
    }
    parsed = architecture_md.parse(architecture_md.render(arch))
    assert parsed == {"A": {"screens": ["S1"], "apis": [], "entities": ["E"]}}


class FlakyClient:
    name, model, temperature = "flaky", "flaky", None

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def complete_json(self, **_):
        self.calls += 1
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


GOOD = {"flows": [{"flow_id": "FL-1", "actor": "a", "action": "b", "screen": "c", "result": "d", "satisfies": ["F1"]}]}


def test_llm_stage_one_repair_retry():
    client = FlakyClient([{"flows": "wrong"}, GOOD])
    out, rec = run_llm_stage(client, number=3, name="user_flows", file="user_flows.json", payload={})
    assert out == GOOD and rec.attempts == 2 and client.calls == 2


def test_llm_stage_fails_closed_after_one_retry():
    client = FlakyClient([{"flows": "wrong"}, RuntimeError("boom")])
    with pytest.raises(Stop) as info:
        run_llm_stage(client, number=3, name="user_flows", file="user_flows.json", payload={})
    assert info.value.message.startswith("STOP: Stage 3 — user_flows — user_flows.json")
    assert client.calls == 2


def test_cli_exit_codes(tmp_path, capsys):
    assert main(["verify", str(HAPPY_INPUT)]) == 0
    assert main(["verify", str(tmp_path / "nope")]) == 2
    assert "STOP: Missing input" in capsys.readouterr().err


def test_cli_freeze_then_verify(tmp_path):
    import shutil

    dst = tmp_path / "in"
    shutil.copytree(HAPPY_INPUT, dst)
    (dst / "baseline.json").unlink()
    assert main(["verify", str(dst)]) == 2
    assert main(["freeze", str(dst), "--version", "v1", "--approved-by", "me"]) == 0
    assert main(["verify", str(dst)]) == 0
    assert json.loads((dst / "baseline.json").read_text())["approved_by"] == "me"


def test_stage2_entity_ownership_enforced(tmp_path):
    """LLM architecture that drops an entity stops at Stage 2, before spending more tokens."""
    from design_agent.runner import prepare
    from design_agent.stages import architecture as stage2

    index, _ = prepare(HAPPY_INPUT)
    arch = json.loads(
        (HAPPY_INPUT.parent / "replay" / "architecture.json").read_text(encoding="utf-8")
    )
    arch["modules"][0]["entities"] = []  # Customer now unowned

    class Fixed(FlakyClient):
        pass

    with pytest.raises(Stop) as info:
        stage2.run(Fixed([arch]), index)
    assert "missing ['Customer']" in info.value.message
