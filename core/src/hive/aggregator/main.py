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
        Supports both gRPC objects and binary Proto signals.
        """
        item_id = "unknown"
        request_id = ""
        offer = NegotiationOffer(bid_amount=0.0, reputation=1.0, agent_did="unknown")
        metadata = {"brain_path": self.brain_path}

        # 1. Decode Signal
        if isinstance(signal, bytes):
            try:
                proto_signal = Signal().parse(signal)
                request_id = proto_signal.signal_id
                payload_name, _ = betterproto.which_one_of(proto_signal, "payload")

                if payload_name == "negotiation":
                    neg_signal = proto_signal.negotiation
                    item_id = neg_signal.item_id
                    offer = NegotiationOffer(
                        bid_amount=neg_signal.bid_amount,
                        reputation=neg_signal.agent.reputation_score,
                        agent_did=neg_signal.agent.did,
                    )
                elif payload_name == "perception":
                    per_signal = proto_signal.perception
                    # Logic for Perception Signal (Vision Integration)
                    obs = await self.registry.execute(
                        "perception",
                        "perceive_image",
                        {"image_bytes": per_signal.image_data},
                    )

                    vision_error = None
                    vision_result = {}

                    if obs.success:
                        vision_result = obs.data
                        # The Membrane Law: Validate vision output
                        v_obs = await self.registry.execute(
                            "guard",
                            "validate_vision",
                            {"vision_result": vision_result},
                        )
                        if v_obs.success:
                            # LTP: Store perceived asset as Ephemeral Memory
                            agent_did = per_signal.agent.did
                            # Rely on single source of truth for configuration
                            ttl = 3600
                            if (
                                self.settings
                                and hasattr(self.settings, "perception")
                                and hasattr(self.settings.perception, "ephemeral_asset_ttl")
                            ):
                                ttl = self.settings.perception.ephemeral_asset_ttl

                            await self.registry.execute(
                                "persistence",
                                "set_cache",
                                {
                                    "key": f"ephemeral:asset:{agent_did}",
                                    "value": vision_result,
                                    "expire": ttl,
                                },
                            )
                        else:
                            vision_error = v_obs.error
                    else:
                        vision_error = obs.error

                    return HiveContext(
                        item_id=vision_result.get("id", "perceived-vehicle"),
                        offer=NegotiationOffer(
                            bid_amount=0.0,
                            reputation=per_signal.agent.reputation_score,
                            agent_did=per_signal.agent.did,
                        ),
                        item_data=vision_result,
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
                    # Logic for Telegram Signals (Callbacks from UI)
                    user_id = tel_signal.user_id
                    callback_data = tel_signal.callback_data
                    agent_did = f"tg:{user_id}"

                    item_id = "unknown"
                    bid_amount = 0.0
                    if callback_data.startswith("list_now:"):
                        try:
                            # Split into max 3 parts: list_now, item_id, price
                            parts = callback_data.split(":", 2)
                            if len(parts) >= 3:
                                item_id = parts[1]
                                bid_amount = float(parts[2])
                        except (ValueError, IndexError):
                            logger.warning("invalid_callback_data", data=callback_data)

                    # Fetch ephemeral asset from cache
                    item_data = {}
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
                logger.error("binary_signal_decode_failed", error=str(e))
                raise ValueError(f"Failed to decode binary signal: {e}") from e
        else:
            # Handle gRPC request object
            # Support wrapped Signal in NegotiateRequest
            if (
                hasattr(signal, "signal")
                and not isinstance(signal, Signal)
                and signal.signal
                and signal.signal.signal_id
            ):
                return await self.perceive(signal.signal, **kwargs)

            item_id = signal.item_id
            request_id = getattr(signal, "request_id", "")
            offer = NegotiationOffer(
                bid_amount=signal.bid_amount,
                reputation=signal.agent.reputation_score,
                agent_did=signal.agent.did,
            )

        # 2. Fetch standard item data if not already returned
        item_data = {}
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
