import json
import re
import time
from pathlib import Path
from typing import Any, cast

import dspy
import litellm
import structlog
from aura.negotiation.v1 import negotiation_pb2
from aura_core import resolve_brain_path
from jinja2 import Template
from langchain_mistralai import MistralAIEmbeddings
from pydantic import BaseModel

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
    """Negotiation decision signature."""

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


# --- Legacy/Alternative Strategies (for tests and fallbacks) ---


class LLMEngine:
    def __init__(
        self, model: str, temperature: float = 0.7, api_key: str | None = None
    ):
        self.model = model
        self.temperature = temperature
        self.api_key = api_key

    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: type[BaseModel] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if response_format:
            kwargs["response_model"] = response_format
        resp = litellm.completion(**kwargs)
        content = resp.choices[0].message.content
        return content


class AI_Decision(BaseModel):
    action: str
    price: float
    message: str
    reasoning: str


class LiteLLMStrategy:
    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        trigger_price: float = 1000.0,
    ):
        self.engine = LLMEngine(model=model, temperature=temperature, api_key=api_key)
        self.trigger_price = trigger_price
        template_path = (
            Path(__file__).parent.parent.parent
            / "transformer"
            / "prompts"
            / "system.md"
        )
        if template_path.exists():
            with open(template_path) as f:
                self.prompt_template = Template(f.read())
        else:
            self.prompt_template = Template("Item: {{item_name}}, Bid: {{bid}}")

    def evaluate(
        self, item: Any, bid: float, reputation: float, request_id: str | None = None
    ) -> negotiation_pb2.NegotiateResponse:
        if not item:
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )
        item_name = (
            item.get("name", "unknown")
            if isinstance(item, dict)
            else getattr(item, "name", "unknown")
        )
        base_p = (
            item.get("base_price", 0.0)
            if isinstance(item, dict)
            else getattr(item, "base_price", 0.0)
        )
        floor_p = (
            item.get("floor_price", 0.0)
            if isinstance(item, dict)
            else getattr(item, "floor_price", 0.0)
        )
        prompt = self.prompt_template.render(
            business_type="hotel",
            item_name=item_name,
            base_price=base_p,
            floor_price=floor_p,
            market_load="High",
            trigger_price=self.trigger_price,
            bid=bid,
            reputation=reputation,
        )
        msgs = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Make a decision."},
        ]
        try:
            decision: AI_Decision = self.engine.complete(
                messages=msgs, response_format=AI_Decision
            )
            res = negotiation_pb2.NegotiateResponse()
            if decision.action == "accept":
                res.accepted.final_price = decision.price
                res.accepted.reservation_code = f"LLM-{int(time.time())}"
            elif decision.action == "counter":
                res.countered.proposed_price = decision.price
                res.countered.human_message = decision.message
                res.countered.reason_code = "NEGOTIATION_ONGOING"
            elif decision.action == "reject":
                res.rejected.reason_code = "OFFER_TOO_LOW"
            elif decision.action == "ui_required":
                res.ui_required.template_id = "high_value_confirm"
                res.ui_required.context_data["reason"] = decision.message
            return res
        except Exception:  # nosec B112
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="AI_ERROR")
            )


class DSPyStrategy:
    def __init__(self, model: str, compiled_program_path: str = "aura_brain.json"):
        self.negotiator = load_brain(compiled_program_path)
        self.fallback_strategy: Any = None
        dspy.configure(lm=dspy.LM(model=model))

    def _get_fallback_strategy(self) -> Any:
        if self.fallback_strategy is None:
            # Note: This strategy needs an API key which is not passed here.
            # Legacy code, keeping for compatibility.
            self.fallback_strategy = LiteLLMStrategy(model="gpt-3.5-turbo")
        return self.fallback_strategy

    def _create_standard_context(self, item: Any) -> dict[str, Any]:
        meta = (
            item.get("meta", {})
            if isinstance(item, dict)
            else getattr(item, "meta", {})
        )
        item_id = (
            item.get("id", "unknown")
            if isinstance(item, dict)
            else getattr(item, "id", "unknown")
        )
        base_p = (
            item.get("base_price", 0.0)
            if isinstance(item, dict)
            else getattr(item, "base_price", 0.0)
        )
        floor_p = (
            item.get("floor_price", 0.0)
            if isinstance(item, dict)
            else getattr(item, "floor_price", 0.0)
        )

        default_value_adds = [
            {"item": "Breakfast for two", "internal_cost": 20, "perceived_value": 60},
            {"item": "Late checkout", "internal_cost": 0, "perceived_value": 40},
            {"item": "Room upgrade", "internal_cost": 30, "perceived_value": 120},
        ]

        return {
            "item_id": item_id,
            "base_price": base_p,
            "floor_price": floor_p,
            "internal_cost": meta.get("internal_cost", floor_p * 0.8),
            "occupancy": meta.get("occupancy", "medium"),
            "value_add_inventory": meta.get("value_add_inventory", default_value_adds),
        }

    def evaluate(
        self, item: Any, bid: float, reputation: float, request_id: str | None = None
    ) -> negotiation_pb2.NegotiateResponse:
        if not item:
            return negotiation_pb2.NegotiateResponse(
                rejected=negotiation_pb2.OfferRejected(reason_code="ITEM_NOT_FOUND")
            )
        ctx = self._create_standard_context(item)
        result = self.negotiator(input_bid=bid, context=ctx, history=[])
        action_data = result["action"]
        res = negotiation_pb2.NegotiateResponse()
        if action_data["action"] == "accept":
            res.accepted.final_price = action_data["price"]
            res.accepted.reservation_code = f"DSPY-{int(time.time())}"
        elif action_data["action"] == "counter":
            res.countered.proposed_price = action_data["price"]
            res.countered.human_message = action_data["message"]
            res.countered.reason_code = "NEGOTIATION_ONGOING"
        elif action_data["action"] == "reject":
            res.rejected.reason_code = "OFFER_TOO_LOW"
        return res
