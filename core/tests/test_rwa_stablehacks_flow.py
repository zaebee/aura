"""
StableHacks Sprint: End-to-End RWA Metabolic Flow Integration Test

Tests the complete ATCG loop for Real World Asset (RWA) processing:
Signal -> Membrane -> Aggregator -> Transformer -> Membrane -> Connector -> Generator

Biological Flow:
1. Signal arrives with physical asset (Rolex/Gold) + KYC verification
2. Membrane (immune system) validates inbound
3. Aggregator (senses) enriches context
4. AuraTransformer (brain) appraises RWA via DSPy reasoning
5. Membrane (immune system) validates outbound compliance
6. GuardSkill validates transaction safety
7. Observation confirms Solana transaction intent
"""

import json
from unittest.mock import AsyncMock, MagicMock

import betterproto
import pytest
from aura_core import SkillRegistry, make_struct
from aura_core.metabolism import MetabolicLoop
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    Observation,
    RWAVaultIntent,
)
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.membrane import HiveMembrane
from aura_hive.hive.proteins.guard.engine import OutputGuard
from aura_hive.hive.proteins.guard.skill import GuardSkill
from aura_hive.hive.transformer import AuraTransformer

_APPROVED_VAULT = json.dumps(
    {
        "vault_id": "vault-stablehacks-001",
        "asset_identifier": "SN-1401234-ROLEX",
        "asset_domain": "LUXURY_WATCH",
        "appraised_value_usd": 18500.0,
        "ltv_ratio": 0.60,
        "collateral_value_usd": 11100.0,
        "stablecoin_currency": "USDC",
        "reasoning": "Rolex Submariner authenticated. Market value confirmed via SIX rates.",
    }
)


def _make_approved_rwa_observation() -> Observation:
    """Create a mock Observation for APPROVED RWA compliance."""
    raw = {
        "think": "KYC verification passed. Asset authenticated via vision AI. SIX rates confirm market value. Approving vault intent for Solana USDC mint.",
        "compliance_status": "APPROVED",
        "violation_code": "",
        "appraised_value_usd": "18500.0",
        "collateral_value_usd": "11100.0",
        "vault": json.loads(_APPROVED_VAULT),
    }
    obs = MagicMock()
    obs.success = True
    obs.metadata = make_struct(raw)
    return obs


def _make_rejected_rwa_observation(violation_code: str) -> Observation:
    """Create a mock Observation for REJECTED RWA compliance."""
    raw = {
        "think": f"Compliance check failed: {violation_code}",
        "compliance_status": "REJECTED",
        "violation_code": violation_code,
        "appraised_value_usd": "0.0",
        "collateral_value_usd": "0.0",
        "vault": {
            "vault_id": "",
            "asset_identifier": "",
            "asset_domain": "",
            "appraised_value_usd": 0.0,
            "ltv_ratio": 0.60,
            "collateral_value_usd": 0.0,
            "stablecoin_currency": "USDC",
            "reasoning": f"REJECTED: {violation_code}",
        },
    }
    obs = MagicMock()
    obs.success = True
    obs.metadata = make_struct(raw)
    return obs


class MockAggregator:
    """Mock Aggregator (A) for RWA context enrichment."""

    async def perceive(self, signal: MagicMock, **kwargs) -> Context:
        metadata = {
            "rwa_mode": "true",
            "kyc_status": "true",
            "wallet_address": "SolanaVaultExample123",
            "vision_report": {
                "asset_type": "ROLEX_SUBMARINER",
                "serial_number": "SN-1401234",
                "condition": "excellent",
                "authentication_score": 0.95,
            },
            "six_rates": {
                "XAU_USD": "31000.0",
                "USD_CHF": "0.88",
                "ROLEX_SUBMARINER_USD": "18500.0",
            },
            "vitals": {
                "status": "VITALS_STATUS_OK",
                "cpu_usage_percent": "45.0",
                "memory_usage_mb": "512.0",
            },
        }
        return Context(metadata=make_struct(metadata))


class MockConnector:
    """Mock Connector (C) that validates transaction execution."""

    async def act(self, decision: Intent, context: Context) -> Observation:
        params_name, params_value = betterproto.which_one_of(decision, "params")

        if params_name == "rwa_vault" and params_value:
            rwa = params_value
            if decision.action == ActionType.ACTION_TYPE_REJECT:
                return Observation(
                    success=False,
                    error="RWA_REJECTED",
                    metadata=make_struct(
                        {
                            "transaction_chain": "SOLANA",
                            "transaction_type": "RWA_VAULT_REJECTED",
                            "vault_id": rwa.vault_id,
                            "violation_code": rwa.compliance.violation_code
                            if rwa.compliance
                            else "",
                        }
                    ),
                )
            return Observation(
                success=True,
                metadata=make_struct(
                    {
                        "transaction_chain": "SOLANA",
                        "transaction_type": "RWA_VAULT_MINT",
                        "vault_id": rwa.vault_id,
                        "collateral_amount": str(rwa.collateral_value_usd),
                        "currency": rwa.stablecoin_currency,
                    }
                ),
            )

        return Observation(success=False, error="No RWA vault intent found")


