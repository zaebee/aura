from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeeperSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_", env_nested_delimiter="__", extra="ignore"
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
    nats_url: str = Field("nats://nats:4222", alias="AURA_NATS_URL")

    github_token: str = Field(..., alias="GITHUB_TOKEN")
    github_repository: str = Field(..., alias="GITHUB_REPOSITORY")
    github_event_path: str | None = Field(None, alias="GITHUB_EVENT_PATH")
