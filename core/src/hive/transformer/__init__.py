import asyncio
import time
from pathlib import Path
from typing import Any, Protocol

import dspy
import structlog
from aura_core import (
    FailureIntent,
    HiveContext,
    IntentAction,
    SystemVitals,
    Transformer,
)

from config import get_settings
from hive.aggregator import InventoryItem, SessionLocal
from hive.metabolism.logging_config import bind_request_id

from .llm.engine import AuraNegotiator

logger = structlog.get_logger(__name__)

# --- 1. Rule-Based Strategy (The Hive's Instincts) ---


class ItemRepository(Protocol):
    """Protocol for item repository to enable dependency injection."""

    def get_item(self, item_id: str) -> InventoryItem | None: ...


class DatabaseItemRepository:
    """Default repository implementation using the database."""

    def get_item(self, item_id: str) -> InventoryItem | None:
        session = SessionLocal()
        try:
            return session.query(InventoryItem).filter_by(id=item_id).first()
        finally:
            session.close()


class RuleBasedStrategy:
    """
    Rule-based pricing strategy that doesn't require an LLM.
    Integrated into Transformer as a fallback/deterministic mode.
    """

    def __init__(
        self,
        repository: ItemRepository | None = None,
        trigger_price: float = 1000.0,
    ):
        self.repository = repository or DatabaseItemRepository()
        self.trigger_price = trigger_price

    def evaluate(
        self, item_id: str, bid: float, reputation: float, request_id: str | None = None
    ) -> IntentAction:
        if request_id:
            bind_request_id(request_id)

        item = self.repository.get_item(item_id)
        if not item:
            return IntentAction(
                action="reject",
                price=0.0,
                message="Item not found",
                metadata={"reason_code": "ITEM_NOT_FOUND"},
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                action="ui_required",
                price=bid,
                message=f"Bid of ${bid} exceeds security threshold",
                metadata={"template_id": "high_value_confirm"},
            )

        # Rule: Bid below floor price - counter with floor price
        if bid < item.floor_price:
            return IntentAction(
                action="counter",
                price=item.floor_price,
                message=f"We cannot accept less than ${item.floor_price}.",
                metadata={"reason_code": "BELOW_FLOOR"},
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            action="accept",
            price=bid,
            message="Offer accepted.",
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
        )


# --- 2. Aura Transformer (The Sovereign Brain) ---


class AuraTransformer(Transformer[HiveContext, IntentAction]):
    """T - Transformer: Pure reasoning engine using DSPy or deterministic rules."""

    def __init__(self, compiled_program_path: str | None = None):
        self.settings = get_settings()
        self.compiled_program_path = (
            compiled_program_path or self.settings.llm.compiled_program_path
        )

        # Default configuration
        self.negotiator: AuraNegotiator | None = None
        if self.settings.llm.model != "rule":
            dspy.configure(lm=dspy.LM(self.settings.llm.model))
            self.negotiator = self._load_negotiator()

    def _resolve_brain_path(self) -> str:
        search_paths = []
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.append(Path(self.settings.llm.compiled_program_path))

        search_paths.extend(
            [
                Path("/app/core/data/aura_brain.json"),
                Path("/app/data/aura_brain.json"),
                Path("./data/aura_brain.json"),
                Path("/app/core/src/aura_brain.json"),
                Path(__file__).parent.parent / "aura_brain.json",
            ]
        )

        for path in search_paths:
            try:
                if path.exists() and path.is_file():
                    return str(path.absolute())
            except OSError:
                continue
        return "UNKNOWN"

    def _load_negotiator(self) -> AuraNegotiator:
        try:
            resolved_path = self._resolve_brain_path()
            if resolved_path != "UNKNOWN":
                logger.info("loading_compiled_dspy_program", path=resolved_path)
                return dspy.load(resolved_path)  # type: ignore
            else:
                logger.warning("compiled_program_not_found_using_untrained")
                return AuraNegotiator()
        except Exception as e:
            logger.error("failed_to_load_dspy_program", error=str(e))
            return AuraNegotiator()

    def _get_cpu_load(self, system_health: SystemVitals | dict[str, Any]) -> float:
        """Safely extracts CPU load from either SystemVitals or a dictionary."""
        if isinstance(system_health, SystemVitals):
            return system_health.cpu_usage_percent
        return float(system_health.get("cpu_usage_percent", 0.0))

    def _build_economic_context(self, context: HiveContext) -> dict:
        """Construct pure economic context without infrastructure leakage."""
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
        """
        Reason about the negotiation using self-reflective tuning.
        Returns a strictly typed IntentAction.
        """
        # モード check: Deterministic Rule mode
        if self.settings.llm.model == "rule" or self.negotiator is None:
            strategy = RuleBasedStrategy()
            return strategy.evaluate(
                context.item_id,
                context.offer.bid_amount,
                context.offer.reputation,
                context.request_id,
            )

        cpu_load = self._get_cpu_load(context.system_health)

        # Self-reflective tuning: adjust model and temperature based on system health
        model = self.settings.llm.model
        temperature = self.settings.llm.temperature

        if cpu_load > 80.0:
            model = "mistral-small-latest"
            temperature = 0.1
            logger.warning(
                "reflective_tuning_applied", reason="high_cpu", cpu_load=cpu_load
            )

        try:
            with dspy.context(lm=dspy.LM(model, temperature=temperature)):
                result = await asyncio.to_thread(
                    self.negotiator,
                    input_bid=context.offer.bid_amount,
                    context=self._build_economic_context(context),
                    history=[],
                )

            action_data = result["action"]

            return IntentAction(
                action=action_data["action"],
                price=action_data["price"],
                message=action_data["message"],
                thought=result.get("thought", ""),
                metadata={"dspy_result": result, "model_used": model},
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return FailureIntent(error=str(e), metadata={"context": str(context)})
