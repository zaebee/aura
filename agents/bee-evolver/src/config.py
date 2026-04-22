from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvolverSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AURA_",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    llm__api_key: str = Field(..., alias="AURA_LLM__API_KEY")
    llm__model: str = Field("mistral/mistral-large-latest", alias="AURA_LLM__MODEL")
    llm__fallback_model: str = Field(
        "openai/gpt-4o-mini", alias="AURA_LLM__FALLBACK_MODEL"
    )
    llm__ollama_base_url: str = Field(
        "http://localhost:11434", alias="AURA_LLM__OLLAMA_BASE_URL"
    )

    github_token: str = Field("mock", alias="GITHUB_TOKEN")
    github_repository: str = Field(..., alias="GITHUB_REPOSITORY")
    github_event_name: str = Field("manual", alias="GITHUB_EVENT_NAME")

    telegram_token: str = Field("", alias="AURA_TELEGRAM_TOKEN")
    admin_chat_id: int = Field(
        0,
        validation_alias=AliasChoices(
            "AURA_BEE_KEEPER__ADMIN_CHAT_ID", "AURA_ADMIN_CHAT_ID"
        ),
    )

    evolver_assignee: str = Field("zaebee", alias="EVOLVER_ASSIGNEE")
    # Optional free-text focus hint passed via workflow_dispatch input
    evolver_focus: str = Field("", alias="EVOLVER_FOCUS")
    max_improvements: int = Field(3, alias="EVOLVER_MAX_IMPROVEMENTS")
    max_tokens: int = Field(2000, alias="AURA_BEE_EVOLVER__MAX_TOKENS")

    # Filesystem scan: directories to exclude (comma-separated)
    exclude_dirs: list[str] = Field(
        default=[
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            "gen-proto",
            "gen",
            ".mypy_cache",
            ".ruff_cache",
        ],
        alias="EVOLVER_EXCLUDE_DIRS",
    )
    # GitHub Issues pagination limit
    issues_per_page: int = Field(20, alias="EVOLVER_ISSUES_PER_PAGE")
    # Max chars of issue body passed to the LLM
    issue_body_limit: int = Field(500, alias="EVOLVER_ISSUE_BODY_LIMIT")
