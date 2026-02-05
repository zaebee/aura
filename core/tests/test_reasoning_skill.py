import pytest
from hive.proteins.reasoning.main import ReasoningSkill

from config.llm import LLMSettings


@pytest.mark.asyncio
async def test_reasoning_skill_initialize_rule_mode(mocker):
    skill = ReasoningSkill()
    mocker.patch("hive.proteins.reasoning.main.load_brain")
    settings = LLMSettings(model="rule")
    success = await skill.initialize(settings)
    assert success is True


@pytest.mark.asyncio
async def test_reasoning_skill_execute_no_negotiator():
    skill = ReasoningSkill()
    await skill.initialize(LLMSettings(model="rule"))
    obs = await skill.execute("negotiate", {"bid": 100.0, "context": {}, "history": []})
    assert obs.success is False
    assert "negotiator_not_ready" in obs.error
