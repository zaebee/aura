import httpx

from config import EvolverSettings
from hive.connector import EvolverConnector
from hive.models import EvolutionPlan, Improvement


def _settings(tmp_path, dry_run: bool) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_TOKEN="ghp_realish",
        AURA_TELEGRAM_TOKEN="tg-token",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=dry_run,
    )


def _plan() -> EvolutionPlan:
    return EvolutionPlan(
        improvements=[
            Improvement(
                type="issue",
                title="Something",
                description="d",
                issue_body="body",
            )
        ],
        narrative="n",
    )


def test_dry_run_parses_the_string_forms_a_workflow_passes(tmp_path):
    """The workflow sets EVOLVER_DRY_RUN from a boolean input, which reaches the
    process as the string "true"/"false". This is the seam between the YAML and
    the code — the switch existed for a while with no wire running to it."""
    for raw, expected in (("true", True), ("false", False), ("1", True), ("0", False)):
        settings = EvolverSettings(
            AURA_LLM__API_KEY="test-key",
            GITHUB_REPOSITORY="zaebee/aura",
            AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
            EVOLVER_DRY_RUN=raw,
        )
        assert settings.dry_run is expected, f"{raw!r} should parse to {expected}"


async def test_dry_run_makes_no_http_calls(tmp_path, monkeypatch):
    calls: list[str] = []

    async def _forbid(self, method, url, **kwargs):
        calls.append(str(url))
        raise AssertionError(f"dry_run must not call {url}")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbid)

    connector = EvolverConnector(_settings(tmp_path, dry_run=True))
    observation = await connector.act(
        plan=_plan(), branch="b", timestamp="20260801-1", apply_errors=[]
    )

    assert calls == []
    assert observation.pr_url == ""
    assert observation.telegram_sent is False
