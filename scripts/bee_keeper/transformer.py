import os
from pathlib import Path
from typing import Any

import litellm
import structlog
import yaml

from src.hive.dna import BeeContext, PurityReport

logger = structlog.get_logger(__name__)

class BeeTransformer:
    """T - Transformer: Analyzes purity and generates reports."""

    def __init__(self) -> None:
        self.model = os.getenv("BEE_KEEPER_MODEL", "gpt-4o")
        prompt_path = Path("src/prompts/bee_keeper.md")
        self.persona = prompt_path.read_text() if prompt_path.exists() else "You are bee.Keeper, guardian of the Aura Hive."

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

        if not allowed_files:
            return []

        for file_path in context.filesystem_map:
            p = Path(file_path)
            if str(p.parent) == core_path:
                if p.name not in allowed_files:
                    heresies.append(f"Structural Heresy: '{p.name}' is an unauthorized growth in the core nucleotides.")

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
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            import json

            data: dict[str, Any] = json.loads(content)
            return data
        except Exception as e:
            logger.error("llm_audit_failed", error=str(e))
            return {
                "is_pure": False,
                "heresies": [f"Blight: The Keeper's mind is clouded ({str(e)})"],
                "narrative": "A strange mist descends upon the Hive...",
                "reasoning": str(e)
            }