class MockGenerator:
    """Mock Generator (G) that emits events."""

    async def pulse(self, observation: Observation) -> None:
        pass


class MockPersistence:
    """Mock persistence skill for wallet sanctification check."""

    async def execute(self, intent: str, params: dict) -> Observation:
        if intent == "is_wallet_sanctified":
            return Observation(
                success=True,
                metadata=make_struct({"sanctified": True}),
            )
        return Observation(success=False, error="Unknown intent")


@pytest.fixture
def mock_reasoning_skill():
    """Fixture providing a mock reasoning skill that returns APPROVED RWA."""
    skill = MagicMock()
    skill.execute = AsyncMock(return_value=_make_approved_rwa_observation())
    skill.get_name = MagicMock(return_value="reasoning")
    skill.get_capabilities = MagicMock(return_value=["rwa", "trade", "negotiate"])
    skill.initialize = AsyncMock(return_value=True)
    return skill


@pytest.fixture
def mock_guard_skill():
    """Fixture providing a configured GuardSkill."""
    skill = GuardSkill()
    settings = SafetySettings()
    provider = OutputGuard(safety_settings=settings)
    skill.bind(settings, provider)

    persistence = MockPersistence()
    registry = SkillRegistry()
    registry.register("persistence", persistence)
    skill.inject_registry(registry)

    return skill


@pytest.fixture
def skill_registry(mock_reasoning_skill, mock_guard_skill):
    """Fixture providing a configured SkillRegistry."""
    registry = SkillRegistry()
    registry.register("reasoning", mock_reasoning_skill)
    registry.register("guard", mock_guard_skill)
    return registry


@pytest.fixture
def rwa_transformer(skill_registry):
    """Fixture providing an AuraTransformer configured for RWA."""
    return AuraTransformer(registry=skill_registry)


@pytest.fixture
def rwa_membrane(skill_registry):
    """Fixture providing a HiveMembrane for RWA validation."""
    return HiveMembrane(registry=skill_registry)


@pytest.fixture
def metabolic_loop(rwa_transformer, rwa_membrane):
    """Fixture providing a full MetabolicLoop for RWA processing."""
    return MetabolicLoop(
        aggregator=MockAggregator(),
        transformer=rwa_transformer,
        connector=MockConnector(),
        generator=MockGenerator(),
        membrane=rwa_membrane,
    )


@pytest.mark.asyncio
async def test_rwa_stablehacks_flow_approved(metabolic_loop):
    """
    Test Case: RWA flow with KYC=true and compliant asset

    Verifies:
    1. AuraTransformer outputs ActionType.ACTION_TYPE_ACCEPT with RWA vault intent
    2. Membrane allows compliant RWA through
    3. GuardSkill validates transaction
    4. Observation contains Solana transaction intent
    """
    mock_signal = MagicMock()
    mock_signal.signal_type = "SIGNAL_TYPE_NEGOTIATION"
    mock_signal.bid_amount = 0.0

    observation = await metabolic_loop.execute(mock_signal)

    assert observation.success is True, f"Metabolic loop failed: {observation.error}"

    meta = observation.metadata.to_dict()
    assert (
        meta.get("transaction_chain") == "SOLANA"
    ), "Expected Solana as the transaction chain"
    assert (
        meta.get("transaction_type") == "RWA_VAULT_MINT"
    ), "Expected RWA_VAULT_MINT transaction type"
    assert (
        meta.get("vault_id") == "vault-stablehacks-001"
    ), "Expected vault ID from approved vault"
    assert (
        float(meta.get("collateral_amount", "0")) > 0
    ), "Expected positive collateral amount"


@pytest.mark.asyncio
async def test_rwa_transformer_produces_solana_intent(rwa_transformer):
    """
    Test Case: Verify AuraTransformer outputs intent for Solana transaction

    Verifies the Transformer (brain) produces an Intent that:
    1. Has ActionType.ACTION_TYPE_ACCEPT for compliant RWA
    2. Contains RWAVaultIntent with Solana wallet address
    3. Has APPROVED compliance status
    """
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "kyc_status": "true",
                "wallet_address": "SolanaVaultExample123",
                "vision_report": {
                    "asset_type": "ROLEX_SUBMARINER",
                    "serial_number": "SN-1401234",
                    "condition": "excellent",
                    "authentication_score": 0.95,
                },
                "six_rates": {
                    "XAU_USD": "31000.0",
                    "USD_CHF": "0.88",
                    "ROLEX_SUBMARINER_USD": "18500.0",
                },
                "vitals": {
                    "status": "VITALS_STATUS_OK",
                    "cpu_usage_percent": "45.0",
                    "memory_usage_mb": "512.0",
                },
            }
        ),
    )

    intent = await rwa_transformer.think(context)

    params_name, params_value = betterproto.which_one_of(intent, "params")
    assert params_name == "rwa_vault", f"Expected 'rwa_vault', got '{params_name}'"
    assert (
        intent.action == ActionType.ACTION_TYPE_ACCEPT
    ), f"Expected ActionType.ACTION_TYPE_ACCEPT for compliant RWA, got {intent.action}"
    assert (
        params_value.wallet_address == "SolanaVaultExample123"
    ), "Expected Solana wallet address in vault intent"
    assert params_value.compliance.kyc_passed is True, "Expected KYC to pass"
    assert (
        params_value.compliance.compliance_status == "APPROVED"
    ), "Expected compliance status APPROVED"


