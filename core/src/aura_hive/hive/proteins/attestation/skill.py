from typing import Any

import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.attestation import AttestationSettings

from .engine import AttestationEngine

logger = structlog.get_logger(__name__)


class AttestationSkill(
    SkillProtocol[AttestationSettings, Any, dict[str, Any], Observation]
):
    """
    Attestation Protein: signs decision receipts.

    One capability, one key. Extracted from the transaction protein, which had
    accreted this alongside payments — so attesting a decision required turning
    on crypto payment locks, and the Membrane called the payments protein to
    vouch for an audit record.
    """

    def __init__(self) -> None:
        self.settings: AttestationSettings | None = None
        self.provider: AttestationEngine | None = None
        self._capabilities = {"sign_receipt": self._sign_receipt}

    def get_name(self) -> str:
        return "attestation"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: AttestationSettings, provider: Any) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            # Reported, never raised. The decision this receipt describes has
            # already been made and is already safe; losing it because a key
            # was unreachable trades the guarantee for the attestation.
            logger.error("attestation_failed", error=str(e))
            return Observation(success=False, error=str(e))

    async def _sign_receipt(self, params: dict[str, Any]) -> Observation:
        payload = params.get("payload")
        if not payload:
            return Observation(success=False, error="payload_missing")

        if not self.provider:
            return Observation(success=False, error="attestation_key_not_configured")

        result = self.provider.sign(payload)
        return Observation(success=True, metadata=make_struct(result))
