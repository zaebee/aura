"""
Universal LLM client wrapper using litellm.

Provides a consistent interface for calling any LLM provider (OpenAI, Mistral,
Anthropic, Ollama, etc.) with structured output support.
"""

from typing import Any, Type

import litellm
import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class LLMEngine:
    """Universal LLM client supporting multiple providers via litellm."""

    def __init__(self, model: str, temperature: float = 0.7):
        """
        Initialize LLM engine.

        Args:
            model: Model identifier in litellm format (e.g., "openai/gpt-4o",
                   "mistral/mistral-large-latest", "ollama/mistral")
            temperature: Sampling temperature (0.0-1.0)
        """
        self.model = model
        self.temperature = temperature
        logger.info(
            "llm_engine_initialized",
            model=model,
            temperature=temperature,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: Type[BaseModel] | None = None,
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

            if response_format:
                kwargs["response_format"] = response_format

            response = litellm.completion(**kwargs)

            # Extract content
            content = response.choices[0].message.content

            # Parse structured output if requested
            if response_format:
                result = response_format.model_validate_json(content)
                logger.info(
                    "llm_call_completed",
                    model=self.model,
                    structured=True,
                )
                return result
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
