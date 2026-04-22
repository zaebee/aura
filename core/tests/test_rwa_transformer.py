import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import betterproto
import pytest
from aura_core import SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    RWAComplianceScore,
    RWAVaultIntent,
)
from hive.membrane import HiveMembrane
from hive.proteins.reasoning.engine import AuraRWANegotiator
from hive.transformer import AuraTransformer
from hive.transformer.signatures import AppraiseAndVerifyRWA

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APPROVED_VAULT = json.dumps(
    {
        "vault_id": "vault-GOLD-abc12345",
        "asset_identifier": "gold-bar-001",
        "asset_domain": "GOLD",
        "appraised_value_usd": 62000.0,
        "ltv_ratio": 0.60,
        "collateral_value_usd": 37200.0,
        "stablecoin_currency": "USDC",
        "wallet_address": "abc12345xyz",
        "reasoning": "KYC passed. 2 troy oz gold at $31000/oz = $62000. LTV 60% = $37200.",
    }
)

_REJECTED_VAULT = json.dumps(
    {
        "vault_id": "vault-GOLD-abc12345",
        "asset_identifier": "gold-bar-001",
        "asset_domain": "GOLD",
        "appraised_value_usd": 0.0,
        "ltv_ratio": 0.60,
        "collateral_value_usd": 0.0,
        "stablecoin_currency": "USDC",
        "wallet_address": "abc12345xyz",
        "reasoning": "REJECTED: KYC_MISSING — wallet not verified.",
    }
)


def _make_rwa_obs(
    compliance_status: str,
    violation_code: str,
    appraised: float,
    collateral: float,
    vault_json: str,
) -> Any:
    raw: dict[str, Any] = {
        "think": f"<think>compliance={compliance_status}</think>",
        "compliance_status": compliance_status,
        "violation_code": violation_code,
        "appraised_value_usd": str(appraised),
        "collateral_value_usd": str(collateral),
        "vault": json.loads(vault_json),
    }
    obs = MagicMock()
    obs.success = True
    obs.metadata = make_struct(raw)
    return obs


# ---------------------------------------------------------------------------
# 1. Signature field contract
# ---------------------------------------------------------------------------


def test_appraise_and_verify_rwa_signature_fields():
    sig = AppraiseAndVerifyRWA
    inputs = list(sig.input_fields.keys())
    outputs = list(sig.output_fields.keys())

    assert "vision_report" in inputs
    assert "wallet_address" in inputs
    assert "kyc_status" in inputs
    assert "six_rates" in inputs
    assert "ltv_ratio" in inputs
    assert "system_vitals" in inputs

    assert "think" in outputs
    assert "compliance_status" in outputs
    assert "violation_code" in outputs
    assert "appraised_value_usd" in outputs
    assert "collateral_value_usd" in outputs
    assert "vault_intent_json" in outputs


# ---------------------------------------------------------------------------
# 2. AuraRWANegotiator — KYC rejected
# ---------------------------------------------------------------------------


def test_rwa_negotiator_kyc_rejected(mocker):
    negotiator = AuraRWANegotiator()

    mock_pred = MagicMock()
    mock_pred.think = "<think>KYC not passed.</think>"
    mock_pred.compliance_status = "REJECTED"
    mock_pred.violation_code = "KYC_MISSING"
    mock_pred.appraised_value_usd = "0.0"
    mock_pred.collateral_value_usd = "0.0"
    mock_pred.vault_intent_json = _REJECTED_VAULT

    mocker.patch.object(negotiator.appraise, "forward", return_value=mock_pred)

    result = negotiator.forward(
        vision_report={"asset_type": "GOLD", "weight_oz": 2.0},
        wallet_address="abc12345xyz",
        kyc_status="false",
        six_rates={"XAU_USD": 31000.0},
        ltv_ratio="0.60",
        system_vitals={},
    )

    assert result["compliance_status"] == "REJECTED"
    assert result["violation_code"] == "KYC_MISSING"
    assert float(result["appraised_value_usd"]) == 0.0
    assert float(result["collateral_value_usd"]) == 0.0
    assert result["vault"]["appraised_value_usd"] == 0.0


# ---------------------------------------------------------------------------
# 3. AuraRWANegotiator — approved
# ---------------------------------------------------------------------------


def test_rwa_negotiator_approved(mocker):
    negotiator = AuraRWANegotiator()

    mock_pred = MagicMock()
    mock_pred.think = "<think>KYC passed. Asset verified.</think>"
    mock_pred.compliance_status = "APPROVED"
    mock_pred.violation_code = ""
    mock_pred.appraised_value_usd = "62000.0"
    mock_pred.collateral_value_usd = "37200.0"
    mock_pred.vault_intent_json = _APPROVED_VAULT

    mocker.patch.object(negotiator.appraise, "forward", return_value=mock_pred)

    result = negotiator.forward(
        vision_report={
            "asset_type": "GOLD",
            "weight_oz": 2.0,
            "condition": "excellent",
        },
        wallet_address="abc12345xyz",
        kyc_status="true",
        six_rates={"XAU_USD": 31000.0},
        ltv_ratio="0.60",
        system_vitals={},
    )

    assert result["compliance_status"] == "APPROVED"
    assert result["violation_code"] == ""
    assert float(result["collateral_value_usd"]) > 0
    assert result["vault"]["collateral_value_usd"] == 37200.0


