import asyncio
import json
import os
from typing import Any

import structlog

from .schema import ExportResult, VisualIdentity

logger = structlog.get_logger(__name__)


class KineticEngine:
    """
    The Kinetic Engine: Acts as the Transcriptional Enzyme,
    converting metabolic data into cinematic artifacts via Remotion.
    """

    def __init__(self, remotion_project_path: str, output_dir: str) -> None:
        self.remotion_project_path = remotion_project_path
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def synthesize_identity(self, domain_signal: str | None) -> VisualIdentity:
        """Enzymatic mapping of domain signals to Visual Identity."""
        identities = {
            "Hyundai": VisualIdentity(
                primary_color="#003478", secondary_color="#A4A4A4", style="Modern"
            ),
            "Tesla": VisualIdentity(
                primary_color="#E81922", secondary_color="#FFFFFF", style="Minimal"
            ),
            "BMW": VisualIdentity(
                primary_color="#0066B3", secondary_color="#FFFFFF", style="Sport"
            ),
            "Property": VisualIdentity(
                primary_color="#2D5A27", secondary_color="#F5F5F5", style="Organic"
            ),
            "Workspace": VisualIdentity(
                primary_color="#6A0DAD", secondary_color="#E6E6FA", style="Corporate"
            ),
        }
        return identities.get(
            domain_signal or "Default",
            VisualIdentity(
                primary_color="#FFD700", secondary_color="#000000", style="Hive"
            ),
        )

    async def render_video(
        self, composition_id: str, props: dict[str, Any], output_filename: str
    ) -> str:
        """Executes the Remotion CLI to render a video artifact."""
        import tempfile

        # Sanitize output filename to prevent path traversal
        safe_filename = os.path.basename(output_filename)
        output_path = os.path.abspath(os.path.join(self.output_dir, safe_filename))

        # 1. Create temporary props file to avoid shell escaping issues
        props_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(props, f)
                props_path = f.name

            # 2. Construct the CLI command
            # Entry point is usually src/index.ts or src/index.tsx in a Remotion project
            # We use a relative path here because we set cwd=self.remotion_project_path in subprocess
            entry_point = "src/index.ts"
            if not os.path.exists(os.path.join(self.remotion_project_path, entry_point)):
                # Try .tsx
                entry_point += "x"

            cmd = [
                "npx",
                "remotion",
                "render",
                entry_point,
                composition_id,
                output_path,
                f"--props={props_path}",
                "--overwrite",
            ]

            logger.info(
                "kinetic_render_started",
                composition=composition_id,
                output=output_path,
            )

            # 3. Execute async subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.remotion_project_path,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_msg = stderr.decode(errors="replace")
                logger.error("kinetic_render_failed", error=err_msg)
                raise RuntimeError(f"Remotion render failed: {err_msg}")

            logger.info("kinetic_render_success", output=output_path)
            return output_path

        finally:
            # 4. Cleanup temporary props
            if props_path and os.path.exists(props_path):
                os.remove(props_path)

    async def export_artifact(self, local_path: str) -> ExportResult:
        """Handles the storage of the resulting MP4 in the Persistence layer."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Artifact not found at {local_path}")

        artifact_id = os.path.basename(local_path)
        size_bytes = os.path.getsize(local_path)

        # DESIGN NOTE: In production, this would upload to S3/GCS.
        # Here we simulate the persistence layer by returning a mock URL.
        # return ExportResult(
        #     artifact_id=artifact_id,
        #     url=f"https://artifacts.aura.hive/{artifact_id}",
        #     size_bytes=size_bytes
        # )

        # For the design/hackathon, we use file URI
        return ExportResult(
            artifact_id=artifact_id,
            url=f"file://{local_path}",
            size_bytes=size_bytes,
        )
