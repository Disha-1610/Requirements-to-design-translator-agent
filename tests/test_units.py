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

    def complete_json(self, **kw):
        self.calls += 1
        self.prompts = getattr(self, "prompts", []) + [kw["user"]]
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
    client = FlakyClient([{"flows": "wrong"}, {"flows": "still wrong"}])
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
        stage2.run(Fixed([arch, arch]), index)
    assert "missing ['Customer']" in info.value.message


def test_repair_prompt_includes_rejected_output_and_problems():
    bad = {"flows": "wrong"}
    client = FlakyClient([bad, GOOD])
    run_llm_stage(client, number=3, name="user_flows", file="user_flows.json", payload={})
    assert "PREVIOUS OUTPUT REJECTED" not in client.prompts[0]
    assert '{"flows":"wrong"}' in client.prompts[1]
    assert "flows:" in client.prompts[1]


def test_reference_check_failure_triggers_repair():
    client = FlakyClient([GOOD, GOOD])
    seen = []

    def check(out):
        seen.append(out)
        return ["check 3 — FL-1/F99 — not in baseline"] if len(seen) == 1 else []

    out, rec = run_llm_stage(
        client, number=3, name="user_flows", file="user_flows.json", payload={}, check=check
    )
    assert rec.attempts == 2 and "F99" in client.prompts[1]


def test_reference_check_failure_stops_after_repair():
    client = FlakyClient([GOOD, GOOD])
    with pytest.raises(Stop) as info:
        run_llm_stage(
            client, number=3, name="user_flows", file="user_flows.json", payload={},
            check=lambda o: ["invented field 'foo'"],
        )
    assert "invented field 'foo'" in info.value.message


def test_transient_error_is_retried():
    from design_agent.llm import TransientLLMError

    client = FlakyClient([TransientLLMError("overloaded"), GOOD])
    out, rec = run_llm_stage(client, number=3, name="user_flows", file="user_flows.json", payload={})
    assert out == GOOD and rec.attempts == 2
    assert "PREVIOUS OUTPUT REJECTED" not in client.prompts[1]


def test_non_transient_error_is_not_retried():
    client = FlakyClient([PermissionError("bad api key"), GOOD])
    with pytest.raises(PermissionError):
        run_llm_stage(client, number=3, name="user_flows", file="user_flows.json", payload={})
    assert client.calls == 1


def test_ui_stage_repairs_invented_field_and_error_id():
    """Stage 4 output with an invented field + ERR id is repaired before Stage 8."""
    import copy

    from design_agent.runner import prepare
    from design_agent.stages import ui_spec as stage4

    replay = HAPPY_INPUT.parent / "replay"
    index, _ = prepare(HAPPY_INPUT)
    arch = json.loads((replay / "architecture.json").read_text(encoding="utf-8"))
    flows = json.loads((replay / "user_flows.json").read_text(encoding="utf-8"))
    good = json.loads((replay / "ui_spec.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(good)
    bad["screens"][0]["fields"][0]["name"] = "zz_invented_field"
    bad["screens"][0]["fields"][0]["error_ids"] = ["ERR-999"]
    client = FlakyClient([bad, good])
    _, rec = stage4.run(client, index, arch, flows)
    assert rec.attempts == 2
    assert "zz_invented_field" in client.prompts[1] and "ERR-999" in client.prompts[1]
    assert "check 6" in client.prompts[1] and "check 4" in client.prompts[1]


# ---------------------------------------------------------------------------
# max_tokens guard
# ---------------------------------------------------------------------------

def test_max_tokens_stop_reason_raises_bad_output_error():
    """AnthropicClient must raise BadOutputError — not silently pass — when the
    model is cut off mid-tool-call (stop_reason == 'max_tokens')."""
    import types
    from design_agent.llm import AnthropicClient, BadOutputError

    client = AnthropicClient.__new__(AnthropicClient)

    # Build a minimal fake response with stop_reason == "max_tokens".
    fake_resp = types.SimpleNamespace(
        stop_reason="max_tokens",
        content=[],
        usage=types.SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        id="req_test",
    )

    class _FakeAnthropic:
        class APIConnectionError(Exception): pass
        class RateLimitError(Exception): pass
        class InternalServerError(Exception): pass

    class _FakeMessages:
        def create(self, **kw):
            return fake_resp

    class _FakeRawClient:
        messages = _FakeMessages()

    client._anthropic = _FakeAnthropic()
    client._client = _FakeRawClient()
    client.model = "test"
    client.temperature = None
    client.max_tokens = 100
    client.last_usage = {}

    with pytest.raises(BadOutputError) as info:
        client.complete_json(stage="architecture", system="sys", user="usr", schema={})
    assert "max_tokens" in str(info.value)
    assert "architecture" in str(info.value)


# ---------------------------------------------------------------------------
# Prompt hash covers both system and payload (reproducibility)
# ---------------------------------------------------------------------------

def test_prompt_hash_changes_when_payload_changes():
    """The prompt_sha256 in StageRecord must differ when the payload differs."""
    client_a = FlakyClient([GOOD])
    client_b = FlakyClient([GOOD])
    _, rec_a = run_llm_stage(client_a, number=3, name="user_flows", file="f.json", payload={"x": 1})
    _, rec_b = run_llm_stage(client_b, number=3, name="user_flows", file="f.json", payload={"x": 2})
    assert rec_a.prompt_sha256 != rec_b.prompt_sha256


def test_prompt_hash_is_stable_for_same_inputs():
    """Identical system + payload must always yield the same digest."""
    client_a = FlakyClient([GOOD])
    client_b = FlakyClient([GOOD])
    _, rec_a = run_llm_stage(client_a, number=3, name="user_flows", file="f.json", payload={"x": 1})
    _, rec_b = run_llm_stage(client_b, number=3, name="user_flows", file="f.json", payload={"x": 1})
    assert rec_a.prompt_sha256 == rec_b.prompt_sha256


# ---------------------------------------------------------------------------
# last_usage forwarded into StageRecord
# ---------------------------------------------------------------------------

def test_stage_record_captures_usage_from_client():
    """If the client exposes last_usage, it must appear in StageRecord.usage."""
    class UsageClient(FlakyClient):
        last_usage = {"input_tokens": 42, "output_tokens": 7, "request_id": "req_abc"}

    client = UsageClient([GOOD])
    _, rec = run_llm_stage(client, number=3, name="user_flows", file="f.json", payload={})
    assert rec.usage == {"input_tokens": 42, "output_tokens": 7, "request_id": "req_abc"}


def test_stage_record_usage_empty_when_client_has_none():
    """Clients without last_usage (e.g. ReplayClient) yield an empty usage dict."""
    client = FlakyClient([GOOD])
    # FlakyClient has no last_usage attribute.
    _, rec = run_llm_stage(client, number=3, name="user_flows", file="f.json", payload={})
    assert rec.usage == {}
