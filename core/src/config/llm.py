from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_LLM__",
        extra="ignore",
        populate_by_name=True,
    )

    model: str = Field(
        "mistral/mistral-large-latest",
        validation_alias=AliasChoices("AURA_LLM__MODEL", "LLM_MODEL"),
    )
    api_key: SecretStr = Field("")  # type: ignore
    openai_api_key: SecretStr = Field("")  # type: ignore
    temperature: float = 0.7
    compiled_program_path: str = "aura_brain.json"

    @field_validator("model", mode="before")
    @classmethod
    def ensure_provider_prefix(cls, v: str) -> str:
        """Ensure model name always includes a provider prefix."""
        if isinstance(v, str) and "/" not in v:
            return f"mistral/{v}"
        return v

    @model_validator(mode="after")
    def validate_api_keys(self) -> "LLMSettings":
        """Validate API keys are present for non-rule-based models."""
        if self.model.startswith("mistral/"):
            if not self.api_key or not self.api_key.get_secret_value():
                raise ValueError(
                    "AURA_LLM__API_KEY is required for Mistral models. "
                    "Set AURA_LLM__API_KEY environment variable."
                )
        elif self.model.startswith("openai/"):
            if not self.openai_api_key or not self.openai_api_key.get_secret_value():
                raise ValueError(
                    "AURA_LLM__OPENAI_API_KEY is required for OpenAI models. "
                    "Set AURA_LLM__OPENAI_API_KEY environment variable."
                )
        return self
