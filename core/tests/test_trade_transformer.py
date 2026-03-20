"""Tests for ERC-8004 trade intent generation across the transformer stack."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core import SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    ContextType,
    Intent,
    TradeIntent,
    ValidationScore,
)
from hive.membrane import HiveMembrane
from hive.proteins.reasoning.engine import AuraTradeNegotiator
from hive.transformer import AuraTransformer
from hive.transformer.signatures import GenerateTradeIntent, GenerateTradeRisk

# ---------------------------------------------------------------------------
# 1. Signature field contract
# ---------------------------------------------------------------------------


def test_generate_trade_risk_signature_fields():
    sig = GenerateTradeRisk
    input_fields = list(sig.input_fields.keys())
    output_fields = list(sig.output_fields.keys())
    assert "market_context" in input_fields
    assert "system_vitals" in input_fields
    assert "current_treasury" in input_fields
    assert "think" in output_fields
    assert "risk_score" in output_fields
    assert "risk_category" in output_fields


def test_generate_trade_intent_signature_fields():
    sig = GenerateTradeIntent
    input_fields = list(sig.input_fields.keys())
    output_fields = list(sig.output_fields.keys())
    assert "market_context" in input_fields
    assert "system_vitals" in input_fields
    assert "current_treasury" in input_fields
    assert "risk_assessment" in input_fields
    assert "trade_intent_json" in output_fields


# ---------------------------------------------------------------------------
# 2. AuraTradeNegotiator — low-risk path
# ---------------------------------------------------------------------------


def test_aura_trade_negotiator_low_risk(mocker):
    negotiator = AuraTradeNegotiator()

    low_risk_trade = json.dumps(
        {
            "trade_id": "trade-1700000000-VEHICLE",
            "asset_identifier": "asset-456",
            "asset_domain": "VEHICLE",
            "proposed_price": 250.0,
            "currency_code": "USDC",
            "reasoning": "Market stable, risk LOW at 0.04.",
        }
    )

    mock_risk_pred = MagicMock()
    mock_risk_pred.think = "<think>Drawdown ~4%. Safe.</think>"
    mock_risk_pred.risk_score = "0.04"
    mock_risk_pred.risk_category = "LOW"

    mock_intent_pred = MagicMock()
    mock_intent_pred.trade_intent_json = low_risk_trade

    mocker.patch.object(negotiator.assess_risk, "forward", return_value=mock_risk_pred)
    mocker.patch.object(
        negotiator.generate_intent, "forward", return_value=mock_intent_pred
    )

    result = negotiator.forward(
        market_context={"prices": {"USDC": 1.0}, "asset_domain": "VEHICLE"},
        system_vitals={"cpu_usage_percent": 20.0},
        current_treasury={"USDC": 1000.0},
        risk_threshold=0.10,
    )

    assert result["risk_score"] == "0.04"
    assert result["risk_category"] == "LOW"
    assert result["trade"]["proposed_price"] == 250.0
    assert "REJECTED_HIGH_RISK" not in result["trade"]["reasoning"]


# ---------------------------------------------------------------------------
# 3. AuraTradeNegotiator — high-risk path
# ---------------------------------------------------------------------------


def test_aura_trade_negotiator_high_risk(mocker):
    negotiator = AuraTradeNegotiator()

    high_risk_trade = json.dumps(
        {
            "trade_id": "trade-1700000001-VEHICLE",
            "asset_identifier": "asset-456",
            "asset_domain": "VEHICLE",
            "proposed_price": 0.0,
            "currency_code": "USDC",
            "reasoning": "REJECTED_HIGH_RISK: drawdown 15% exceeds threshold.",
        }
    )

    mock_risk_pred = MagicMock()
    mock_risk_pred.think = "<think>Drawdown ~15%. Too risky.</think>"
    mock_risk_pred.risk_score = "0.15"
    mock_risk_pred.risk_category = "HIGH"

    mock_intent_pred = MagicMock()
    mock_intent_pred.trade_intent_json = high_risk_trade

    mocker.patch.object(negotiator.assess_risk, "forward", return_value=mock_risk_pred)
    mocker.patch.object(
        negotiator.generate_intent, "forward", return_value=mock_intent_pred
    )

    result = negotiator.forward(
        market_context={"prices": {"USDC": 1.0}, "asset_domain": "VEHICLE"},
        system_vitals={"cpu_usage_percent": 90.0},
        current_treasury={"USDC": 100.0},
        risk_threshold=0.10,
    )

    assert float(result["risk_score"]) > 0.10
    assert result["risk_category"] == "HIGH"
    assert result["trade"]["proposed_price"] == 0.0
    assert "REJECTED_HIGH_RISK" in result["trade"]["reasoning"]


# ---------------------------------------------------------------------------
# 4. AuraTransformer.think() — trade path activated
# ---------------------------------------------------------------------------


def _make_trade_obs(
    risk_score: float,
    risk_category: str,
    proposed_price: float,
    rejected: bool = False,
) -> Any:
    """Build a mock Observation whose metadata matches the trade reasoning output."""
    raw: dict[str, Any] = {
        "think": f"<think>risk={risk_score}</think>",
        "risk_score": str(risk_score),
        "risk_category": risk_category,
        "trade": {
            "trade_id": "trade-test-001",
            "asset_identifier": "asset-001",
            "asset_domain": "VEHICLE",
            "proposed_price": proposed_price,
            "currency_code": "USDC",
            "reasoning": (
                "REJECTED_HIGH_RISK: too risky." if rejected else "Market stable."
            ),
        },
    }
    obs = MagicMock()
    obs.success = True
    obs.metadata = make_struct(raw)
    return obs


@pytest.mark.asyncio
async def test_transformer_think_trade_path_low_risk():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_trade_obs(0.04, "LOW", 250.0, rejected=False)
    )
    registry.register("reasoning", mock_reasoning)

    transformer = AuraTransformer(registry=registry)
    context = Context(
        context_type=ContextType.CONTEXT_TYPE_HIVE,
        metadata=make_struct(
            {
                "trade_mode": "true",
                "asset_domain": "VEHICLE",
                "asset_identifier": "asset-001",
                "prices": {"USDC": "1.0"},
                "treasury": {"USDC": "1000.0"},
            }
        ),
    )

    intent = await transformer.think(context)

    # Verify trade params oneof is set
    import betterproto

    params_name, params_value = betterproto.which_one_of(intent, "params")
    assert params_name == "trade", f"Expected 'trade', got '{params_name}'"
    assert intent.action == ActionType.ACTION_TYPE_ACCEPT
    assert params_value.validation_score.risk_score == pytest.approx(0.04, abs=1e-6)


@pytest.mark.asyncio
async def test_transformer_think_trade_path_high_risk():
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    mock_reasoning.execute = AsyncMock(
        return_value=_make_trade_obs(0.15, "HIGH", 0.0, rejected=True)
    )
    registry.register("reasoning", mock_reasoning)

    transformer = AuraTransformer(registry=registry)
    context = Context(
        context_type=ContextType.CONTEXT_TYPE_HIVE,
        metadata=make_struct(
            {
                "trade_mode": "true",
                "asset_domain": "VEHICLE",
                "asset_identifier": "asset-001",
            }
        ),
    )

    intent = await transformer.think(context)

    import betterproto

    params_name, _ = betterproto.which_one_of(intent, "params")
    assert params_name == "trade"
    assert intent.action == ActionType.ACTION_TYPE_REJECT


# ---------------------------------------------------------------------------
# 5. HiveMembrane — blocks high-risk trade intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_membrane_blocks_high_risk_trade():
    registry = SkillRegistry()
    membrane = HiveMembrane(registry=registry)

    high_risk_intent = Intent(
        action=ActionType.ACTION_TYPE_ACCEPT,  # transformer mistakenly accepted
        reasoning="<think>risk=0.20</think>",
        trade=TradeIntent(
            trade_id="trade-bad",
            proposed_price=500.0,
            currency_code="USDC",
            reasoning="Some reasoning",
            validation_score=ValidationScore(
                risk_score=0.20,
                risk_category="HIGH",
            ),
        ),
    )

    context = Context(
        metadata=make_struct({"floor_price": "100.0"}),
    )

    result = await membrane.inspect_outbound(high_risk_intent, context)

    assert result.action == ActionType.ACTION_TYPE_REJECT
    assert "MEMBRANE: high-risk trade blocked" in result.reasoning


@pytest.mark.asyncio
async def test_transformer_respects_custom_risk_threshold():
    """Threshold from SafetySettings overrides the 0.10 default."""
    registry = SkillRegistry()
    mock_reasoning = MagicMock()
    # risk_score=0.12 — above default 0.10 but below custom threshold of 0.20
    # rejected=False: LLM did not self-reject; threshold check must decide
    mock_reasoning.execute = AsyncMock(
        return_value=_make_trade_obs(0.12, "HIGH", 200.0, rejected=False)
    )
    registry.register("reasoning", mock_reasoning)

    settings = MagicMock()
    settings.llm.model = "mistral"
    settings.safety.trade_risk_threshold = 0.20  # relaxed threshold

    transformer = AuraTransformer(registry=registry, settings=settings)
    context = Context(
        metadata=make_struct({"trade_mode": "true", "asset_domain": "VEHICLE"}),
    )

    intent = await transformer.think(context)

    import betterproto

    params_name, _ = betterproto.which_one_of(intent, "params")
    assert params_name == "trade"
    # 0.12 < 0.20 threshold → should ACCEPT
    assert intent.action == ActionType.ACTION_TYPE_ACCEPT


@pytest.mark.asyncio
async def test_membrane_passes_low_risk_trade():
    registry = SkillRegistry()
    membrane = HiveMembrane(registry=registry)

    low_risk_intent = Intent(
        action=ActionType.ACTION_TYPE_ACCEPT,
        reasoning="<think>risk=0.04</think>",
        trade=TradeIntent(
            trade_id="trade-ok",
            proposed_price=250.0,
            currency_code="USDC",
            reasoning="Market stable.",
            validation_score=ValidationScore(
                risk_score=0.04,
                risk_category="LOW",
            ),
        ),
    )

    context = Context(
        metadata=make_struct({"floor_price": "100.0"}),
    )

    result = await membrane.inspect_outbound(low_risk_intent, context)

    assert result.action == ActionType.ACTION_TYPE_ACCEPT
    assert "MEMBRANE" not in result.reasoning
