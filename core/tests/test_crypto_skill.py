import pytest
from hive.proteins.crypto.main import CryptoSkill
from config.crypto import CryptoSettings

@pytest.mark.asyncio
async def test_crypto_skill_execute_not_initialized():
    skill = CryptoSkill()
    obs = await skill.execute("get_address", {})
    assert obs.success is False
    assert "not_initialized" in obs.error
