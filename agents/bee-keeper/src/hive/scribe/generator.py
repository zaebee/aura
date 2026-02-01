import litellm
import structlog

from src.config import KeeperSettings
from src.hive.dna import (
    ALLOWED_CHAMBERS,
    AuditObservation,
    BeeContext,
    BeeObservation,
    find_hive_root,
)

logger = structlog.get_logger(__name__)


class BeeGenerator:
    """G - Generator: Updates documentation and chronicles."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.model = settings.llm__model
        litellm.api_key = settings.llm__api_key
        root = find_hive_root()
        prompt_path = root / "agents/bee-keeper/prompts/bee_keeper.md"
        self.persona = (
            prompt_path.read_text()
            if prompt_path.exists()
            else "You are bee.Keeper, guardian of the Aura Hive."
        )

    async def generate(
        self,
        report: AuditObservation,
        context: BeeContext,
        observation: BeeObservation,
    ) -> None:
        logger.info("bee_generator_generate_started")

        # 1. Update llms.txt if needed
        if ".proto" in context.git_diff:
            logger.info("proto_changes_detected_updating_llms_txt")
            await self._update_llms_txt(context)

        # 2. Update HIVE_STATE.md
        await self._update_hive_state(report, context, observation)

    async def _update_llms_txt(self, context: BeeContext) -> None:
        root = find_hive_root()
        llms_txt_path = root / "llms.txt"
        current_llms_txt = llms_txt_path.read_text() if llms_txt_path.exists() else ""

        proto_files = list((root / "proto").rglob("*.proto"))
        proto_contents = ""
        for p in proto_files:
            proto_contents += f"\n--- {p} ---\n{p.read_text()}\n"

        prompt = f"""
        {self.persona}

        The internal DNA (Protobuf definitions) of the Aura Hive has changed.
        Update the `llms.txt` file to reflect these changes.

        --- Current llms.txt ---
        {current_llms_txt}

        --- Protobuf Definitions ---
        {proto_contents}

        Return the FULL updated content for `llms.txt`. Do not include any other text or markdown formatting markers.
        """

        try:
            response = await litellm.acompletion(
                model=self.model, messages=[{"role": "user", "content": prompt}]
            )
            updated_content = response.choices[0].message.content
            # Strip markdown
            if updated_content.startswith("```"):
                updated_content = "\n".join(updated_content.splitlines()[1:-1])

            llms_txt_path.write_text(updated_content.strip())
            logger.info("llms_txt_synchronized")
        except Exception as e:
            logger.error("llms_txt_sync_failed", error=str(e))

    async def _update_hive_state(
        self,
        report: AuditObservation,
        context: BeeContext,
        observation: BeeObservation,
    ) -> None:
        root = find_hive_root()
        state_path = root / "HIVE_STATE.md"
        current_content = state_path.read_text() if state_path.exists() else ""

        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Resource stats (pure Python)
        metrics = context.hive_metrics
        success_rate = metrics.get("negotiation_success_rate", 0.0)

        # Formatting Blight vs Heresy
        # If all LLMs failed, it's a Blight
        llm_unavailable = report.metadata.get("llm_unavailable", False)
        status_label = "PURE" if report.is_pure else "IMPURE"
        if llm_unavailable and not report.is_pure:
            status_label = "BLIGHTED"

        new_entry = f"## Audit: {now}\n\n"
        new_entry += f"**Status:** {status_label}\n"
        new_entry += f"**Negotiation Success Rate:** {success_rate:.2f}\n\n"
        new_entry += f"> {report.narrative}\n\n"

        if report.heresies:
            new_entry += "**Heresies Detected (Sacred Chambers):**\n"
            for h in report.heresies:
                # Map paths to roles if present in heresy string
                formatted_h = h
                for path, role in ALLOWED_CHAMBERS.items():
                    if path in h:
                        formatted_h = h.replace(path, f"{path} ({role})")
                new_entry += f"- {formatted_h}\n"

        # Chronicle reflective findings isolated from the Transformer's deterministic logic
        reflective_heresies = report.metadata.get("reflective_heresies", [])
        if reflective_heresies:
            new_entry += "\n**Reflective Insights (The Inquisitor's Eye):**\n"
            for rh in reflective_heresies:
                new_entry += f"- {rh}\n"

        if observation.injuries:
            new_entry += "\n**🤕 Injuries (Physical Blockages):**\n"
            for injury in observation.injuries:
                new_entry += f"- {injury}\n"

        # Hidden metadata for "Cost of Governance"
        new_entry += f"\n<!-- metadata\nexecution_time: {report.execution_time:.2f}s\ntoken_usage: {report.token_usage}\nevent: {context.event_name}\n-->\n"
        new_entry += "\n---\n\n"

        # To keep it simple and fulfill the log nature, we rebuild the file header + current status + audit log.
        full_content = "# Aura Hive State\n\n"
        full_content += f"**Last Pulse:** {now}\n"
        full_content += f"**Current Success Rate:** {success_rate:.2f}\n"
        full_content += (
            f"**Governance Cost (Last):** {report.token_usage} tokens / {report.execution_time:.2f}s\n\n"
        )
        full_content += "## Audit Log\n\n"
        full_content += new_entry

        # Keep some of the old log
        if current_content:
            log_start = current_content.find("## Audit Log")
            if log_start != -1:
                old_log = current_content[log_start + len("## Audit Log") :].strip()
                full_content += old_log[:5000]  # Truncate old log

        if full_content.strip() != current_content.strip():
            try:
                state_path.write_text(full_content)
                logger.info("hive_state_updated")
            except Exception as e:
                logger.error("hive_state_update_failed", error=str(e))
        else:
            logger.info("hive_state_unchanged_skipping_write")
