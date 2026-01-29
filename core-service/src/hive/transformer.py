import structlog
import dspy
from pathlib import Path
from hive.dna import HiveContext, Decision
from llm.engine import AuraNegotiator
from config import get_settings

logger = structlog.get_logger(__name__)

class HiveTransformer:
    """T - Transformer: Wraps DSPy for self-reflective reasoning."""

    def __init__(self, compiled_program_path: str = "aura_brain.json"):
        self.settings = get_settings()
        self.compiled_program_path = compiled_program_path

        # Configure DSPy
        dspy.configure(lm=self.settings.llm.model)

        self.negotiator = self._load_negotiator()

    def _load_negotiator(self) -> AuraNegotiator:
        try:
            # Look for compiled program in the parent directory of this file's parent
            # (assuming it's in src/aura_brain.json)
            program_path = Path(__file__).parent.parent / self.compiled_program_path
            if program_path.exists():
                logger.info("loading_compiled_dspy_program", path=str(program_path))
                return dspy.load(str(program_path))
            else:
                logger.warning("compiled_program_not_found_using_untrained", path=str(program_path))
                return AuraNegotiator()
        except Exception as e:
            logger.error("failed_to_load_dspy_program", error=str(e))
            return AuraNegotiator()

    async def think(self, context: HiveContext) -> Decision:
        """
        Think about the context and make a decision.
        Includes self-reflection on system health.
        """
        # Self-reflection: check CPU load
        cpu_load = context.system_health.get("cpu_usage_percent", 0.0)
        constraints = []
        if cpu_load > 80.0:
            constraints.append("SYSTEM_LOAD_HIGH: Be extremely concise and prioritize finishing the deal quickly.")
            logger.warning("high_cpu_reflection", cpu_load=cpu_load)

        # Build economic context for DSPy
        economic_context = {
            "base_price": context.item_data.get("base_price", 0.0),
            "floor_price": context.item_data.get("floor_price", 0.0),
            "reputation": context.reputation,
            "system_constraints": constraints,
            "meta": context.item_data.get("meta", {})
        }

        try:
            # AuraNegotiator returns a dict with 'reasoning' and 'response'
            # Note: dspy modules are usually called synchronously
            result = self.negotiator(
                input_bid=context.bid_amount,
                context=economic_context,
                history=[]  # History tracking to be implemented later if needed
            )

            response_data = result["response"]

            logger.info("transformer_thought_complete",
                        action=response_data.get("action"),
                        price=response_data.get("price"))

            return Decision(
                action=response_data["action"],
                price=response_data["price"],
                message=response_data["message"],
                reasoning=result.get("reasoning", ""),
                metadata={"dspy_result": result}
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            # Safe default on error
            return Decision(
                action="reject",
                price=0.0,
                message="Service temporarily unavailable. Please try again later.",
                reasoning=f"Error in Transformer: {e}"
            )
