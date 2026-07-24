from typing import Any

import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation

from .engine import KineticEngine
from .schema import HeartbeatProps, VisionReportProps

logger = structlog.get_logger(__name__)


class KineticSkill(SkillProtocol[Any, KineticEngine, dict[str, Any], Observation]):
    """
    Kinetic Protein: Responsible for visual artifact synthesis.
    Turns metabolic signals into high-engagement videos for the Hive's Memory.
    """

    def __init__(self) -> None:
        self.settings: Any = None
        self.provider: KineticEngine | None = None
        self._capabilities = {
            "synthesize_vision_report": self._synthesize_vision_report,
            "render_heartbeat": self._render_heartbeat,
            "export_artifact": self._export_artifact,
        }

    def get_name(self) -> str:
        return "kinetic"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: Any, provider: KineticEngine) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return self.provider is not None

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error("kinetic_skill_execution_failed", error=str(e))
            return Observation(success=False, error=str(e))

    def _sanitize_id(self, identifier: Any) -> str:
        """Sanitizes an ID for use in filenames."""
        import re

        clean = re.sub(r"[^a-zA-Z0-9_\-]", "", str(identifier))
        return clean or "unknown"

    async def _synthesize_vision_report(self, params: dict[str, Any]) -> Observation:
        """Enzyme: Turns a VehicleProductData (passed as dict) into a video report."""
        if not self.provider:
            return Observation(success=False, error="provider_not_ready")

        make = params.get("make") or params.get("brand")
        identity = self.provider.synthesize_identity(make)
        asset_id = self._sanitize_id(params.get("id"))

        props = VisionReportProps(
            asset_id=asset_id,
            name=str(params.get("name", "Unknown Asset")),
            make=make,
            model=params.get("model"),
            year=params.get("year"),
            confidence_score=float(params.get("confidence_score", 0.0)),
            identity=identity,
        )

        output_filename = f"vision_{asset_id}.mp4"

        # Background synthesis: offload to maintain metabolic loop throughput
        async def _background_render() -> None:
            try:
                if self.provider:
                    await self.provider.render_video(
                        "VisionReport", props.model_dump(), output_filename
                    )
            except Exception as e:
                logger.error("vision_report_synthesis_failed", error=str(e))

        import asyncio

        asyncio.create_task(_background_render())

        return Observation(
            success=True,
            metadata=make_struct(
                {"status": "queued", "output_filename": output_filename}
            ),
        )

    async def _render_heartbeat(self, params: dict[str, Any]) -> Observation:
        """Enzyme: Turns NATS event stream vitals into an animation."""
        if not self.provider:
            return Observation(success=False, error="provider_not_ready")

        identity = self.provider.synthesize_identity("Default")

        props = HeartbeatProps(
            timestamp=params.get("timestamp", "now"),
            event_count=int(params.get("event_count", 0)),
            system_load=float(params.get("system_load", 0.0)),
            identity=identity,
        )

        # Background synthesis
        async def _background_render() -> None:
            try:
                if self.provider:
                    await self.provider.render_video(
                        "Heartbeat", props.model_dump(), "heartbeat.mp4"
                    )
            except Exception as e:
                logger.error("heartbeat_render_failed", error=str(e))

        import asyncio

        asyncio.create_task(_background_render())

        return Observation(
            success=True,
            metadata=make_struct({"status": "queued"}),
        )

    async def _export_artifact(self, params: dict[str, Any]) -> Observation:
        """Enzyme: Handles storage/upload of the artifact."""
        if not self.provider:
            return Observation(success=False, error="provider_not_ready")

        local_path = params.get("local_path")
        if not local_path:
            return Observation(success=False, error="local_path_required")

        result = await self.provider.export_artifact(local_path)
        return Observation(
            success=True,
            metadata=make_struct(result.model_dump()),
        )
