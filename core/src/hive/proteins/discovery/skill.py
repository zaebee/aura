from typing import Any

import dspy
import structlog
from aura_core import SkillProtocol, get_raw_key, make_struct
from aura_core_gen.aura.core.v1 import DiscoveryObservation, Observation, XenoEntity
from github import Github

from config.discovery import DiscoverySettings

from .engine import (
    analyze_compatibility,
    generate_proposal,
    scan_github,
    sequence_genome,
)
from .schema import AnalysisParams, FirstContactParams, ScanParams, SequenceParams

logger = structlog.get_logger(__name__)


class DiscoverySkill(
    SkillProtocol[DiscoverySettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Discovery Protein: Scans GitHub, sequences genomes, and analyzes compatibility.
    Rhizomatic implementation: Maps connections without cloning.
    """

    def __init__(self) -> None:
        self.settings: DiscoverySettings | None = None
        self.provider: dict[str, Any] | None = None
        self.github_client: Github | None = None
        self._capabilities = {
            "scan_github": self._scan_github,
            "sequence_genome": self._sequence_genome,
            "analyze_compatibility": self._analyze_compatibility,
            "first_contact": self._first_contact,
        }

    def get_name(self) -> str:
        return "discovery"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: DiscoverySettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        if not self.settings or not self.provider:
            return False

        # Initialize GitHub Client
        token = get_raw_key(self.settings.github_token)
        self.github_client = Github(token) if token else Github()

        # Configure DSPy LM
        lm = self.provider.get("lm")
        if lm:
            dspy.configure(lm=lm)

        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Discovery skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _scan_github(self, params: dict[str, Any]) -> Observation:
        if not self.github_client or not self.settings:
            return Observation(success=False, error="discovery_not_ready")

        p = ScanParams(**params)
        results = await scan_github(
            p.query, self.github_client, limit=self.settings.scan_repo_limit
        )
        return Observation(
            success=True, metadata=make_struct({"repositories": results})
        )

    async def _sequence_genome(self, params: dict[str, Any]) -> Observation:
        if not self.github_client:
            return Observation(success=False, error="github_client_not_ready")

        p = SequenceParams(**params)
        context = await sequence_genome(p.repo_url, self.github_client)
        return Observation(
            success=True, metadata=make_struct({"repo_context": context})
        )

    async def _analyze_compatibility(self, params: dict[str, Any]) -> Observation:
        p = AnalysisParams(**params)
        analysis = await analyze_compatibility(p.repo_context)
        return Observation(success=True, metadata=make_struct(analysis))

    async def _first_contact(self, params: dict[str, Any]) -> Observation:
        """
        Full Loop: Scan -> Sequence -> Analyze -> Propose (Optional)
        Returns a DiscoveryObservation with XenoEntity objects.
        """
        if not self.github_client or not self.settings:
            return Observation(success=False, error="discovery_not_ready")

        p = FirstContactParams(**params)

        # 1. Scan
        repos = await scan_github(
            p.query, self.github_client, limit=self.settings.scan_repo_limit
        )

        entities = []
        contact_meta = []  # For backward compatibility in metadata if needed

        for r in repos:
            repo_url = r["url"]
            # 2. Sequence (Rhizomatic: scanning files, not cloning)
            context = await sequence_genome(repo_url, self.github_client)
            # 3. Analyze
            analysis = await analyze_compatibility(context)

            # 4. Create XenoEntity
            entity = XenoEntity(
                repo_url=repo_url,
                architecture_type=analysis.get("architecture_type", "Unknown"),
                detected_interfaces=analysis.get("detected_interfaces", []),
                compatibility_score=analysis.get("compatibility_score", 0.0),
            )
            entities.append(entity)

            # 5. Generate proposal if highly compatible
            proposal = ""
            if (
                analysis.get("compatibility_score", 0.0)
                > self.settings.proposal_compatibility_threshold
            ):
                proposal = await generate_proposal(context, analysis)

            contact_meta.append(
                {"repo": r["name"], "analysis": analysis, "proposal": proposal}
            )

        obs = Observation(
            success=True, metadata=make_struct({"contacts": contact_meta})
        )
        obs.discovery = DiscoveryObservation(entities=entities)
        return obs
