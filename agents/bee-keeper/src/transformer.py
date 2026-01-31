from pathlib import Path
from typing import Any

import re
import litellm
import structlog
import yaml  # type: ignore

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
        heresies, audit_metadata = self._deterministic_audit(context)

        # 2. LLM Audit (Reflective)
        # Handle large diffs
        if len(context.git_diff) > 4000:
            logger.info("large_diff_detected_summarizing_first")
            summary = await self._summarize_diff(context.git_diff)
            context.git_diff = f"SUMMARY OF CHANGES:\n{summary}"

        purity_analysis = await self._llm_audit(context)

        all_heresies = heresies + purity_analysis.get("heresies", [])
        is_pure = len(all_heresies) == 0

        # Aggregate total heresies for density calculation
        total_heresies = audit_metadata.get("total_heresy_count", 0) + len(
            purity_analysis.get("heresies", [])
        )

        return PurityReport(
            is_pure=is_pure,
            heresies=all_heresies,
            narrative=purity_analysis.get("narrative", "The Hive remains silent."),
            reasoning=purity_analysis.get("reasoning", ""),
            token_usage=purity_analysis.get("token_usage", 0),
            metadata={
                "llm_response": purity_analysis,
                "total_heresies": total_heresies,
                "audit_metadata": audit_metadata,
            },
        )

    def _get_allowed_proteins(self) -> set[str]:
        """Dynamically determine allowed files based on Aura DNA."""
        proteins = {
            "types.py",
            "README.md",
            "metaphor.md",
            "__init__.py",
            "dna.py",
            "metabolism.py",
            "membrane.py",
        }

        # Add names from manifest if any
        manifest_allowed = self.manifest.get("hive", {}).get("allowed_files", [])
        proteins.update(manifest_allowed)

        dna_path_str = self.manifest.get("hive", {}).get("dna_path", "core-service/src/hive/dna.py")
        dna_path = Path("../../") / dna_path_str

        if dna_path.exists():
            for file_to_parse in [dna_path, dna_path.parent / "types.py"]:
                if file_to_parse.exists():
                    content = file_to_parse.read_text()
                    names = re.findall(r"class\s+([A-Za-z0-9_]+)", content)
                    for name in names:
                        proteins.add(f"{name.lower()}.py")

        return proteins

    def _deterministic_audit(self, context: BeeContext) -> tuple[list[str], dict[str, Any]]:
        heresy_groups: dict[str, list[str]] = {
            "structural": [],
            "print": [],
            "os.getenv": [],
        }
        pattern_files: dict[str, set[str]] = {"print": set(), "os.getenv": set()}
        structural_files: set[str] = set()

        core_path = self.manifest.get("hive", {}).get("core_path", "core-service/src/hive")
        core_path_obj = Path(core_path)
        allowed_proteins = self._get_allowed_proteins()

        # 1. Structural Check
        for file_path in context.filesystem_map:
            p = Path(file_path)
            try:
                # Ensure we only check files actually within the core hive path or its subdirectories
                p.relative_to(core_path_obj)
                if p.name not in allowed_proteins:
                    heresy_groups["structural"].append(
                        f"Structural Heresy: '{p.name}' is a foreign sprout needing pruning in the core nucleotides."
                    )
                    structural_files.add(str(p.parent))
            except ValueError:
                continue

        # 2. Pattern Enforcement
        diff_lines = context.git_diff.splitlines()
        current_file = "unknown"
        for line in diff_lines:
            if line.startswith("+++ b/"):
                current_file = line[6:]
            if line.startswith("+") and not line.startswith("+++"):
                added_code = line[1:]
                # Defensive pattern check: ignore if it's a comment or part of a docstring on the same line
                is_comment = re.search(r"^\s*#", added_code)
                is_docstring = re.search(r"^\s*(\"\"\"|''')", added_code)

                if not is_comment and not is_docstring:
                    # Remove trailing comments for the check
                    code_to_check = re.sub(r"#.*", "", added_code)

                    if (
                        re.search(r"\bprint\(", code_to_check)
                        and "logger" not in added_code
                    ):
                        heresy_groups["print"].append(added_code.strip())
                        pattern_files["print"].add(current_file)
                    if (
                        re.search(r"\bos\.getenv\(", code_to_check)
                        and "settings" not in added_code
                    ):
                        heresy_groups["os.getenv"].append(added_code.strip())
                        pattern_files["os.getenv"].add(current_file)

        # Aggregate results
        final_heresies = []
        total_count = sum(len(v) for v in heresy_groups.values())

        # Structural
        count = len(heresy_groups["structural"])
        if count > 5:
            dirs_count = len(structural_files)
            final_heresies.append(
                f"🚨 **Structural Heresy:** Detected {count} foreign sprouts needing pruning across {dirs_count} core nucleotides. Please clean the Hive."
            )
        else:
            final_heresies.extend(heresy_groups["structural"])

        # Print
        count = len(heresy_groups["print"])
        if count > 5:
            files_count = len(pattern_files["print"])
            final_heresies.append(
                f"🚨 **Pattern Heresy:** Detected {count} instances of raw `print()` across {files_count} files. This clutters the Hive's blood. Please switch to `structlog`."
            )
        else:
            for code in heresy_groups["print"]:
                final_heresies.append(
                    f"Pattern Heresy: Raw 'print()' detected in diff: `{code}`. Use `structlog` instead."
                )

        # os.getenv
        count = len(heresy_groups["os.getenv"])
        if count > 5:
            files_count = len(pattern_files["os.getenv"])
            final_heresies.append(
                f"🚨 **Pattern Heresy:** Detected {count} instances of raw `os.getenv()` across {files_count} files. This clutters the Hive's blood. Please switch to `settings`."
            )
        else:
            for code in heresy_groups["os.getenv"]:
                final_heresies.append(
                    f"Pattern Heresy: Raw 'os.getenv()' detected in diff: `{code}`. Use `settings` instead."
                )

        return final_heresies, {"total_heresy_count": total_count}

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

    async def _summarize_diff(self, diff: str) -> str:
        prompt = f"""
        {self.persona}
        Summarize the key architectural changes in this Git diff.
        Focus on which nucleotides were touched and if any new logic was added outside the ATCG pattern.

        DIFF:
        {diff[:10000]}  # Truncate to avoid context overflow
        """
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            return str(response.choices[0].message.content)
        except Exception as e:
            logger.warning("diff_summarization_failed", error=str(e))
            return "Large diff (could not summarize)."

    async def _call_llm(self, prompt: str, use_fallback: bool = False) -> dict[str, Any]:
        model = self.settings.llm__fallback_model if use_fallback else self.model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.max_tokens,
        }

        if use_fallback and "ollama" in model:
            kwargs["api_base"] = self.settings.llm__ollama_base_url

        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content
        import json

        data: dict[str, Any] = json.loads(content)
        # Capture token usage if available
        if hasattr(response, "usage") and response.usage:
            data["token_usage"] = getattr(response.usage, "total_tokens", 0)

        return data
