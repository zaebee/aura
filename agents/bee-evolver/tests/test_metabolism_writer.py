import json

from config import EvolverSettings
from hive.connector import EvolverConnector
from hive.records import MetabolicRecord


def _settings(tmp_path, **overrides) -> EvolverSettings:
    values = dict(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        AURA_METABOLISM_LOG=str(tmp_path / "nested" / "metabolism.jsonl"),
    )
    values.update(overrides)
    return EvolverSettings(**values)


def _record(cycle_id: str) -> MetabolicRecord:
    return MetabolicRecord(
        ts="2026-08-01T18:40:12Z",
        bee="evolver",
        cycle_id=cycle_id,
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=1,
        prompt_tokens=10,
        completion_tokens=5,
        usd=0.001,
        wall_clock_s=1.0,
        outcome="success",
        dry_run=True,
    )


def test_writer_appends_and_creates_parent_dir(tmp_path):
    settings = _settings(tmp_path)
    connector = EvolverConnector(settings)

    connector.write_metabolic_record(_record("cycle-1"))
    connector.write_metabolic_record(_record("cycle-2"))

    lines = open(settings.metabolism_log, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["cycle_id"] == "cycle-1"
    assert json.loads(lines[1])["cycle_id"] == "cycle-2"


def test_writer_failure_does_not_propagate(tmp_path):
    # A directory where the log file should be makes the open() fail.
    bad = tmp_path / "blocked"
    bad.mkdir()
    settings = _settings(tmp_path, AURA_METABOLISM_LOG=str(bad))
    connector = EvolverConnector(settings)

    connector.write_metabolic_record(_record("cycle-1"))  # must not raise
