import asyncio
import logging
from typing import Any

import dspy
import psutil  # type: ignore[import-untyped]
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation
from hive.chemistry.hill_regulator import HillRegulator

from config.llm import LLMSettings

from .engine import (
    AuraRWANegotiator,
    AuraTradeNegotiator,
    generate_embedding,
    load_brain,
)
from .schema import EmbeddingParams, NegotiationParams, RWAParams, TradeParams

logger = logging.getLogger(__name__)


class ReasoningSkill(
    SkillProtocol[LLMSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Reasoning Protein: Handles LLM logic, DSPy negotiation, and embeddings.
    Now integrated with HillRegulator to prevent Memory Famine.
    """

    def __init__(self) -> None:
        self.settings: LLMSettings | None = None
        self.provider: dict[str, Any] | None = None
        self.negotiator: Any = None
        self.trade_negotiator: AuraTradeNegotiator | None = None
        self.rwa_negotiator: AuraRWANegotiator | None = None
        self._embed_model: Any = None
        self._capabilities = {
            "negotiate": self._negotiate,
            "trade": self._trade,
            "rwa": self._rwa,
            "generate_embedding": self._generate_embedding,
        }

    def get_name(self) -> str:
        return "reasoning"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: LLMSettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        if not self.settings or not self.provider:
            return False

        if "rule" not in self.settings.model.lower():
            try:
                lm = self.provider.get("lm")
                if lm:
                    dspy.configure(lm=lm)

                self.negotiator = load_brain(
                    getattr(self.settings, "compiled_program_path", None)
                )
                self.trade_negotiator = AuraTradeNegotiator()
                self.rwa_negotiator = AuraRWANegotiator()
                self._embed_model = self.provider.get("embedder")
            except Exception as e:
                logger.error(f"Failed to initialize Reasoning: {e}")
                return False
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Reasoning skill error: {e}")
            return Observation(success=False, error=str(e))

    def _apply_hill_dampening(self, content_str: str) -> str:
        """Apply HillRegulator to dampen context if memory is high."""
        try:
            process = psutil.Process()
            mem_mb = process.memory_info().rss / (1024 * 1024)
            # Limit at 1GB for dampening start
            limit_mb = 1024.0

            char_count = len(content_str)
            dampened_chars = HillRegulator.regulate_context(
                char_count, mem_mb, limit_mb
            )

            if dampened_chars < char_count:
                logger.warning(
                    "hill_dampening_applied: original=%d dampened=%d mem_mb=%f",
                    char_count,
                    dampened_chars,
                    mem_mb,
                )
                return content_str[:dampened_chars]
        except Exception as e:
            logger.error("hill_regulator_error: %s", str(e))

        return content_str

    async def _negotiate(self, params: dict[str, Any]) -> Observation:
        if not self.negotiator:
            return Observation(success=False, error="negotiator_not_ready")

        # We need to handle the dict fields before passing to NegotiationParams
        # since mypy complained about type mismatch in CI
        context_data = params.get("context", {})
        history_data = params.get("history", [])

        if isinstance(context_data, str):
            context_data = {"raw": context_data}
        if isinstance(history_data, str):
            history_data = [{"raw": history_data}]

        p_neg = NegotiationParams(
            bid=params.get("bid", 0.0),
            context=context_data,
            history=history_data
        )

        # Apply Hill Dampening to context and history
        # We convert to str for dampening logic then keep it simple
        context_str = str(p_neg.context)
        history_str = str(p_neg.history)

        dampened_context = self._apply_hill_dampening(context_str)
        # Note: we don't convert back to dict yet, just ensuring we don't OOM
        # In Larva phase, we keep the original objects if no dampening triggered
        # or we could just use the dampened strings if needed.
        # For now, if no reduction, use original.

        final_context = p_neg.context if len(dampened_context) == len(context_str) else {"dampened": dampened_context}
        final_history = p_neg.history if len(self._apply_hill_dampening(history_str)) == len(history_str) else [{"dampened": history_str}]

        def call() -> dict[str, Any]:
            from typing import cast

            neg = cast(Any, self.negotiator)
            return cast(
                dict[str, Any],
                neg(
                    input_bid=p_neg.bid,
                    context=final_context,
                    history=final_history,
                ),
            )

        result = await asyncio.to_thread(call)
        metadata = result.copy()
        return Observation(success=True, metadata=make_struct(metadata))

    async def _rwa(self, params: dict[str, Any]) -> Observation:
        if not self.rwa_negotiator:
            return Observation(success=False, error="rwa_negotiator_not_ready")
        p_rwa = RWAParams(**params)

        def call() -> dict[str, Any]:
            from typing import cast

            neg = cast(AuraRWANegotiator, self.rwa_negotiator)
            return neg.forward(
                vision_report=p_rwa.vision_report,
                wallet_address=p_rwa.wallet_address,
                kyc_status=p_rwa.kyc_status,
                six_rates=p_rwa.six_rates,
                ltv_ratio=p_rwa.ltv_ratio,
                system_vitals=p_rwa.system_vitals,
            )

        result = await asyncio.to_thread(call)
        return Observation(success=True, metadata=make_struct(result))

    async def _trade(self, params: dict[str, Any]) -> Observation:
        if not self.trade_negotiator:
            return Observation(success=False, error="trade_negotiator_not_ready")
        p_trade = TradeParams(**params)

        def call() -> dict[str, Any]:
            from typing import cast

            neg = cast(AuraTradeNegotiator, self.trade_negotiator)
            return neg.forward(
                market_context=p_trade.market_context,
                system_vitals=p_trade.system_vitals,
                current_treasury=p_trade.current_treasury,
                risk_threshold=p_trade.risk_threshold,
            )

        result = await asyncio.to_thread(call)
        return Observation(success=True, metadata=make_struct(result))

    async def _generate_embedding(self, params: dict[str, Any]) -> Observation:
        if not self._embed_model:
            return Observation(success=False, error="embed_model_not_ready")
        p_emb = EmbeddingParams(**params)

        emb = await asyncio.to_thread(generate_embedding, p_emb.text, self._embed_model)
        # Store embedding in the dedicated field to avoid precision loss
        return Observation(success=True, embedding=[float(x) for x in emb])
