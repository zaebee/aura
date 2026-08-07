from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeeperSettings(BaseSettings):  # type: ignore
    model_config = SettingsConfigDict(
        env_prefix="AURA_",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    llm__api_key: str = Field(..., alias="AURA_LLM__API_KEY")
    llm__model: str = Field("gpt-4o-mini", alias="AURA_LLM__MODEL")
    llm__fallback_model: str = Field("ollama/llama3", alias="AURA_LLM__FALLBACK_MODEL")
    llm__ollama_base_url: str = Field(
        "http://localhost:11434", alias="AURA_LLM__OLLAMA_BASE_URL"
    )

    prometheus_url: str = Field(
        "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090",
        alias="AURA_PROMETHEUS_URL",
    )
    loki_url: str = Field(
        "http://loki.monitoring.svc.cluster.local:3100",
        alias="AURA_LOKI_URL",
    )
    nats_url: str = Field(
        "nats://nats:4222",
        validation_alias=AliasChoices(
            "AURA_DATABASE__NATS_URL", "AURA_NATS_URL", "NATS_URL"
        ),
    )

    admin_chat_id: int = Field(0, alias="AURA_BEE_KEEPER__ADMIN_CHAT_ID")

    github_token: str = Field("mock", alias="GITHUB_TOKEN")
    github_repository: str = Field(..., alias="GITHUB_REPOSITORY")
    github_event_path: str | None = Field(None, alias="GITHUB_EVENT_PATH")
    github_event_name: str = Field("manual", alias="GITHUB_EVENT_NAME")
    github_cc_recipients: str = Field("@jules", alias="GITHUB_CC_RECIPIENTS")

    max_tokens: int = Field(1000, alias="AURA_BEE_KEEPER__MAX_TOKENS")

    # Metabolism instrumentation (Gate 0)
    metabolism_log: str = Field(".hive/metabolism.jsonl", alias="AURA_METABOLISM_LOG")
    git_sha: str = Field("", alias="GITHUB_SHA")
