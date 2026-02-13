from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    Aggregator,
    HiveContext,
    NegotiationOffer,
    SkillRegistry,
    SystemVitals,
    resolve_brain_path,
)
from aura_core.gen.aura.assets import v1 as asset_pb2
from aura_core.gen.aura.core.v1 import (
    AssetContextData,
    ContextType,
    HiveContextData,
    Signal,
    Status,
)
from aura_core.gen.aura.core.v1.google import protobuf

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, HiveContext]):
    """A - Aggregator: Consolidates persistence and telemetry signals."""

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.settings = settings
        self.registry = registry
        compiled_path = None
        if (
            settings
            and hasattr(settings, "llm")
            and hasattr(settings.llm, "compiled_program_path")
        ):
            compiled_path = settings.llm.compiled_program_path
        self.brain_path = resolve_brain_path(compiled_path)

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics) via Telemetry Protein."""
        try:
            # Call Telemetry Protein via SkillRegistry
            obs = await self.registry.execute("telemetry", "fetch_metrics", {})
            if obs.success and obs.payload:
                return cast(SystemVitals, SystemVitals().parse(obs.payload.value))
            return SystemVitals(status="unstable")
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))
            return SystemVitals(status="error")

    async def get_system_metrics(self) -> dict[str, Any]:
        """Backward compatibility for legacy status calls."""
        vitals = await self.get_vitals()
        return vitals.to_dict()

    async def perceive(self, signal: Any, **kwargs: Any) -> HiveContext:
        """
        Perceive signal and turn it into Context.
        Supports gRPC objects, binary Proto signals, and recursive Signal wrapping.
        """
        # 1. Initialize Default Context Components
        item_id = "unknown"
        request_id = ""
        offer = NegotiationOffer(bid_amount=0.0, reputation=1.0, agent_did="unknown")
        metadata = {"brain_path": self.brain_path or ""}

        # Standardized Proprioception
        vitals = await self.get_vitals()

        # 2. Extract or Parse Signal
        proto_signal = None
        if isinstance(signal, bytes):
            try:
                proto_signal = Signal().parse(signal)
            except Exception as e:
                logger.error("binary_signal_decode_failed", error=str(e))
                raise ValueError(f"Failed to decode binary signal: {e}") from e
        elif isinstance(signal, Signal):
            proto_signal = signal
        elif (
            hasattr(signal, "signal")
            and signal.signal
            and (
                getattr(signal.signal, "identifier", None)
                or getattr(signal.signal, "signal_id", None)
            )
        ):
            # It's a NegotiateRequest wrapping a Signal (Recursive normalization)
            return await self.perceive(signal.signal, **kwargs)

        # 3. Process Signal (Binary or Object-based)
        if proto_signal:
            try:
                request_id = (
                    proto_signal.identifier or getattr(proto_signal, "signal_id", "")
                )
                payload_name, _ = betterproto.which_one_of(proto_signal, "payload")

                # Defensive check for empty payloads (Signal Integrity)
                if not payload_name:
                    logger.error("empty_signal_mutation", signal_id=request_id)
                    return HiveContext(
                        identifier=request_id,
                        context_type=cast(ContextType, ContextType.CONTEXT_TYPE_HIVE),
                        system_health=cast(Status, Status.STATUS_DEGRADED),
                        vitals=vitals,
                        hive=HiveContextData(
                            item_identifier=item_id,
                            offer=offer,
                            request_id=request_id,
                        ),
                        metadata={**metadata, "error": "Empty Signal Mutation"},
                    )

                if payload_name == "negotiation":
                    neg_signal = proto_signal.negotiation
                    item_id = neg_signal.item_identifier
                    offer = NegotiationOffer(
                        bid_amount=neg_signal.bid_amount,
                        reputation=neg_signal.agent.reputation_score,
                        agent_did=neg_signal.agent.did,
                    )
                    # Fall through to standard item data fetch

                elif payload_name == "perception":
                    per_signal = proto_signal.perception
                    obs = await self.registry.execute(
                        "perception",
                        "perceive_image",
                        {"image_bytes": per_signal.image_data},
                    )

                    vision_error = None
                    asset = None
                    if obs.success and obs.payload:
                        asset = asset_pb2.Asset().parse(obs.payload.value)

                        # Pack for guard validation (legacy expects dict for now)
                        item_data = {
                            "make": asset.vehicle.brand if asset.vehicle else "",
                            "model": asset.vehicle.model if asset.vehicle else "",
                            "year": asset.vehicle.year if asset.vehicle else 0,
                            "confidence_score": float(obs.metadata.get("confidence_score", 0.0))
                        }

                        v_obs = await self.registry.execute(
                            "guard",
                            "validate_vision",
                            {"vision_result": item_data},
                        )
                        if v_obs.success:
                            agent_did = per_signal.agent.did
                            ttl = 3600
                            if (
                                self.settings
                                and hasattr(self.settings, "perception")
                                and hasattr(
                                    self.settings.perception, "ephemeral_asset_ttl"
                                )
                            ):
                                ttl = self.settings.perception.ephemeral_asset_ttl

                            await self.registry.execute(
                                "persistence",
                                "set_cache",
                                {
                                    "key": f"ephemeral:asset:{agent_did}",
                                    "value": item_data,
                                    "expire": ttl,
                                },
                            )
                        else:
                            vision_error = v_obs.error
                    else:
                        vision_error = obs.error

                    return HiveContext(
                        identifier=request_id,
                        context_type=cast(ContextType, ContextType.CONTEXT_TYPE_HIVE),
                        system_health=cast(Status, Status.STATUS_OK),
                        vitals=vitals,
                        hive=HiveContextData(
                            item_identifier=asset.identifier if asset else "perceived-vehicle",
                            offer=NegotiationOffer(
                                bid_amount=0.0,
                                reputation=per_signal.agent.reputation_score,
                                agent_did=per_signal.agent.did,
                            ),
                            request_id=request_id,
                            asset_payload=cast(protobuf.Any, obs.payload) if obs.success else protobuf.Any(),
                        ),
                        metadata={
                            **metadata,
                            "source": "vision",
                            "vision_error": vision_error or "",
                        },
                    )

                elif payload_name == "telegram":
                    tel_signal = proto_signal.telegram
                    user_id = tel_signal.user_id
                    callback_data = tel_signal.callback_data
                    message_text = tel_signal.message_text
                    agent_did = f"tg:{user_id}"

                    item_id = proto_signal.metadata.get("item_id", "unknown")
                    bid_amount = 0.0

                    if callback_data:
                        if callback_data.startswith("list_now:"):
                            try:
                                parts = callback_data.split(":", 2)
                                if len(parts) >= 3:
                                    item_id = parts[1]
                                    bid_amount = float(parts[2])
                            except (ValueError, IndexError):
                                logger.warning("invalid_callback_data", data=callback_data)
                    elif message_text:
                        clean_text = message_text.strip().replace("$", "")
                        if clean_text.replace(".", "", 1).isdigit():
                            bid_amount = float(clean_text)

                    # Fetch ephemeral asset from cache
                    obs = await self.registry.execute(
                        "persistence",
                        "get_cache",
                        {"key": f"ephemeral:asset:{agent_did}"},
                    )
                    asset_payload = None
                    if obs.success and obs.payload:
                        asset = asset_pb2.Asset().parse(obs.payload.value)
                        asset_payload = obs.payload
                        if item_id == "perceived-vehicle" or item_id == "unknown":
                            item_id = asset.identifier

                    return HiveContext(
                        identifier=request_id,
                        context_type=cast(ContextType, ContextType.CONTEXT_TYPE_HIVE),
                        system_health=cast(Status, Status.STATUS_OK),
                        vitals=vitals,
                        hive=HiveContextData(
                            item_identifier=item_id,
                            offer=NegotiationOffer(
                                bid_amount=bid_amount,
                                reputation=1.0,
                                agent_did=agent_did,
                            ),
                            request_id=request_id,
                            asset_payload=cast(protobuf.Any, asset_payload) if asset_payload else protobuf.Any(),
                        ),
                        metadata={
                            **metadata,
                            "source": "telegram",
                            "callback_data": callback_data or "",
                        },
                    )

                elif payload_name == "search":
                    search_sig = proto_signal.search
                    return HiveContext(
                        identifier=request_id,
                        context_type=cast(ContextType, ContextType.CONTEXT_TYPE_ASSET),
                        system_health=cast(Status, Status.STATUS_OK),
                        vitals=vitals,
                        asset=AssetContextData(
                            search_query=search_sig.query,
                            asset_metadata={"agent_did": search_sig.agent.did}
                        ),
                        metadata={**metadata, "source": "search"},
                    )

                else:
                    raise ValueError(f"Unsupported payload: {payload_name}")

            except Exception as e:
                logger.error("signal_processing_failed", error=str(e))
                raise ValueError(f"Failed to process signal: {e}") from e
        else:
            # 4. Handle standard gRPC objects (Fallback)
            item_id = getattr(signal, "item_id", "unknown")
            request_id = getattr(signal, "request_id", "")
            if hasattr(signal, "agent") and signal.agent:
                offer = NegotiationOffer(
                    bid_amount=getattr(signal, "bid_amount", 0.0),
                    reputation=getattr(signal.agent, "reputation_score", 1.0),
                    agent_did=getattr(signal.agent, "did", "unknown"),
                )

        # 5. Fetch standard item data if not already returned or found in ephemeral cache
        asset_payload = None
        try:
            obs = await self.registry.execute(
                "persistence", "read_item", {"item_id": item_id}
            )
            if obs.success and obs.payload:
                asset_payload = obs.payload
                metadata.update(obs.metadata)
        except Exception as e:
            logger.error("aggregator_persistence_error", error=str(e))

        return HiveContext(
            identifier=request_id,
            context_type=cast(ContextType, ContextType.CONTEXT_TYPE_HIVE),
            system_health=cast(Status, Status.STATUS_OK),
            vitals=vitals,
            hive=HiveContextData(
                item_identifier=item_id,
                offer=offer,
                request_id=request_id,
                asset_payload=cast(protobuf.Any, asset_payload) if asset_payload else protobuf.Any(),
            ),
            metadata=metadata,
        )
