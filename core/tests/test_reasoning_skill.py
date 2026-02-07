import pytest
from hive.proteins.reasoning.main import ReasoningSkill

from config.llm import LLMSettings


@pytest.mark.asyncio
async def test_reasoning_skill_initialize_rule_mode(mocker):
    skill = ReasoningSkill()
    mocker.patch("hive.proteins.reasoning.main.load_brain")
    settings = LLMSettings(model="rule")
    skill.bind(settings, {"lm": None, "embedder": None})
    success = await skill.initialize()
    assert success is True


@pytest.mark.asyncio
async def test_reasoning_skill_execute_no_negotiator():
    skill = ReasoningSkill()
    settings = LLMSettings(model="rule")
    skill.bind(settings, {"lm": None, "embedder": None})
    await skill.initialize()
    obs = await skill.execute("negotiate", {"bid": 100.0, "context": {}, "history": []})
    assert obs.success is False
    assert "negotiator_not_ready" in obs.error
