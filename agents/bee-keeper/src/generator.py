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

        # 2. Append to CHRONICLES.md
        await self._update_chronicles(report)

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

    async def _update_chronicles(self, report: PurityReport) -> None:
        chronicles_path = Path("../../CHRONICLES.md")

        # Create if not exists
        if not chronicles_path.exists():
            chronicles_path.write_text("# Aura Hive Chronicles\n\n")

        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"## Audit: {now}\n\n"
        entry += f"> {report.narrative}\n\n"
        if report.heresies:
            entry += "**Findings:** Impurities detected.\n"
            for h in report.heresies:
                entry += f"- {h}\n"
        else:
            entry += "**Findings:** Architectural purity maintained.\n"
        entry += "\n---\n\n"

        try:
            with open(chronicles_path, "a") as f:
                f.write(entry)
            logger.info("chronicles_updated")
        except Exception as e:
            logger.error("chronicles_update_failed", error=str(e))
