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
from llm.prepare.clean import clean_and_parse_json
from llm.signatures import Negotiate
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class AuraNegotiator(dspy.Module):
    """DSPy-based negotiation module with Chain-of-Thought reasoning.

    This module uses the Negotiate signature to make optimized negotiation decisions
    based on economic context and training examples.
    """

    def __init__(self):
        super().__init__()
        self.negotiate_chain = dspy.ChainOfThought(Negotiate)
        logger.info("dspy_negotiator_initialized", module="AuraNegotiator")

    def forward(self, input_bid: float, context: Any, history: Any = None) -> dict:
        """Forward pass for negotiation decision.

        Args:
            input_bid: Buyer's current offer amount
            context: Economic context (dict or JSON string)
            history: Negotiation history (list or JSON string)

        Returns:
            Dictionary containing 'reasoning' and 'response' (parsed dict)
        """
        # 1. Normalize inputs to JSON strings for DSPy (avoiding double-encoding)
        history_json = (
            history if isinstance(history, str) else json.dumps(history or [])
        )
        context_json = context if isinstance(context, str) else json.dumps(context)

        # 2. Extract keys for safe logging
        try:
            ctx_dict = (
                json.loads(context_json)
                if isinstance(context_json, str)
                else context_json
            )
            context_keys = list(ctx_dict.keys()) if isinstance(ctx_dict, dict) else []
        except Exception:
            context_keys = []

        logger.debug(
            "dspy_forward_pass_started",
            input_bid=input_bid,
            context_keys=context_keys,
            history_length=len(history or [])
            if not isinstance(history, str)
            else "N/A",
        )

        # 3. Execute DSPy chain
        prediction = self.negotiate_chain(
            input_bid=str(input_bid), context=context_json, history=history_json
        )

        # 4. Parse and validate JSON response
        try:
            raw_response = prediction.response
            response_data = clean_and_parse_json(raw_response)

            # Validation: ensure required keys exist
            for key in ["action", "price", "message"]:
                if key not in response_data:
                    raise ValueError(f"Missing required key '{key}' in LLM response")

            logger.info(
                "dspy_decision_made",
                action=response_data.get("action", "unknown"),
                price=response_data.get("price", 0),
                reasoning_length=len(prediction.reasoning),
            )

            # 5. Return clean dictionary
            return {
                "reasoning": prediction.reasoning,
                "response": response_data,
            }

        except Exception as e:
            logger.error(
                "dspy_parsing_failed",
                error=str(e),
                raw_response=getattr(prediction, "response", "N/A"),
            )
            raise ValueError(f"Failed to parse negotiator response: {e}") from e


class LLMEngine:
    """Universal LLM client supporting multiple providers via litellm."""

    def __init__(
        self, model: str, temperature: float = 0.7, api_key: str | None = None
    ):
        """
        Initialize LLM engine.

        Args:
            model: Model identifier in litellm format (e.g., "openai/gpt-4o",
                   "mistral/mistral-large-latest", "ollama/mistral")
            temperature: Sampling temperature (0.0-1.0)
            api_key: Optional API key for the provider
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

        Args:
            messages: List of message dicts with "role" and "content" keys
            response_format: Optional Pydantic model for structured output

        Returns:
            Parsed Pydantic model instance if response_format provided,
            otherwise raw string response

        Raises:
            litellm.AuthenticationError: Missing or invalid API key
            litellm.APIError: Provider API failure
            Exception: Other errors (parsing, network, etc.)
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
                return content
            else:
                logger.info(
                    "llm_call_completed",
                    model=self.model,
                    structured=False,
                    response_length=len(content),
                )
                return content

        except litellm.AuthenticationError as e:
            logger.error(
                "llm_authentication_error",
                model=self.model,
                error=str(e),
                hint="Check API key environment variable",
            )
            raise

        except litellm.APIError as e:
            logger.error(
                "llm_api_error",
                model=self.model,
                error=str(e),
                provider=self.model.split("/")[0] if "/" in self.model else "unknown",
            )
            raise

        except Exception as e:
            logger.error(
                "llm_unexpected_error",
                model=self.model,
                error=str(e),
                exc_info=True,
            )
            raise
