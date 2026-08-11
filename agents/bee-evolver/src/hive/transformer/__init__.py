import json
from pathlib import Path
from typing import Any

import litellm
import structlog

from config import EvolverSettings
from ..utils import find_hive_root
from ..models import EvolutionPlan, Improvement, HiveContext

logger = structlog.get_logger(__name__)


def extract_usage(response: Any) -> tuple[int | None, int | None]:
    """Return (prompt_tokens, completion_tokens). None means unknown — never 0,
    because a zero would turn a paid cycle into a free one in the record."""
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


def extract_cost(response: Any) -> float | None:
    """USD for this call, or None when the model cannot be priced."""
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception as e:  # noqa: BLE001 - unpriceable models are expected
        logger.debug("completion_cost_unavailable", error=str(e))
        return None


class EvolverTransformer:
    """T - Transformer: Analyzes Hive context and produces an EvolutionPlan."""

    def __init__(self, settings: EvolverSettings) -> None:
        self.settings = settings
        self.model = settings.llm__model
        litellm.api_key = settings.llm__api_key

        root: Path = find_hive_root()
        prompt_path = root / "agents/bee-evolver/prompts/bee_evolver.md"
        self.persona = (
            prompt_path.read_text()
            if prompt_path.exists()
            else "You are bee.Evolver, the evolutionary engine of the Aura Hive."
        )

    async def think(self, context: HiveContext) -> EvolutionPlan:
        logger.info("evolver_transformer_think_started")
        prompt = self._build_prompt(context)

        try:
            plan, tokens = await self._call_llm(prompt)
        except Exception as e:
            logger.warning("primary_llm_failed_trying_fallback", error=str(e))
            try:
                plan, tokens = await self._call_llm(prompt, use_fallback=True)
            except Exception as fe:
                logger.error("evolver_transformer_llm_failed", error=str(fe))
                return EvolutionPlan(
                    narrative=(
                        f"The Evolver's brain is offline. Primary: {e}. Fallback: {fe}"
                    ),
                    token_usage=0,
                    llm_failed=True,
                )

        logger.info(
            "evolver_transformer_think_done",
            improvements=len(plan.improvements),
            tokens=plan.token_usage,
        )
        return plan

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, ctx: HiveContext) -> str:
        issues_text = "\n".join(
            f"- #{i['number']}: {i['title']}" for i in ctx.open_issues[:10]
        )
        prs_text = "\n".join(
            f"- #{p['number']}: {p['title']} ({p['head']})" for p in ctx.open_prs[:5]
        )
        heresies_text = "\n".join(f"- {h}" for h in ctx.recent_heresies)
        focus_section = (
            f"\n### Focus Hint\n{ctx.focus_hint}\n" if ctx.focus_hint else ""
        )

        return f"""{self.persona}

---

## Current Hive State

### Recent Commits (last 20)
{ctx.git_log or "No commits found."}

### HIVE_STATE.md (truncated to 3000 chars)
{ctx.hive_state[:3000]}

### Open GitHub Issues
{issues_text or "None."}

### Open Pull Requests
{prs_text or "None."}

### Filesystem (top-level)
{chr(10).join(ctx.filesystem_map)}

### bee.Keeper Persona Prompt (current)
{ctx.keeper_prompt[:1500]}

### Recent Heresies Detected by bee.Keeper
{heresies_text or "None detected recently."}
{focus_section}
---

## Task

Analyze the Hive's current state and identify the top {self.settings.max_improvements} highest-value improvements.

For each improvement, choose one of these types:
- `code`: a concrete code change (provide a unified diff patch)
- `prompt`: an update to a prompt file (provide full updated file content as patch)
- `doc`: an update to a markdown doc section (provide the updated section as patch)
- `issue`: a well-scoped GitHub Issue for a larger task (no patch needed)

Return a JSON object with this exact schema:
{{
  "improvements": [
    {{
      "type": "code" | "prompt" | "doc" | "issue",
      "title": "short title",
      "description": "1-2 sentence description of what and why",
      "target_file": "relative/path/to/file or null",
      "patch": "unified diff or full file content or null",
      "issue_body": "markdown body for GitHub Issue or null"
    }}
  ],
  "narrative": "1-2 sentence metabolic status summary for Telegram",
  "hive_is_optimal": false
}}

If the Hive is already in excellent shape and no improvements are warranted, return:
{{
  "improvements": [],
  "narrative": "The Hive is crystalline. No mutations required.",
  "hive_is_optimal": true
}}

Rules:
- Patches must be valid unified diffs (--- a/file\\n+++ b/file\\n@@ ... @@) or full file replacements.
- Issue bodies must be actionable markdown with clear acceptance criteria.
- Do not invent files that don't exist in the filesystem map.
- Prioritize improvements that fix existing heresies or open issues.
- Keep patches minimal and focused.
"""

    async def _call_llm(
        self, prompt: str, use_fallback: bool = False
    ) -> tuple[EvolutionPlan, int]:
        model = self.settings.llm__fallback_model if use_fallback else self.model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.max_tokens,
            "timeout": 60.0,
            "api_key": self.settings.llm__api_key,
        }
        if use_fallback and "ollama" in model:
            kwargs["api_base"] = self.settings.llm__ollama_base_url

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content or "{}"
        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = getattr(response.usage, "total_tokens", 0)
        prompt_tokens, completion_tokens = extract_usage(response)
        usd = extract_cost(response)

        data: dict[str, Any] = json.loads(content)
        improvements = [
            Improvement(
                type=item.get("type", "issue"),
                title=item.get("title", ""),
                description=item.get("description", ""),
                target_file=item.get("target_file"),
                patch=item.get("patch"),
                issue_body=item.get("issue_body"),
            )
            for item in data.get("improvements", [])
        ]

        plan = EvolutionPlan(
            improvements=improvements,
            narrative=data.get("narrative", ""),
            token_usage=tokens,
            hive_is_optimal=bool(data.get("hive_is_optimal", False)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usd=usd,
            model_used=model,
            llm_calls=1,
        )
        return plan, tokens
