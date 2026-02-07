import pytest
from hive.proteins.transaction.skill import TransactionSkill


@pytest.mark.asyncio
async def test_transaction_skill_execute_not_initialized():
    skill = TransactionSkill()
    obs = await skill.execute("get_address", {})
    assert obs.success is False
    assert "not_initialized" in obs.error
