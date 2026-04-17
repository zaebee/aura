from dataclasses import dataclass, field
from typing import Literal


ImprovementType = Literal["code", "prompt", "doc", "issue"]


@dataclass
class Improvement:
    """A single concrete improvement proposed by the Evolver."""

    type: ImprovementType
    title: str
    description: str
    # File to patch (for code/prompt/doc types)
    target_file: str | None = None
    # Unified diff or full replacement content
    patch: str | None = None
    # Body for a GitHub Issue (for issue type, or supplementary for others)
    issue_body: str | None = None
    # GitHub Issue URL after creation (populated by Connector)
    issue_url: str | None = None


@dataclass
class HiveContext:
    """Aggregated snapshot of the Hive's current state."""

    git_log: str = ""
    hive_state: str = ""
    open_issues: list[dict] = field(default_factory=list)
    open_prs: list[dict] = field(default_factory=list)
    filesystem_map: list[str] = field(default_factory=list)
    keeper_prompt: str = ""
    recent_heresies: list[str] = field(default_factory=list)
    focus_hint: str = ""


@dataclass
class EvolutionPlan:
    """Output of the Transformer: ordered list of improvements + metabolic summary."""

    improvements: list[Improvement] = field(default_factory=list)
    # Short narrative for Telegram pulse
    narrative: str = ""
    token_usage: int = 0
    # True if the LLM determined no improvements are needed
    hive_is_optimal: bool = False


@dataclass
class EvolverObservation:
    """Result of a full evolutionary cycle (output of Connector)."""

    success: bool
    pr_url: str = ""
    issue_urls: list[str] = field(default_factory=list)
    branch_name: str = ""
    telegram_sent: bool = False
    errors: list[str] = field(default_factory=list)
    plan: EvolutionPlan | None = None
