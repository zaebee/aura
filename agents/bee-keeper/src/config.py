from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeeperSettings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(
        env_prefix="AURA_", env_nested_delimiter="__", extra="ignore", populate_by_name=True
    )

    llm__api_key: str = Field(..., alias="AURA_LLM__API_KEY")
    llm__model: str = Field("gpt-4o-mini", alias="AURA_LLM__MODEL")
    llm__fallback_model: str = Field("ollama/llama3", alias="AURA_LLM__FALLBACK_MODEL")
    llm__ollama_base_url: str = Field(
        "http://localhost:11434", alias="AURA_LLM__OLLAMA_BASE_URL"
    )

    prometheus_url: str = Field(
        "http://prometheus-kube-prometheus-prometheus.monitoring:9090",
        alias="AURA_PROMETHEUS_URL",
    )
    nats_url: str = Field(
        "nats://nats:4222",
        validation_alias=AliasChoices(
            "AURA_DATABASE__NATS_URL", "AURA_NATS_URL", "NATS_URL"
        ),
    )

    github_token: str = Field(..., alias="GITHUB_TOKEN")
    github_repository: str = Field(..., alias="GITHUB_REPOSITORY")
    github_event_path: str | None = Field(None, alias="GITHUB_EVENT_PATH")
    github_event_name: str = Field("manual", alias="GITHUB_EVENT_NAME")

    max_tokens: int = Field(1000, alias="AURA_BEE_KEEPER__MAX_TOKENS")
