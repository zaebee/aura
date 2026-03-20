import json
import re
from typing import Any, cast

import dspy
import structlog
from aura_core import resolve_brain_path
from hive.transformer.signatures import GenerateTradeIntent, GenerateTradeRisk
from langchain_mistralai import MistralAIEmbeddings

logger = structlog.get_logger(__name__)

# --- JSON Cleaning Implementation ---


def clean_and_parse_json(text: str) -> dict[str, Any]:
    if not text:
        raise ValueError("Empty or null input")
    try:
        return cast(dict[str, Any], json.loads(text))
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return cast(dict[str, Any], json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return cast(dict[str, Any], json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from: {text[:100]}...") from None


# --- DSPy Signatures and Modules ---


class Negotiate(dspy.Signature):
    """
    You are Ona & Jules, an autonomous sales manager and expert appraiser.

    Strategic Directives:
    1. VISION DISCOVERY: If 'vision_result' is in context, you must act as an Expert Appraiser.
       Calculate a suggested rental price as (Floor Price + 20% margin).
       Acknowledge vehicle details and ask user for verification.
    2. REALITY VERIFICATION: If user response in 'history' indicates a correction to your identification,
       trigger a 'Double Strand Break' (DSB): apologize, halt automation, and request manual entry.
    3. NEGOTIATION: If it's a standard bid, follow floor price rules.
    """

    input_bid = dspy.InputField(desc="Current buyer bid")
    context = dspy.InputField(desc="Economic context JSON")
    history = dspy.InputField(desc="Negotiation history JSON")
    thought = dspy.OutputField(desc="Strategic reasoning")
    action = dspy.OutputField(desc="Decision JSON with action, price, message")


class AuraNegotiator(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.negotiate = dspy.Predict(Negotiate)

    def forward(
        self, input_bid: float, context: Any, history: Any = None
    ) -> dict[str, Any]:
        h_json = history if isinstance(history, str) else json.dumps(history or [])
        c_json = context if isinstance(context, str) else json.dumps(context)
        pred = self.negotiate(input_bid=str(input_bid), context=c_json, history=h_json)
        try:
            action_data = clean_and_parse_json(pred.action)
            return cast(
                dict[str, Any],
                {
                    "thought": pred.thought,
                    "action": action_data,
                    "raw_action": pred.action,
                },
            )
        except Exception as e:
            raise ValueError(f"Negotiator parsing failed: {e}") from e


class AuraTradeNegotiator(dspy.Module):
    """
    Two-stage DSPy module for ERC-8004 trade intent generation.

    Stage 1 (GenerateTradeRisk): calculates drawdown potential and assigns a
    risk score before any trade decision is made.
    Stage 2 (GenerateTradeIntent): produces a structured JSON trade intent,
    automatically rejecting if risk_score > 0.10.
    """

    def __init__(self) -> None:
        super().__init__()
        self.assess_risk = dspy.Predict(GenerateTradeRisk)
        self.generate_intent = dspy.Predict(GenerateTradeIntent)

    def forward(
        self,
        market_context: dict[str, Any],
        system_vitals: dict[str, Any],
        current_treasury: dict[str, Any],
    ) -> dict[str, Any]:
        mc_json = json.dumps(market_context)
        sv_json = json.dumps(system_vitals)
        ct_json = json.dumps(current_treasury)

        # Stage 1: risk assessment
        risk_pred = self.assess_risk(
            market_context=mc_json,
            system_vitals=sv_json,
            current_treasury=ct_json,
        )
        risk_assessment = {
            "think": risk_pred.think,
            "risk_score": risk_pred.risk_score,
            "risk_category": risk_pred.risk_category,
        }

        # Stage 2: trade intent generation
        intent_pred = self.generate_intent(
            market_context=mc_json,
            system_vitals=sv_json,
            current_treasury=ct_json,
            risk_assessment=json.dumps(risk_assessment),
        )

        try:
            trade_data = clean_and_parse_json(intent_pred.trade_intent_json)
        except Exception as e:
            raise ValueError(
                f"TradeNegotiator JSON parsing failed: {e}. "
                f"Raw output: {intent_pred.trade_intent_json!r}"
            ) from e

        return cast(
            dict[str, Any],
            {
                "think": risk_pred.think,
                "risk_score": risk_pred.risk_score,
                "risk_category": risk_pred.risk_category,
                "trade": trade_data,
            },
        )


# --- Embeddings Implementation ---


def get_embedding_model(api_key: str) -> MistralAIEmbeddings:
    return MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=api_key,
    )


def generate_embedding(text: str, model: MistralAIEmbeddings) -> list[float]:
    return cast(list[float], model.embed_query(text))


# --- Brain Loading Helper ---


def load_brain(compiled_path: str | None = None) -> Any:
    """Load the DSPy brain using the standardized absolute discovery logic."""
    path = resolve_brain_path(compiled_path)
    if path != "UNKNOWN":
        try:
            return dspy.load(path)
        except Exception:  # nosec B112
            logger.warning("failed_to_load_brain", path=path)

    return AuraNegotiator()
