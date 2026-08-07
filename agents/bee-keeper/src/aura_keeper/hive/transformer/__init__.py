from pathlib import Path
from typing import Any, cast

import json
import litellm
import structlog
import yaml  # type: ignore

from aura_keeper.config import KeeperSettings
from aura_core import (
    ALLOWED_CHAMBERS,
    DETERMINISM_EXEMPT_PATHS,
    ALLOWED_ROOT_FILES,
    MACRO_ATCG_FOLDERS,
    Transformer,
    check_determinism,
    find_hive_root,
    make_struct,
)
from aura_core_gen.aura.core.v1 import (
    AuditObservation,
    Context,
)
import dspy
from .signatures import DiagnoseError

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


class BeeTransformer(Transformer[Context, AuditObservation]):
    """T - Transformer: Analyzes purity and generates audit observations."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.model = settings.llm__model
        litellm.api_key = settings.llm__api_key
        # Metabolism instrumentation (Gate 0). bee.Keeper makes more than one
        # LLM call per cycle, so usage is accumulated rather than overwritten.
        self.usage_totals: dict[str, Any] = {}
        self.reset_usage()

    def reset_usage(self) -> None:
        """Clear per-cycle usage. Called at the start of every cycle.

        main() runs a continuous loop, calling execute() once per NATS error
        event on this same long-lived instance. Without a reset the totals
        accumulate across cycles, so every record after the first reports the
        sum of all preceding cycles — silently and without bound.
        """
        self.usage_totals = {
            "llm_calls": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "usd": None,
            "model": None,
        }
        self.lm = dspy.LM(
            f"openai/{self.model}", api_key=self.settings.llm__api_key, cache=False
        )
        self._init_paths()

    def _accumulate_usage(self, response: Any, model: str) -> None:
        """Sum usage across every LLM call in a cycle.

        bee.Keeper makes more than one call per cycle (_summarize_diff and
        _call_llm); recording only one would undercount its baseline by
        construction. None + value keeps 'unknown' from silently becoming 0.
        """
        prompt, completion = extract_usage(response)
        usd = extract_cost(response)

        def _add(current: Any, addition: Any) -> Any:
            if addition is None:
                return current
            if current is None:
                return addition
            return current + addition

        self.usage_totals["llm_calls"] = int(self.usage_totals["llm_calls"]) + 1
        self.usage_totals["prompt_tokens"] = _add(
            self.usage_totals["prompt_tokens"], prompt
        )
        self.usage_totals["completion_tokens"] = _add(
            self.usage_totals["completion_tokens"], completion
        )
        self.usage_totals["usd"] = _add(self.usage_totals["usd"], usd)
        self.usage_totals["model"] = model

    def _init_paths(self) -> None:
        root = find_hive_root()

        prompt_path = root / "agents/bee-keeper/prompts/bee_keeper.md"
        self.persona = (
            prompt_path.read_text()
            if prompt_path.exists()
            else "You are bee.Keeper, guardian of the Aura Hive."
        )

        # Load manifest
        manifest_path = root / "agents/bee-keeper/hive-manifest.yaml"
        if manifest_path.exists():
            with open(manifest_path) as f:
                self.manifest = yaml.safe_load(f)
        else:
            self.manifest = {}

    async def think(self, context: Context, **kwargs: Any) -> AuditObservation:
        """Main entry point for BeeKeeper reasoning."""
        logger.info("bee_transformer_think_started")

        # 1. Gather context from metadata
        meta = context.metadata.to_dict()
        vitals = cast(dict[str, Any], meta.get("vitals", {}))
        logs = meta.get("recent_logs", "")
        error_log = context.bee.error_message
        source = context.bee.error_source

        system_context = (
            f"Source: {source}\nVitals: {json.dumps(vitals)}\nRecent Logs:\n{logs}"
        )

        # 2. Diagnose via DSPy
        diagnosis, fix, tokens = await self._diagnose(error_log, system_context)

        # 3. Structural check (still useful for success rate check etc)
        structural_findings = self._deterministic_audit(context)

        metadata = {
            "diagnosis": diagnosis,
            "fix_suggestion": fix,
            "structural_findings": structural_findings,
        }

        return AuditObservation(
            is_pure=len(structural_findings) == 0,
            heresies=structural_findings,
            narrative=diagnosis,
            reasoning=fix,
            token_usage=tokens,
            metadata=make_struct(metadata),
        )

    async def _diagnose(
        self, error_log: str, system_context: str
    ) -> tuple[str, str, int]:
        """Use DSPy to diagnose the error."""
        with dspy.context(lm=self.lm):
            predictor = dspy.Predict(DiagnoseError)
            try:
                result = predictor(error_log=error_log, system_context=system_context)
                # Attempt to get usage from dspy (if available in this version)
                tokens = 0
                if hasattr(self.lm, "history") and self.lm.history:
                    last_query = self.lm.history[-1]
                    if "response" in last_query and hasattr(
                        last_query["response"], "usage"
                    ):
                        tokens = last_query["response"].usage.total_tokens

                return result.diagnosis, result.fix_suggestion, tokens
            except Exception as e:
                logger.error("dspy_diagnosis_failed", error=str(e))
                return f"Diagnosis failed: {e}", "Manual intervention required.", 0

    def _deterministic_audit(self, context: Context) -> list[str]:
        heresies = []
        core_path = self.manifest.get("hive", {}).get("core_path", "core/src/hive")
        allowed_files = self.manifest.get("hive", {}).get("allowed_files", [])

        # 1. Macro-ATCG (Root) Check
        for item in context.bee.filesystem_map:
            p = Path(item)
            # Only check top-level items
            if p.parent == Path("."):
                name = p.name
                # Ignore hidden files and standard directories
                if name.startswith(".") or name in [
                    ".git",
                    ".github",
                    ".venv",
                    ".vscode",
                ]:
                    continue

                is_macro_folder = name in MACRO_ATCG_FOLDERS
                is_allowed_file = name in ALLOWED_ROOT_FILES

                if not (is_macro_folder or is_allowed_file):
                    heresies.append(
                        f"Root Heresy: '{name}' is a foreign sprout in the project root. Move it to a Nucleotide or the Tool-Shed."
                    )

        # 2. Structural Check (Core and Allowed Chambers)
        for file_path in context.bee.filesystem_map:
            p = Path(file_path)

            # Check core Hive nucleotides
            if str(p.parent) == core_path:
                if allowed_files and p.name not in allowed_files:
                    heresies.append(
                        f"Structural Heresy: '{p.name}' is an unauthorized growth in the core nucleotides."
                    )
                continue

            # Check allowed peripheral chambers (Sanctified Infrastructure)
            is_sanctified = False
            for chamber in ALLOWED_CHAMBERS:
                if str(p).startswith(chamber):
                    is_sanctified = True
                    break

            # If it's not in core, not a known chamber, and not a dotfile/metafile/rootfile, flag it
            if (
                not is_sanctified
                and not p.name.startswith(".")
                and len(p.parts) > 1
                and p.parts[0] not in MACRO_ATCG_FOLDERS
            ):
                heresies.append(
                    f"Unauthorized Growth: '{p}' has expanded outside sanctioned chambers. The Inquisitor demands its removal."
                )

        # 3. Metric Verification
        metrics = context.bee.hive_metrics
        success_rate = metrics.get("negotiation_success_rate", 1.0)

        if success_rate < 0.7:
            heresies.append(
                f"Hive Alert: 'negotiation_success_rate' is {success_rate:.2f}, which is below the critical threshold of 0.7. The Hive flow is obstructed."
            )

        # 4. Pattern Enforcement (No raw print or os.getenv in diff)
        diff_lines = context.bee.git_diff.splitlines()
        current_file = ""
        for line in diff_lines:
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue

            if line.startswith("+") and not line.startswith("+++"):
                added_code = line[1:].strip()
                # Ignore comments
                if (
                    added_code.startswith("#")
                    or added_code.startswith('"""')
                    or added_code.startswith("'''")
                ):
                    continue

                # Skip pattern check for the transformer itself to avoid false positives on rule definitions
                if "/transformer/" in current_file:
                    continue

                if "print(" in added_code and "logger" not in added_code:
                    heresies.append(
                        f"Pattern Heresy: Raw 'print()' detected in diff: `{added_code}`. Use `structlog` instead."
                    )
                if "os.getenv(" in added_code and "settings" not in added_code:
                    heresies.append(
                        f"Pattern Heresy: Raw 'os.getenv()' detected in diff: `{added_code}`. Use `settings` instead."
                    )

                # 5. Genomic Purity Check (No legacy imports)
                if "aura_core.types" in added_code:
                    heresies.append(
                        f"Genomic Heresy: Legacy import `aura_core.types` detected in diff: `{added_code}`. Use chromosomal DNA (`aura_core_gen.aura.*`) instead."
                    )

                # 6. Protocol Enforcement (Ensure classes in ATCG folders implement generic protocols)
                if "class " in added_code and ":" in added_code:
                    # Check if it's in an ATCG nucleotide
                    is_atcg_file = any(
                        n in current_file
                        for n in ["aggregator", "transformer", "connector", "generator"]
                    )
                    if is_atcg_file and "src/hive" in current_file:
                        # Ensure it implements the generic protocol (e.g., Aggregator[...) or SkillProtocol
                        has_protocol = any(
                            p in added_code
                            for p in [
                                "Aggregator[",
                                "Transformer[",
                                "Connector[",
                                "Generator[",
                                "SkillProtocol",
                            ]
                        )
                        if not has_protocol:
                            heresies.append(
                                f"Protocol Heresy: Class `{added_code}` in `{current_file}` does not implement a Generic ATCG Protocol or SkillProtocol. Architecture purity is compromised."
                            )

                # 7. determinism rule (non-determinism belongs to the Transformer alone)
                determinism_heresy = check_determinism(
                    current_file, added_code, DETERMINISM_EXEMPT_PATHS
                )
                if determinism_heresy:
                    heresies.append(determinism_heresy)

        return heresies

    async def _llm_audit(self, context: Context, git_diff: str) -> dict[str, Any]:
        prompt = f"""
        {self.persona}

        ### Sacred Architecture Manifest
        {yaml.dump(self.manifest)}

        ### Current Hive Signals
        **Git Diff:**
        {git_diff}

        **Filesystem Map:**
        {context.bee.filesystem_map}

        **Hive Metrics:**
        {context.bee.hive_metrics}

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
        except (
            litellm.exceptions.APIConnectionError,
            litellm.exceptions.ServiceUnavailableError,
            litellm.exceptions.Timeout,
            litellm.exceptions.AuthenticationError,
            json.JSONDecodeError,
        ) as e:
            logger.warning("primary_llm_failed_trying_fallback", error=str(e))
            try:
                return await self._call_llm(prompt, use_fallback=True)
            except Exception as fe:
                logger.error("llm_audit_failed_completely", error=str(fe))
                # Fallback to a "Safe" pure-ish response so structural audit can still pass
                return {
                    "is_pure": True,  # Assume pure if LLM is down, structural check still runs in think()
                    "heresies": [],
                    "narrative": "A thick mist covers the Hive. The Keeper senses only the physical structures, the deeper patterns remain hidden.",
                    "reasoning": f"LLM Connectivity failure. Primary: {e}. Fallback: {fe}",
                    "llm_unavailable": True,
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
            self._accumulate_usage(response, self.model)
            return str(response.choices[0].message.content)
        except Exception as e:
            logger.warning("diff_summarization_failed", error=str(e))
            return "Large diff (could not summarize)."

    async def _call_llm(
        self, prompt: str, use_fallback: bool = False
    ) -> dict[str, Any]:
        model = self.settings.llm__fallback_model if use_fallback else self.model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.max_tokens,
            "timeout": 30.0,  # Add timeout for resilience
        }

        if use_fallback and "ollama" in model:
            kwargs["api_base"] = self.settings.llm__ollama_base_url

        response = await litellm.acompletion(**kwargs)
        self._accumulate_usage(response, model)
        content = response.choices[0].message.content

        data: dict[str, Any] = json.loads(content)
        # Capture token usage if available
        if hasattr(response, "usage") and response.usage:
            data["token_usage"] = getattr(response.usage, "total_tokens", 0)

        return data
