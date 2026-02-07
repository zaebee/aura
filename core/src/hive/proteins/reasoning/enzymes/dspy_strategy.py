import time
from pathlib import Path
from typing import Any

import dspy
import litellm
from jinja2 import Template
from pydantic import BaseModel

from hive.proto.aura.negotiation.v1 import negotiation_pb2
from .engine import load_brain

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
