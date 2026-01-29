from typing import Any

import structlog
from hive.dna import HiveContext
from monitor import get_hive_metrics

from db import InventoryItem, SessionLocal

logger = structlog.get_logger(__name__)


class HiveAggregator:
    """A - Aggregator: Consolidates database and system health signals."""

    async def perceive(self, signal: Any) -> HiveContext:
        """
        Extract data from the inbound signal and enrich it with system state.

        Args:
            signal: The inbound gRPC request.
        """
        item_id = signal.item_id
        bid_amount = signal.bid_amount
        agent_did = signal.agent.did
        reputation = signal.agent.reputation_score
        request_id = getattr(signal, "request_id", "")

        logger.debug(
            "aggregator_perceive_started", item_id=item_id, request_id=request_id
        )

        # 1. Fetch item data from database
        item_data = {}
        session = SessionLocal()
        try:
            item = session.query(InventoryItem).filter_by(id=item_id).first()
            if item:
                item_data = {
                    "name": item.name,
                    "base_price": item.base_price,
                    "floor_price": item.floor_price,
                    "meta": item.meta or {},
                }
            else:
                logger.warning("item_not_found", item_id=item_id)
        except Exception as e:
            logger.error("aggregator_db_error", error=str(e))
        finally:
            session.close()

        # 2. Fetch system health metrics
        system_health = {}
        try:
            system_health = await get_hive_metrics()
        except Exception as e:
            logger.error("aggregator_metrics_error", error=str(e))

        return HiveContext(
            item_id=item_id,
            bid_amount=bid_amount,
            agent_did=agent_did,
            reputation=reputation,
            item_data=item_data,
            system_health=system_health,
            request_id=request_id,
        )
