from pathlib import Path
from typing import Any

import litellm
import structlog
import yaml

from src.config import KeeperSettings
from src.dna import BeeContext, PurityReport

logger = structlog.get_logger(__name__)


class BeeTransformer:
    """T - Transformer: Analyzes purity and generates reports."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.model = settings.llm__model
        litellm.api_key = settings.llm__api_key

        prompt_path = Path("prompts/bee_keeper.md")
        self.persona = (
            prompt_path.read_text()
            if prompt_path.exists()
            else "You are bee.Keeper, guardian of the Aura Hive."
        )

        # Load manifest
        manifest_path = Path("hive-manifest.yaml")
        if manifest_path.exists():
            with open(manifest_path) as f:
                self.manifest = yaml.safe_load(f)
        else:
            self.manifest = {}

    async def think(self, context: BeeContext) -> PurityReport:
        logger.info("bee_transformer_think_started")

        # 1. Structural Check (Deterministic)
        heresies = self._deterministic_audit(context)

        # 2. LLM Audit (Reflective)
        purity_analysis = await self._llm_audit(context)

        all_heresies = heresies + purity_analysis.get("heresies", [])
        is_pure = len(all_heresies) == 0

        return PurityReport(
            is_pure=is_pure,
            heresies=all_heresies,
            narrative=purity_analysis.get("narrative", "The Hive remains silent."),
            reasoning=purity_analysis.get("reasoning", ""),
            metadata={"llm_response": purity_analysis}
        )

    def _deterministic_audit(self, context: BeeContext) -> list[str]:
        heresies = []
        core_path = self.manifest.get("hive", {}).get("core_path", "core-service/src/hive")
        allowed_files = self.manifest.get("hive", {}).get("allowed_files", [])

        # 1. Structural Check
        for file_path in context.filesystem_map:
            p = Path(file_path)
            if str(p.parent) == core_path:
                if allowed_files and p.name not in allowed_files:
                    heresies.append(
                        f"Structural Heresy: '{p.name}' is an unauthorized growth in the core nucleotides."
                    )

        # 2. Pattern Enforcement (No raw print or os.getenv in diff)
        diff_lines = context.git_diff.splitlines()
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                added_code = line[1:].strip()
                if "print(" in added_code and "logger" not in added_code:
                    heresies.append(
                        f"Pattern Heresy: Raw 'print()' detected in diff: `{added_code}`. Use `structlog` instead."
                    )
                if "os.getenv(" in added_code and "settings" not in added_code:
                    heresies.append(
                        f"Pattern Heresy: Raw 'os.getenv()' detected in diff: `{added_code}`. Use `settings` instead."
                    )

        return heresies

    async def _llm_audit(self, context: BeeContext) -> dict[str, Any]:
        prompt = f"""
        {self.persona}

        ### Sacred Architecture Manifest
        {yaml.dump(self.manifest)}

        ### Current Hive Signals
        **Git Diff:**
        {context.git_diff}

        **Filesystem Map:**
        {context.filesystem_map}

        **Hive Metrics:**
        {context.hive_metrics}

        ### Task
        Analyze the changes for any violations of the ATCG (Aggregator, Transformer, Connector, Generator) pattern or architectural impurities.

        Return a JSON object with:
        - "is_pure": boolean
        - "heresies": list of strings (empty if pure)
        - "narrative": a short narrative paragraph in the "Gardener & Hive" metaphor about the audit.
        - "reasoning": explanation of your findings.
        """

        try:
            return await self._call_llm(prompt)
        except Exception as e:
            logger.warning("primary_llm_failed_trying_fallback", error=str(e))
            try:
                return await self._call_llm(prompt, use_fallback=True)
            except Exception as fe:
                logger.error("llm_audit_failed_completely", error=str(fe))
                return {
                    "is_pure": False,
                    "heresies": [f"Blight: The Keeper's mind is clouded ({str(fe)})"],
                    "narrative": "A strange mist descends upon the Hive...",
                    "reasoning": f"Primary error: {e}. Fallback error: {fe}",
                }

    async def _call_llm(self, prompt: str, use_fallback: bool = False) -> dict[str, Any]:
        model = self.settings.llm__fallback_model if use_fallback else self.model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }

        if use_fallback and "ollama" in model:
            kwargs["api_base"] = self.settings.llm__ollama_base_url

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content
        import json

        data: dict[str, Any] = json.loads(content)
        return data
