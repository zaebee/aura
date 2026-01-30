from pydantic import AliasChoices, BaseModel, Field, SecretStr


def get_raw_key(key_field):
    """
    Safely retrieve the raw string value from a SecretStr or a plain string.
    Fixes AttributeError: 'str' object has no attribute 'get_secret_value'.
    """
    if isinstance(key_field, SecretStr):
        return key_field.get_secret_value()
    return key_field  # It's already a string


class LLMSettings(BaseModel):
    model: str = Field(
        "mistral-large-latest",
        validation_alias=AliasChoices("AURA_LLM__MODEL", "LLM_MODEL"),
    )
    api_key: SecretStr = Field(...)
    openai_api_key: SecretStr = Field(...)
    temperature: float = 0.7
    compiled_program_path: str = "aura_brain.json"
