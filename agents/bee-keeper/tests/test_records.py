import json

from aura_keeper.hive.records import MetabolicRecord


def _record(**overrides) -> MetabolicRecord:
    base = dict(
        ts="2026-08-01T18:40:12Z",
        bee="keeper",
        cycle_id="20260801-184012",
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=2,
        prompt_tokens=900,
        completion_tokens=120,
        usd=0.004,
        wall_clock_s=12.5,
        outcome="success",
        dry_run=False,
    )
    base.update(overrides)
    return MetabolicRecord(**base)


def test_to_json_line_is_one_line_of_valid_json():
    line = _record().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line)["llm_calls"] == 2


def test_unknown_usage_serialises_as_null_not_zero():
    parsed = json.loads(
        _record(prompt_tokens=None, completion_tokens=None, usd=None).to_json_line()
    )
    assert parsed["prompt_tokens"] is None
    assert parsed["usd"] is None


def test_scheduled_heartbeat_records_zero_llm_calls():
    # Scheduled runs skip the LLM entirely; that is llm_calls=0 with null usage,
    # and such rows must be excluded from any cost baseline.
    parsed = json.loads(
        _record(
            llm_calls=0,
            model=None,
            prompt_tokens=None,
            completion_tokens=None,
            usd=None,
        ).to_json_line()
    )
    assert parsed["llm_calls"] == 0
    assert parsed["model"] is None
