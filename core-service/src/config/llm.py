from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_raw_key(key_field: SecretStr | str) -> str:
    """
    Safely retrieve the raw string value from a SecretStr or a plain string.
    Fixes AttributeError: 'str' object has no attribute 'get_secret_value'.
    """
    if isinstance(key_field, SecretStr):
        return key_field.get_secret_value()
    return key_field  # It's already a string


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

    @field_validator("model")
    @classmethod
    def validate_model_prefix(cls, v: str) -> str:
        if "/" not in v:
            return f"mistral/{v}"
        return v
