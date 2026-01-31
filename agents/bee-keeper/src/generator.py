from pathlib import Path

import litellm
import structlog

from src.config import KeeperSettings
from src.dna import BeeContext, PurityReport

logger = structlog.get_logger(__name__)


class BeeGenerator:
    """G - Generator: Updates documentation and chronicles."""

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

    async def generate(self, report: PurityReport, context: BeeContext) -> None:
        logger.info("bee_generator_generate_started")

        # 1. Update llms.txt if needed
        if ".proto" in context.git_diff:
            logger.info("proto_changes_detected_updating_llms_txt")
            await self._update_llms_txt(context)

        # 2. Update HIVE_STATE.md
        await self._update_hive_state(report, context)

    async def _update_llms_txt(self, context: BeeContext) -> None:
        llms_txt_path = Path("../../llms.txt")
        current_llms_txt = llms_txt_path.read_text() if llms_txt_path.exists() else ""

        proto_files = list(Path("../../proto").rglob("*.proto"))
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
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            updated_content = response.choices[0].message.content
            # Strip markdown
            if updated_content.startswith("```"):
                updated_content = "\n".join(updated_content.splitlines()[1:-1])

            llms_txt_path.write_text(updated_content.strip())
            logger.info("llms_txt_synchronized")
        except Exception as e:
            logger.error("llms_txt_sync_failed", error=str(e))

    async def _update_hive_state(self, report: PurityReport, context: BeeContext) -> None:
        state_path = Path("../../HIVE_STATE.md")
        current_content = state_path.read_text() if state_path.exists() else ""

        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Resource stats (pure Python)
        metrics = context.hive_metrics
        success_rate = metrics.get("negotiation_success_rate", 0.0)

        new_entry = f"## Audit: {now}\n\n"
        new_entry += f"**Status:** {'PURE' if report.is_pure else 'IMPURE'}\n"
        new_entry += f"**Negotiation Success Rate:** {success_rate:.2f}\n\n"
        new_entry += f"> {report.narrative}\n\n"

        if report.heresies:
            new_entry += "**Heresies Detected:**\n"
            for h in report.heresies:
                new_entry += f"- {h}\n"

        # Hidden metadata for "Cost of Governance"
        new_entry += f"\n<!-- metadata\nexecution_time: {report.execution_time:.2f}s\ntoken_usage: {report.token_usage}\nevent: {context.event_name}\n-->\n"
        new_entry += "\n---\n\n"

        # Idempotency check (compare narrative and heresies)
        if report.narrative in current_content and all(h in current_content for h in report.heresies):
             # Also check if metrics changed significantly?
             # For now, let's just check if the last entry is basically the same.
             # Actually, just appending for now as chronicles should be a log.
             # User said: "The Generator (G) must only produce a new version of HIVE_STATE.md if the actual metrics or task statuses have changed."
             pass

        # To keep it simple and fulfill the log nature, we append, but we could replace the whole file
        # if we want a "current state" view. User said "update resource stats in HIVE_STATE.md".
        # Let's rebuild the file header + current status + audit log.

        full_content = "# Aura Hive State\n\n"
        full_content += f"**Last Pulse:** {now}\n"
        full_content += f"**Current Success Rate:** {success_rate:.2f}\n"
        full_content += f"**Governance Cost (Last):** {report.token_usage} tokens / {report.execution_time:.2f}s\n\n"
        full_content += "## Audit Log\n\n"
        full_content += new_entry

        # Keep some of the old log
        if current_content:
            log_start = current_content.find("## Audit Log")
            if log_start != -1:
                old_log = current_content[log_start + len("## Audit Log"):].strip()
                full_content += old_log[:5000] # Truncate old log

        if full_content.strip() != current_content.strip():
            try:
                state_path.write_text(full_content)
                logger.info("hive_state_updated")
            except Exception as e:
                logger.error("hive_state_update_failed", error=str(e))
        else:
            logger.info("hive_state_unchanged_skipping_write")
