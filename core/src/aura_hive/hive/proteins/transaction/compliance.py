"""C2C9 compliance guard: KYC/AML enforcement for RWA collateral release.

Extracted from TransactionSkill so the transaction protein *delegates* the
Membrane decision instead of embedding it. Pure logic over the HiveContext
metadata; raises MetabolicSecurityError on a missing context or a compliance
violation, exactly as the inline check did.
"""

from typing import Any

import structlog

from aura_hive.hive.metabolism import MetabolicSecurityError

logger = structlog.get_logger(__name__)


def enforce_rwa_compliance(context: Any, required_kyc: str, required_aml: str) -> None:
    """C2C9 Membrane enforcement: raise unless KYC/AML clearance matches.

    Args:
        context: HiveContext carrying compliance metadata (google.protobuf.Struct).
        required_kyc: KYC status required to release collateral.
        required_aml: AML risk level required to release collateral.

    Raises:
        MetabolicSecurityError: if the context is missing or compliance fails.
    """
    if not context:
        raise MetabolicSecurityError("Security context missing: HiveContext required")

    # Extract metadata from Context (google.protobuf.Struct)
    metadata = (
        context.metadata.to_dict() if hasattr(context.metadata, "to_dict") else {}
    )
    kyc_status = metadata.get("kyc_status")
    aml_risk = metadata.get("aml_risk")

    if kyc_status != required_kyc or aml_risk != required_aml:
        logger.error(
            "c2c9_security_violation",
            kyc_status=kyc_status,
            aml_risk=aml_risk,
            agent_did=metadata.get("agent_did", "unknown"),
        )
        raise MetabolicSecurityError(
            f"C2C9 Membrane Violation: Compliance failure "
            f"(KYC: {kyc_status}, AML: {aml_risk})"
        )
