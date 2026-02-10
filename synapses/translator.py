import json

from aura_core.gen.aura.dna.v1 import ItemData


def map_item_to_json_ld(item: ItemData) -> str:
    """
    OpenSchema Transformation: Maps internal ItemData to Schema.org JSON-LD (Product).
    """
    json_ld = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "identifier": item.identifier,
        "name": item.name,
        "description": item.description,
        "offers": {
            "@type": "Offer",
            "price": item.base_price,
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
        },
    }

    # Add any extra metadata from item.meta
    if item.meta:
        for key, value in item.meta.items():
            if key not in json_ld:
                json_ld[key] = value

    return json.dumps(json_ld, indent=2)


class TranslationEnzyme:
    """Standardized enzyme for internal-to-external schema translation."""

    def to_public_json_ld(self, item: ItemData) -> str:
        return map_item_to_json_ld(item)