# ---------------------------------------------------------------------------
# 4. Transformer — RWA path, KYC rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transformer_think_rwa_path_rejected():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_rwa_obs("REJECTED", "KYC_MISSING", 0.0, 0.0, _REJECTED_VAULT)
    )
    registry.register("reasoning", mock_reasoning)

    transformer = AuraTransformer(registry=registry)
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "kyc_status": "false",
                "wallet_address": "abc12345xyz",
                "vision_report": {"asset_type": "GOLD"},
                "six_rates": {"XAU_USD": "31000.0"},
            }
        ),
    )

    intent = await transformer.think(context)

    params_name, _ = betterproto.which_one_of(intent, "params")
    assert params_name == "rwa_vault", f"Expected 'rwa_vault', got '{params_name}'"
    assert intent.action == ActionType.ACTION_TYPE_REJECT


# ---------------------------------------------------------------------------
# 5. Transformer — RWA path, approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transformer_think_rwa_path_approved():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_rwa_obs("APPROVED", "", 62000.0, 37200.0, _APPROVED_VAULT)
    )
    registry.register("reasoning", mock_reasoning)

    transformer = AuraTransformer(registry=registry)
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "kyc_status": "true",
                "wallet_address": "abc12345xyz",
                "vision_report": {"asset_type": "GOLD", "weight_oz": "2.0"},
                "six_rates": {"XAU_USD": "31000.0"},
            }
        ),
    )

    intent = await transformer.think(context)

    params_name, params_value = betterproto.which_one_of(intent, "params")
    assert params_name == "rwa_vault"
    assert intent.action == ActionType.ACTION_TYPE_ACCEPT
    assert params_value.collateral_value_usd == pytest.approx(37200.0, abs=0.01)


# ---------------------------------------------------------------------------
# 6. Transformer — RWA takes priority over trade path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transformer_rwa_takes_priority_over_trade():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_rwa_obs("APPROVED", "", 62000.0, 37200.0, _APPROVED_VAULT)
    )
    registry.register("reasoning", mock_reasoning)

    transformer = AuraTransformer(registry=registry)
    # Both rwa_mode AND asset_domain (trade trigger) are set
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "asset_domain": "GOLD",  # would trigger trade path
                "kyc_status": "true",
                "wallet_address": "abc12345xyz",
            }
        ),
    )

    intent = await transformer.think(context)

    params_name, _ = betterproto.which_one_of(intent, "params")
    assert params_name == "rwa_vault", (
        f"RWA path should take priority over trade path, got '{params_name}'"
    )
    # Verify reasoning protein was called with 'rwa', not 'trade'
    # skill.execute(intent, params) — intent is the first positional arg
    call_args = mock_reasoning.execute.call_args
    assert call_args.args[0] == "rwa"


# ---------------------------------------------------------------------------
# 7. Membrane — blocks KYC failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_membrane_blocks_kyc_failure():
    registry = SkillRegistry()
    membrane = HiveMembrane(registry=registry)

    bad_intent = Intent(
        action=ActionType.ACTION_TYPE_ACCEPT,  # transformer mistakenly accepted
        reasoning="<think>compliance=REJECTED</think>",
        rwa_vault=RWAVaultIntent(
            vault_id="vault-bad",
            wallet_address="abc12345xyz",
            appraised_value_usd=0.0,
            collateral_value_usd=0.0,
            compliance=RWAComplianceScore(
                kyc_passed=False,
                aml_passed=False,
                compliance_status="REJECTED",
                violation_code="KYC_MISSING",
            ),
        ),
    )

    context = Context(metadata=make_struct({"floor_price": "0.0"}))
    result = await membrane.inspect_outbound(bad_intent, context)

    assert result.action == ActionType.ACTION_TYPE_REJECT
    assert "MEMBRANE: KYC compliance failure" in result.reasoning


# ---------------------------------------------------------------------------
# 8. Membrane — passes compliant RWA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_membrane_passes_compliant_rwa():
    registry = SkillRegistry()
    membrane = HiveMembrane(registry=registry)

    good_intent = Intent(
        action=ActionType.ACTION_TYPE_ACCEPT,
        reasoning="<think>compliance=APPROVED</think>",
        rwa_vault=RWAVaultIntent(
            vault_id="vault-ok",
            wallet_address="abc12345xyz",
            appraised_value_usd=62000.0,
            collateral_value_usd=37200.0,
            compliance=RWAComplianceScore(
                kyc_passed=True,
                aml_passed=True,
                compliance_status="APPROVED",
                violation_code="",
            ),
        ),
    )

    context = Context(metadata=make_struct({"floor_price": "0.0"}))
    result = await membrane.inspect_outbound(good_intent, context)

    assert result.action == ActionType.ACTION_TYPE_ACCEPT
    assert "MEMBRANE" not in result.reasoning


# ---------------------------------------------------------------------------
# 9. Transformer respects custom rwa_ltv_ratio from settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rwa_ltv_ratio_from_settings():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_rwa_obs("APPROVED", "", 62000.0, 31000.0, _APPROVED_VAULT)
    )
    registry.register("reasoning", mock_reasoning)

    settings = MagicMock()
    settings.safety.rwa_ltv_ratio = 0.50  # custom — not the default 0.60

    transformer = AuraTransformer(registry=registry, settings=settings)
    context = Context(
        metadata=make_struct(
            {
                "rwa_mode": "true",
                "kyc_status": "true",
                "wallet_address": "abc12345xyz",
            }
        ),
    )

    await transformer.think(context)

    call_args = mock_reasoning.execute.call_args
    # skill.execute(intent, params) — params is the second positional arg
    passed_params = call_args.args[1]
    assert passed_params["ltv_ratio"] == "0.5"
