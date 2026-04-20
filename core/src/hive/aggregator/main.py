from collections.abc import Callable
from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    Aggregator,
    SkillRegistry,
    make_struct,
    resolve_brain_path,
)
from aura_core_gen.aura.core.v1 import (
    AssetContextData,
    Context,
    ContextType,
    HiveContextData,
    NegotiationOffer,
    Signal,
    Status,
    SystemVitals,
)

logger = structlog.get_logger(__name__)


def _get_metadata_dict(obj: Any) -> dict[str, Any]:
    meta = getattr(obj, "metadata", {})
    if hasattr(meta, "to_dict"):
        return cast(dict[str, Any], meta.to_dict())
    return meta if isinstance(meta, dict) else {}


class HiveAggregator(Aggregator[Any, Context]):
    """A - Aggregator: Consolidates persistence and telemetry signals."""

    def _update_metadata(self, obj: Any, updates: dict[str, Any]) -> None:
        meta = _get_metadata_dict(obj)
        meta.update(updates)
        obj.metadata = make_struct(meta)

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
        self.brain_path = resolve_brain_path(compiled_path or "")

        # Signal Enzymes: Dispatching based on Signal payload oneof
        self._SIGNAL_ENZYMES: dict[str, Callable[[Any, Signal, Context], Any]] = {
            "negotiation": self._perceive_negotiation,
            "perception": self._perceive_perception,
            "telegram": self._perceive_telegram,
            "asset": self._perceive_asset,
            "search": self._perceive_search,
        }

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics) via Telemetry Protein."""
        from datetime import UTC, datetime

        try:
            # Call Telemetry Protein via SkillRegistry
            obs = await self.registry.execute("telemetry", "fetch_metrics", {})
            if obs.success:
                return cast(
                    SystemVitals, SystemVitals().from_dict(_get_metadata_dict(obs))
                )
            return SystemVitals(status="unstable", timestamp=datetime.now(UTC))
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))
            return SystemVitals(status="error", timestamp=datetime.now(UTC))

    def _map_vitals_to_status(self, vitals: SystemVitals) -> Status:
        status_str = (vitals.status or "").lower()
        if status_str == "ok":
            return cast(Status, Status.STATUS_OK)
        if status_str in ["degraded", "unstable"]:
            return cast(Status, Status.STATUS_DEGRADED)
        if status_str == "error":
            return cast(Status, Status.STATUS_ERROR)
        if status_str == "critical":
            return cast(Status, Status.STATUS_CRITICAL)
        return cast(Status, Status.STATUS_UNSPECIFIED)

    async def perceive(self, signal: Any, **kwargs: Any) -> Context:
        """
        Perceive signal and turn it into Context.
        Transitioning from primitive reflex arcs (if/else) to complex enzymatic cascades.
        """
        # 1. Internal Proprioception (Moved from MetabolicLoop to Aggregator)
        vitals = await self.get_vitals()
        system_status = self._map_vitals_to_status(vitals)

        # 2. Initialize Base Context
        context = Context(
            system_health=system_status,
            metadata=make_struct(
                {
                    "brain_path": self.brain_path,
                    "vitals": vitals.to_dict(),
                }
            ),
        )

        # 3. Extract or Parse Signal
        proto_signal: Signal | None = None
        # UHM Coherence Check
        try:
            coherence_obs = await self.registry.execute(
                "coherence", "get_vitals", {"signal_strength": 1.0}
            )
            if coherence_obs.success:
                coh_vitals: dict[str, Any]  = cast(dict[str, Any], coherence_obs.metadata.to_dict().get("vitals", {}) )
                self._update_metadata(context, {"coherence_purity": str(coh_vitals.get("purity", 0))})
                if coh_vitals.get("status") == "ZOMBIE":
                    logger.warning("metabolic_zombie_detected", purity=coh_vitals.get("purity"))
        except Exception as e:
            logger.error("coherence_check_failed", error=str(e))

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
            and isinstance(signal.signal, Signal)
        ):
            # It's a NegotiateRequest wrapping a Signal
            return await self.perceive(signal.signal, **kwargs)

        # 4. Enzymatic Dispatching
        if proto_signal:
            context.identifier = proto_signal.identifier
            context.trace = proto_signal.trace
            payload_name, payload_value = betterproto.which_one_of(
                proto_signal, "payload"
            )

            if payload_name in self._SIGNAL_ENZYMES:
                enzyme = self._SIGNAL_ENZYMES[payload_name]
                # Enzymatic Cascade: Returns a context with specific data populated
                context = await enzyme(payload_value, proto_signal, context)
            else:
                logger.warning("unsupported_signal_payload", payload=payload_name)
        else:
            # Fallback for legacy objects (if any)
            context.identifier = str(
                getattr(signal, "item_id", getattr(signal, "identifier", "unknown"))
            )
            if hasattr(signal, "bid_amount"):
                context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_HIVE)
                context.hive = HiveContextData(
                    item_identifier=context.identifier,
                    offer=NegotiationOffer(
                        bid_amount=float(getattr(signal, "bid_amount", 0.0)),
                        reputation=float(getattr(signal.agent, "reputation_score", 1.0))
                        if hasattr(signal, "agent")
                        else 1.0,
                        agent_did=str(getattr(signal.agent, "did", "unknown"))
                        if hasattr(signal, "agent")
                        else "unknown",
                    ),
                    request_id=str(getattr(signal, "request_id", "")),
                )

        # 5. Post-Perception: Enrichment from Persistence if needed
        if context.context_type == ContextType.CONTEXT_TYPE_HIVE and context.hive:
            if not _get_metadata_dict(context).get("item_name"):
                await self._enrich_context_from_persistence(context)

        return context

    async def _perceive_negotiation(
        self, payload: Any, signal: Signal, context: Context
    ) -> Context:
        """Enzyme for Negotiation signals. Now supports Hybrid Signal v0.3.1 (Photos)."""
        # If hybrid signal contains image data, trigger visual perception reflex
        item_data: dict[str, Any] = {}
        vision_error = None

        if hasattr(payload, "image_data") and payload.image_data:
            # 1. Perception
            obs = await self.registry.execute(
                "perception",
                "perceive_image",
                {"image_bytes": payload.image_data},
            )

            if not obs.success:
                vision_error = getattr(obs, "error", "Perception failed")

            if not vision_error:
                # 2. Validation
                item_data = _get_metadata_dict(obs)
                v_obs = await self.registry.execute(
                    "guard",
                    "validate_vision",
                    {"vision_result": item_data},
                )

                if not v_obs.success:
                    vision_error = getattr(v_obs, "error", "Validation failed")

            if not vision_error:
                # 3. Success path: Cache ephemeral asset
                agent_did = payload.agent.did if payload.agent else "unknown"
                ttl = 3600
                if self.settings and hasattr(self.settings, "perception"):
                    ttl = int(
                        getattr(self.settings.perception, "ephemeral_asset_ttl", 3600)
                    )

                await self.registry.execute(
                    "persistence",
                    "set_cache",
                    {
                        "key": f"ephemeral:asset:{agent_did}",
                        "value": item_data,
                        "expire": ttl,
                    },
                )

        context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_HIVE)

        # Use perceived item_id if it's a vision discovery
        item_id = payload.item_identifier
        if (not item_id or item_id == "unknown") and item_data.get("id"):
            item_id = str(item_data.get("id"))

        context.hive = HiveContextData(
            item_identifier=item_id or "unknown",
            item_domain=payload.item_domain,
            offer=NegotiationOffer(
                bid_amount=payload.bid_amount,
                reputation=payload.agent.reputation_score if payload.agent else 1.0,
                agent_did=payload.agent.did if payload.agent else "unknown",
            ),
            request_id=signal.identifier,
        )

        metadata_updates = {"source": "negotiation"}
        if item_data:
            metadata_updates.update(
                {
                    "source": "vision",  # Upgrade source to vision for hybrid signals
                    "vision_error": str(vision_error or ""),
                    "item_name": str(item_data.get("name", "")),
                }
            )

        self._update_metadata(context, metadata_updates)
        return context

    async def _perceive_perception(
        self, payload: Any, signal: Signal, context: Context
    ) -> Context:
        """Enzyme for Vision Perception signals."""
        obs = await self.registry.execute(
            "perception",
            "perceive_image",
            {"image_bytes": payload.image_data},
        )

        item_data: dict[str, Any] = {}
        vision_error = None
        if obs.success:
            item_data = _get_metadata_dict(obs)
            v_obs = await self.registry.execute(
                "guard",
                "validate_vision",
                {"vision_result": item_data},
            )
            if v_obs.success:
                agent_did = payload.agent.did
                ttl = 3600
                if self.settings and hasattr(self.settings, "perception"):
                    ttl = int(
                        getattr(self.settings.perception, "ephemeral_asset_ttl", 3600)
                    )

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
                vision_error = getattr(v_obs, "error", "Validation failed")
        else:
            vision_error = getattr(obs, "error", "Perception failed")

        context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_HIVE)
        context.hive = HiveContextData(
            item_identifier=str(item_data.get("id", "perceived-vehicle")),
            offer=NegotiationOffer(
                bid_amount=0.0,
                reputation=payload.agent.reputation_score if payload.agent else 1.0,
                agent_did=payload.agent.did if payload.agent else "unknown",
            ),
            request_id=signal.identifier,
        )
        self._update_metadata(
            context,
            {
                "source": "vision",
                "vision_error": str(vision_error or ""),
                "item_name": str(item_data.get("name", "")),
            },
        )
        return context

    async def _perceive_telegram(
        self, payload: Any, signal: Signal, context: Context
    ) -> Context:
        """Enzyme for Telegram signals."""
        user_id = int(payload.user_id)
        callback_data = str(payload.callback_data)
        message_text = str(payload.message_text)
        agent_did = f"tg:{user_id}"

        item_id = str(_get_metadata_dict(signal).get("item_id", "unknown"))
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
        item_data: dict[str, Any] = {}
        if obs.success:
            item_data = _get_metadata_dict(obs)
            if item_id == "perceived-vehicle" or item_id == "unknown":
                item_id = str(item_data.get("id", item_id))

        # Store Telegram-specific info in metadata to avoid 'oneof' collision in Context
        self._update_metadata(
            context,
            {
                "source": "telegram",
                "chat_id": str(payload.chat_id),
                "user_id": str(user_id),
                "message_text": message_text,
                "callback_data": callback_data,
                "item_name": str(item_data.get("name", "")),
            },
        )

        context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_TELEGRAM)
        # For Telegram, we populate hive context for the Transformer/Reasoning loop
        context.hive = HiveContextData(
            item_identifier=item_id,
            offer=NegotiationOffer(
                bid_amount=bid_amount,
                reputation=1.0,
                agent_did=agent_did,
            ),
            request_id=signal.identifier,
        )
        return context

    async def _perceive_asset(
        self, payload: Any, signal: Signal, context: Context
    ) -> Context:
        """Enzyme for Generic Asset signals."""
        context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_ASSET)
        context.asset = AssetContextData(
            asset_identifier=payload.asset_identifier,
            asset_domain=payload.asset_domain,
        )
        self._update_metadata(
            context,
            {
                "source": "asset",
                "subtype": str(payload.signal_subtype),
            },
        )
        return context

    async def _perceive_search(
        self, payload: Any, signal: Signal, context: Context
    ) -> Context:
        """Enzyme for Search signals."""
        context.context_type = cast(ContextType, ContextType.CONTEXT_TYPE_ASSET)
        context.asset = AssetContextData(
            search_query=payload.query,
            asset_domain=payload.domain,
        )
        self._update_metadata(
            context,
            {
                "source": "search",
                "limit": str(payload.limit),
                "min_similarity": str(payload.min_similarity),
            },
        )
        return context

    async def _enrich_context_from_persistence(self, context: Context) -> None:
        """Helper to fetch additional item data if needed."""
        if not context.hive:
            return

        try:
            obs = await self.registry.execute(
                "persistence", "read_item", {"item_id": context.hive.item_identifier}
            )
            if obs.success:
                self._update_metadata(context, _get_metadata_dict(obs))
        except Exception as e:
            logger.error("aggregator_enrichment_failed", error=str(e))
