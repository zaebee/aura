import hashlib
import time
from typing import Any, cast

import structlog
from aura_core import (
    FailureIntent,
    HiveContext,
    IntentAction,
    SkillRegistry,
    SystemVitals,
    Transformer,
    map_action,
    resolve_brain_path,
)
from aura_core.gen.aura.dna.v1 import ActionType

logger = structlog.get_logger(__name__)


class RuleBasedStrategy:
    """
    Rule-based pricing strategy that doesn't require an LLM.
    Integrated into Transformer as a fallback/deterministic mode.
    """

    def __init__(
        self,
        trigger_price: float = 1000.0,
    ):
        self.trigger_price = trigger_price

    def evaluate(
        self,
        item_data: dict[str, Any],
        bid: float,
        reputation: float,
        request_id: str | None = None,
    ) -> IntentAction:
        if not item_data:
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                price=0.0,
                message="Item not found",
                metadata={"reason_code": "ITEM_NOT_FOUND"},
                thought="<think>Item not found. Rejecting.</think>",
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_UI_REQUIRED),
                price=bid,
                message=f"Bid of ${bid} exceeds security threshold",
                metadata={"template_id": "high_value_confirm"},
                thought="<think>Bid exceeds security threshold. UI confirmation required.</think>",
            )

        floor_price = item_data.get("floor_price", 0.0)
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
                price=floor_price,
                message=f"We cannot accept less than ${floor_price}.",
                metadata={"reason_code": "BELOW_FLOOR"},
                thought=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            action=cast(ActionType, ActionType.ACTION_TYPE_ACCEPT),
            price=bid,
            message="Offer accepted.",
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
            thought="<think>Bid at or above floor price. Accepting.</think>",
        )


class AuraTransformer(Transformer[HiveContext, IntentAction]):
    """T - Transformer: Pure reasoning engine calling Reasoning Protein."""

    def __init__(self, registry: SkillRegistry, settings: Any = None):
        self.settings = settings
        self.registry = registry
        compiled_path = None
        if (
            settings
            and hasattr(settings, "llm")
            and hasattr(settings.llm, "compiled_program_path")
        ):
            compiled_path = settings.llm.compiled_program_path
        self.brain_path = resolve_brain_path(compiled_path)

    def _get_cpu_load(self, system_health: SystemVitals | dict[str, Any]) -> float:
        if isinstance(system_health, SystemVitals):
            return float(system_health.cpu_usage_percent)
        return float(system_health.get("cpu_usage_percent", 0.0))

    def _build_economic_context(self, context: HiveContext) -> dict:
        cpu_load = self._get_cpu_load(context.system_health)
        constraints = []
        if cpu_load > 80.0:
            constraints.append("SYSTEM_LOAD_HIGH: Be extremely concise.")

        return {
            "base_price": context.item_data.get("base_price", 0.0),
            "floor_price": context.item_data.get("floor_price", 0.0),
            "reputation": context.offer.reputation,
            "system_constraints": constraints,
            "meta": context.item_data.get("meta", {}),
        }

    async def think(self, context: HiveContext, **kwargs: Any) -> IntentAction:
        """Reason about the negotiation by calling the Reasoning Protein."""

        # 1. Semantic Bypass (Cache Check)
        item_id = context.item_id
        bid = context.offer.bid_amount
        base_price = context.item_data.get("base_price", 0.0)
        floor_price = context.item_data.get("floor_price", 0.0)

        # Create a stable context summary for hashing
        context_summary = f"base:{base_price},floor:{floor_price}"
        cache_raw = f"{item_id}:{bid}:{context_summary}"
        cache_key = f"semantic_cache:{hashlib.sha256(cache_raw.encode()).hexdigest()}"

        try:
            cache_obs = await self.registry.execute(
                "persistence", "get_cache", {"key": cache_key}
            )
            if cache_obs.success and cache_obs.data:
                logger.info(
                    "cache_hit",
                    item_id=item_id,
                    bid=bid,
                    latency_ms=0,
                    tokens_used=0,
                )
                cached_data = cache_obs.data
                return IntentAction(
                    action=cast(ActionType, map_action(cached_data["action"])),
                    price=cached_data["price"],
                    message=cached_data["message"],
                    thought=cached_data.get("thought", ""),
                    metadata={
                        **cached_data.get("metadata", {}),
                        "cached": True,
                    },
                )
        except Exception as e:
            logger.warning("cache_lookup_failed", error=str(e))

        # Rule-based fallback if requested
        if self.settings and self.settings.llm.model.lower() == "rule":
            strategy = RuleBasedStrategy(
                trigger_price=self.settings.safety.ui_trigger_price
            )
            return strategy.evaluate(
                context.item_data,
                context.offer.bid_amount,
                context.offer.reputation,
                context.request_id,
            )

        try:
            # Call Reasoning Protein
            obs = await self.registry.execute(
                "reasoning",
                "negotiate",
                {
                    "bid": context.offer.bid_amount,
                    "context": self._build_economic_context(context),
                    "history": [],
                },
            )

            if not obs.success:
                # 2. Rate Limit Awareness - Fallback to Rule-based Strategy
                if obs.error and "RateLimitError" in obs.error:
                    logger.warning(
                        "rate_limit_detected_falling_back_to_rule_strategy",
                        error=obs.error,
                    )
                    strategy = RuleBasedStrategy(
                        trigger_price=getattr(self.settings.safety, "ui_trigger_price", 1000.0) if self.settings else 1000.0
                    )
                    return strategy.evaluate(
                        context.item_data,
                        context.offer.bid_amount,
                        context.offer.reputation,
                        context.request_id,
                    )

                logger.error("reasoning_protein_failed", error=obs.error)
                return FailureIntent(error=obs.error or "unknown_error")

            result = obs.data

            # Implement <think> tag logic for transparency
            raw_thought = result.get("thought", "")
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            intent = IntentAction(
                action=cast(ActionType, map_action(result["action"])),
                price=result["price"],
                message=result["message"],
                thought=wrapped_thought,
                metadata={
                    **result.get("metadata", {}),
                    "brain_path": self.brain_path,
                },
            )

            # 3. Save to Redis (TTL: 1 hour)
            try:
                # Convert IntentAction to serializable dict
                cache_value = {
                    "action": str(intent.action),
                    "price": intent.price,
                    "message": intent.message,
                    "thought": intent.thought,
                    "metadata": intent.metadata,
                }
                await self.registry.execute(
                    "persistence",
                    "set_cache",
                    {"key": cache_key, "value": cache_value, "ttl": 3600},
                )
            except Exception as e:
                logger.warning("cache_save_failed", error=str(e))

            return intent

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return FailureIntent(error=str(e))
