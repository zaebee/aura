import json
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import NoDecode
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

    # Filesystem scan: directories to exclude (comma-separated, or a JSON array)
    exclude_dirs: Annotated[list[str], NoDecode] = Field(
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

    @field_validator("exclude_dirs", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """
        Accept `.git,.venv` as well as `[".git", ".venv"]`.

        pydantic-settings JSON-decodes env values for a list field inside the
        env source, *before* field validation — so the comma-separated form the
        comment above promised failed at startup, and a validator alone would
        never have seen the raw string. `NoDecode` on the annotation is what
        hands it here intact. Nobody wants to write a JSON array in a shell for
        a list of directory names.

        Split here rather than at each use: the api-gateway spells its own
        comma-separated settings as `str` and calls `.split(",")` wherever it
        needs them, which duplicates the stripping and the empty-entry filter
        across call sites. Doing it once at the boundary keeps the field typed
        as what it is.

        An empty string yields an empty list — a deliberate "exclude nothing",
        distinct from the variable being unset, which keeps the defaults.
        """
        if not isinstance(value, str):
            return value

        text = value.strip()
        # `NoDecode` means nothing decodes JSON for us any more, so anything
        # already deployed with an array has to be handled here or it would
        # break — the one format that used to work must keep working.
        if text.startswith("["):
            return json.loads(text)

        return [part.strip() for part in text.split(",") if part.strip()]

    # Max chars of issue body passed to the LLM
    issue_body_limit: int = Field(500, alias="EVOLVER_ISSUE_BODY_LIMIT")

    # Metabolism instrumentation (Gate 0)
    metabolism_log: str = Field(".hive/metabolism.jsonl", alias="AURA_METABOLISM_LOG")
    git_sha: str = Field("", alias="GITHUB_SHA")
    # When true the Connector opens no Issues/PRs and sends no Telegram pulse.
    dry_run: bool = Field(False, alias="EVOLVER_DRY_RUN")
