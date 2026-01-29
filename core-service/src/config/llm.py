from pydantic import AliasChoices, BaseModel, Field, SecretStr


class LLMSettings(BaseModel):
    model: str = Field(
        "mistral-large-latest",
        validation_alias=AliasChoices("AURA_LLM__MODEL", "LLM_MODEL"),
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
