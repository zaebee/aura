"""
Universal LLM client wrapper using litellm.

Provides a consistent interface for calling any LLM provider (OpenAI, Mistral,
Anthropic, Ollama, etc.) with structured output support.
Also includes DSPy-based negotiation module for self-optimizing decisions.
"""

import json
from typing import Any

import dspy
import litellm
import structlog
from pydantic import BaseModel

from src.llm.prepare.clean import clean_and_parse_json
from src.llm.signatures import Negotiate

logger = structlog.get_logger(__name__)


class AuraNegotiator(dspy.Module):
    """DSPy-based negotiation module with structured reasoning.

    This module uses the Negotiate signature to make optimized negotiation decisions
    based on economic context and training examples.
    """

    def __init__(self) -> None:
        super().__init__()
        # Use Predict instead of ChainOfThought because 'thought' is explicitly in signature
        self.negotiate = dspy.Predict(Negotiate)
        logger.info("dspy_negotiator_initialized", module="AuraNegotiator")

    def forward(
        self, input_bid: float, context: Any, history: Any = None
    ) -> dict[str, Any]:
        """Forward pass for negotiation decision.

        Args:
            input_bid: Buyer's current offer amount
            context: Economic context (dict or JSON string)
            history: Negotiation history (list or JSON string)

        Returns:
            Dictionary containing 'thought' and 'action' (parsed dict)
        """
        # 1. Normalize inputs to JSON strings for DSPy
        history_json = (
            history if isinstance(history, str) else json.dumps(history or [])
        )
        context_json = context if isinstance(context, str) else json.dumps(context)

        logger.debug(
            "dspy_forward_pass_started",
            input_bid=input_bid,
            history_length=len(history or [])
            if not isinstance(history, str)
            else "N/A",
        )

        # 2. Execute DSPy prediction
        prediction = self.negotiate(
            input_bid=str(input_bid), context=context_json, history=history_json
        )

        # 3. Parse and validate JSON action
        try:
            raw_action = prediction.action
            action_data = clean_and_parse_json(raw_action)

            # Validation: ensure required keys exist
            for key in ["action", "price", "message"]:
                if key not in action_data:
                    raise ValueError(f"Missing required key '{key}' in LLM action")

            logger.info(
                "dspy_decision_made",
                action=action_data.get("action", "unknown"),
                price=action_data.get("price", 0),
                thought_length=len(prediction.thought),
            )

            # 4. Return clean dictionary
            return {
                "thought": prediction.thought,
                "action": action_data,
            }

        except Exception as e:
            logger.error(
                "dspy_parsing_failed",
                error=str(e),
                raw_action=getattr(prediction, "action", "N/A"),
            )
            raise ValueError(f"Failed to parse negotiator action: {e}") from e


class LLMEngine:
    """Universal LLM client supporting multiple providers via litellm."""

    def __init__(
        self, model: str, temperature: float = 0.7, api_key: str | None = None
    ):
        """
        Initialize LLM engine.
        """
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        logger.info(
            "llm_engine_initialized",
            model=model,
            temperature=temperature,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        """
        Call LLM with structured output support.
        """
        try:
            logger.debug(
                "llm_call_started",
                model=self.model,
                message_count=len(messages),
                structured_output=response_format is not None,
            )

            # Call litellm with optional structured output
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }

            if self.api_key:
                kwargs["api_key"] = self.api_key

            if response_format:
                kwargs["response_model"] = response_format

            response = litellm.completion(**kwargs)

            # Extract content
            content = response.choices[0].message.content

            # Return parsed structured output if requested
            if response_format:
                logger.info(
                    "llm_call_completed",
                    model=self.model,
                    structured=True,
                )
                return content  # type: ignore
            else:
                logger.info(
                    "llm_call_completed",
                    model=self.model,
                    structured=False,
                    response_length=len(content),
                )
                return content  # type: ignore

        except Exception as e:
            logger.error(
                "llm_unexpected_error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise
