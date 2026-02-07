"""Telegram Connector Module.
Implements the Connector component for Telegram Metabolism.
"""

import structlog
from aura_core import (
    BaseConnector,
    SkillRegistry,
)
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramConnector(BaseConnector):
    """C - Connector: Executes UI actions and gRPC calls via Proteins."""

    def __init__(self, registry: SkillRegistry):
        super().__init__(registry)
