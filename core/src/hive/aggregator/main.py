from typing import Any

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
from aura_core.gen.aura.dna.v1 import Signal

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
            if obs.success:
                return SystemVitals(**obs.data)
            return SystemVitals(status="unstable", timestamp="", error=obs.error)
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))
            return SystemVitals(status="error", timestamp="", error=str(e))

    async def get_system_metrics(self) -> dict[str, Any]:
        """Backward compatibility for legacy status calls."""
        vitals = await self.get_vitals()
        return dict(vitals.model_dump())

    async def perceive(self, signal: Any, **kwargs: Any) -> HiveContext:
        """
        Perceive signal and turn it into Context.
        Supports gRPC objects, binary Proto signals, and recursive Signal wrapping.
        """
        # 1. Initialize Default Context Components
        item_id = "unknown"
        request_id = ""
        offer = NegotiationOffer(bid_amount=0.0, reputation=1.0, agent_did="unknown")
        item_data: dict[str, Any] = {}
        metadata = {"brain_path": self.brain_path}

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
            and getattr(signal.signal, "signal_id", None)
        ):
            # It's a NegotiateRequest wrapping a Signal (Recursive normalization)
            return await self.perceive(signal.signal, **kwargs)

        # 3. Process Signal (Binary or Object-based)
        if proto_signal:
            try:
                request_id = proto_signal.signal_id
                payload_name, _ = betterproto.which_one_of(proto_signal, "payload")

                # Defensive check for empty payloads (Signal Integrity)
                if not payload_name:
                    logger.error("empty_signal_mutation", signal_id=request_id)
                    return HiveContext(
                        item_id=item_id,
                        offer=offer,
                        item_data=item_data,
                        system_health=await self.get_vitals(),
                        request_id=request_id,
                        metadata={**metadata, "error": "Empty Signal Mutation"},
                    )

                if payload_name == "negotiation":
                    neg_signal = proto_signal.negotiation
                    item_id = neg_signal.item_id
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
                    if obs.success:
                        item_data = obs.data
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
                        item_id=item_data.get("id", "perceived-vehicle"),
                        offer=NegotiationOffer(
                            bid_amount=0.0,
                            reputation=per_signal.agent.reputation_score,
                            agent_did=per_signal.agent.did,
                        ),
                        item_data=item_data,
                        system_health=await self.get_vitals(),
                        request_id=request_id,
                        metadata={
                            **metadata,
                            "source": "vision",
                            "vision_error": vision_error,
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
                    if obs.success and obs.data:
                        item_data = obs.data
                        if item_id == "perceived-vehicle" or item_id == "unknown":
                            item_id = item_data.get("id", item_id)

                    return HiveContext(
                        item_id=item_id,
                        offer=NegotiationOffer(
                            bid_amount=bid_amount,
                            reputation=1.0,
                            agent_did=agent_did,
                        ),
                        item_data=item_data,
                        system_health=await self.get_vitals(),
                        request_id=request_id,
                        metadata={
                            **metadata,
                            "source": "telegram",
                            "callback_data": callback_data,
                        },
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
        if not item_data:
            try:
                obs = await self.registry.execute(
                    "persistence", "read_item", {"item_id": item_id}
                )
                if obs.success and obs.data:
                    item = obs.data
                    item_data = {
                        "id": item["id"],
                        "name": item["name"],
                        "base_price": item["base_price"],
                        "floor_price": item["floor_price"],
                        "meta": item["meta"] or {},
                    }
            except Exception as e:
                logger.error("aggregator_persistence_error", error=str(e))

        return HiveContext(
            item_id=item_id,
            offer=offer,
            item_data=item_data,
            system_health=await self.get_vitals(),
            request_id=request_id,
            metadata=metadata,
        )
