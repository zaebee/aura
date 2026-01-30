from pydantic import AliasChoices, BaseModel, Field, SecretStr


def get_raw_key(key_field):
    """
    Safely retrieve the raw string value from a SecretStr or a plain string.
    Fixes AttributeError: 'str' object has no attribute 'get_secret_value'.
    """
    if hasattr(key_field, "get_secret_value"):
        return key_field.get_secret_value()
    return key_field  # It's already a string


class LLMSettings(BaseModel):
    model: str = Field(
        "mistral-large-latest",
        validation_alias=AliasChoices("AURA_LLM__MODEL", "LLM_MODEL"),
    )
    api_key: SecretStr = Field(
        "",
        validation_alias=AliasChoices("AURA_LLM__API_KEY", "API_KEY"),
    )
    mistral_api_key: SecretStr = Field(
        "",
        validation_alias=AliasChoices(
            "AURA_LLM__MISTRAL_API_KEY", "AURA_LLM__API_KEY", "MISTRAL_API_KEY"
        ),
    )
    openai_api_key: SecretStr = Field(
        "",
        validation_alias=AliasChoices("AURA_LLM__OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    temperature: float = 0.7
    compiled_program_path: str = "aura_brain.json"