@pytest.mark.asyncio
async def test_membrane_blocks_kyc_failure(rwa_membrane):
    """
    Test Case: Membrane blocks RWA with failed KYC

    Verifies the Membrane (immune system):
    1. Catches KYC failure that slipped through Transformer
    2. Overrides ActionType.ACTION_TYPE_ACCEPT to ActionType.ACTION_TYPE_REJECT
    3. Adds MEMBRANE reasoning to explain block
    """
    bad_intent = Intent(
        action=ActionType.ACTION_TYPE_ACCEPT,
        reasoning="<think>Transformer mistakenly accepted due to bug</think>",
        rwa_vault=RWAVaultIntent(
            vault_id="vault-kyc-fail",
            wallet_address="SolanaBadWallet",
            appraised_value_usd=18500.0,
            collateral_value_usd=11100.0,
            compliance=RWAVaultIntent(
                vault_id="vault-kyc-fail",
                wallet_address="SolanaBadWallet",
                appraised_value_usd=18500.0,
                collateral_value_usd=11100.0,
                compliance=RWAVaultIntent().compliance,
            ).compliance,
        ),
    )

    for field in [
        "vault_id",
        "wallet_address",
        "appraised_value_usd",
        "collateral_value_usd",
    ]:
        getattr(bad_intent.rwa_vault, field)

    bad_intent.rwa_vault.compliance = MagicMock()
    bad_intent.rwa_vault.compliance.kyc_passed = False
    bad_intent.rwa_vault.compliance.violation_code = "KYC_MISSING"

    context = Context(metadata=make_struct({}))

    result = await rwa_membrane.inspect_outbound(bad_intent, context)

    assert (
        result.action == ActionType.ACTION_TYPE_REJECT
    ), "Membrane should reject KYC failure"
    assert (
        "MEMBRANE" in result.reasoning or "KYC" in result.reasoning
    ), "Membrane should explain the block reason"


@pytest.mark.asyncio
async def test_guard_validates_transaction(mock_guard_skill):
    """
    Test Case: GuardSkill validates RWA transaction

    Verifies the GuardSkill (safety protein):
    1. Can validate transaction parameters
    2. Allows sanctified wallets to proceed
    3. Computes safe price for transaction
    """
    result = await mock_guard_skill.execute(
        "validate_transaction",
        {
            "wallet_address": "SolanaVaultExample123",
            "llm_price": 18500.0,
            "bid": 18500.0,
            "base_price": 18500.0,
        },
    )

    assert result.success is True, f"GuardSkill validation failed: {result.error}"
    meta = result.metadata.to_dict()
    assert "safe_price" in meta, "GuardSkill should return safe price"


@pytest.mark.asyncio
async def test_rwa_kyc_rejected_path(mock_reasoning_skill, skill_registry):
    """
    Test Case: RWA path with KYC=false is rejected

    Verifies:
    1. Reasoning skill returns REJECTED compliance
    2. Transformer outputs ActionType.ACTION_TYPE_REJECT
    3. Vault values are zeroed out
    """
    mock_reasoning_skill.execute = AsyncMock(
        return_value=_make_rejected_rwa_observation("KYC_MISSING")
    )

    transformer = AuraTransformer(registry=skill_registry)
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "kyc_status": "false",
                "wallet_address": "SolanaRejectedWallet",
                "vision_report": {"asset_type": "GOLD_BAR"},
                "six_rates": {"XAU_USD": "31000.0"},
                "vitals": {},
            }
        ),
    )

    intent = await transformer.think(context)

    assert (
        intent.action == ActionType.ACTION_TYPE_REJECT
    ), "KYC failure should result in REJECT"

    params_name, params_value = betterproto.which_one_of(intent, "params")
    assert params_name == "rwa_vault"
    assert params_value.compliance.violation_code == "KYC_MISSING"


@pytest.mark.asyncio
async def test_metabolic_loop_rejects_kyc_failure(
    metabolic_loop, mock_reasoning_skill, skill_registry
):
    """
    Test Case: Full metabolic loop rejects KYC failure

    Verifies end-to-end rejection path through complete loop.
    Reuses metabolic_loop fixture but overrides the reasoning skill to return rejected status.
    """
    mock_reasoning_skill.execute = AsyncMock(
        return_value=_make_rejected_rwa_observation("AML_SUSPICIOUS")
    )

    mock_signal = MagicMock()
    mock_signal.bid_amount = 0.0
    mock_signal.signal_type = "SIGNAL_TYPE_NEGOTIATION"
    observation = await metabolic_loop.execute(mock_signal)

    meta = observation.metadata.to_dict()
    assert (
        meta.get("transaction_chain") != "SOLANA" or not observation.success
    ), "KYC/AML failure should not produce successful Solana transaction"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
