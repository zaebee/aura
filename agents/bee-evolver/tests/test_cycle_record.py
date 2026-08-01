import json

import pytest

from config import EvolverSettings
from hive.metabolism import EvolverMetabolism


def _settings(tmp_path) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_SHA="abc1234",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=True,
    )


def _read_record(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


async def test_transformer_failure_still_writes_a_record(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _perceive():
        return object()

    async def _boom(_context):
        raise RuntimeError("brain exploded")

    # _configure_git shells out to git; keep the test hermetic.
    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _perceive)
    monkeypatch.setattr(metabolism.transformer, "think", _boom)

    with pytest.raises(RuntimeError):
        await metabolism.execute()

    record = _read_record(settings.metabolism_log)
    assert record["outcome"] == "llm_error"
    assert record["bee"] == "evolver"
    assert record["git_sha"] == "abc1234"
    assert record["wall_clock_s"] >= 0
