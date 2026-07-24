"""Tissue-specificity enzymes: domain-specific attribute storage for assets.

Extracted from PersistenceSkill so the persistence enzyme stays about
persistence — session, deal and item lifecycle — and not about the shape of
vehicle/property/equipment/workspace tissues. PersistenceSkill dispatches into
``ASSET_ENZYMES`` by asset domain during upsert.
"""

from collections.abc import Callable

from aura_core_gen.aura.assets.v1 import Asset, AssetDomain

from .engine import InventoryItem


def store_vehicle_attributes(asset: Asset, item: InventoryItem) -> None:
    """Enzyme: specialized storage for Vehicle tissue."""
    if not asset.vehicle:
        return
    item.meta["vehicle_details"] = {
        "brand": str(getattr(asset.vehicle, "brand", "")),
        "model": str(getattr(asset.vehicle, "model", "")),
        "year": int(getattr(asset.vehicle, "year", 0)),
        "vin": str(getattr(asset.vehicle, "vin", "")),
        "color": str(getattr(asset.vehicle, "color", "")),
        "license_plate": str(getattr(asset.vehicle, "license_plate", "")),
    }


def store_property_attributes(asset: Asset, item: InventoryItem) -> None:
    """Enzyme: specialized storage for Property tissue."""
    if not asset.property:
        return
    item.meta["property_details"] = asset.property.to_dict()


def store_equipment_attributes(asset: Asset, item: InventoryItem) -> None:
    """Enzyme: specialized storage for Equipment tissue."""
    if not asset.equipment:
        return
    item.meta["equipment_details"] = asset.equipment.to_dict()


def store_workspace_attributes(asset: Asset, item: InventoryItem) -> None:
    """Enzyme: specialized storage for Workspace tissue."""
    if not asset.workspace:
        return
    item.meta["workspace_details"] = asset.workspace.to_dict()


# Domain-to-enzyme mapping for "tissue specificity".
ASSET_ENZYMES: dict[int, Callable[[Asset, InventoryItem], None]] = {
    int(AssetDomain.ASSET_DOMAIN_VEHICLE): store_vehicle_attributes,
    int(AssetDomain.ASSET_DOMAIN_PROPERTY): store_property_attributes,
    int(AssetDomain.ASSET_DOMAIN_EQUIPMENT): store_equipment_attributes,
    int(AssetDomain.ASSET_DOMAIN_WORKSPACE): store_workspace_attributes,
}
