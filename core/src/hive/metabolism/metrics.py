from prometheus_client import REGISTRY, Counter

# Negotiation Metrics
def _get_counter(name, documentation, labelnames):
    """Safely get or create a counter to avoid duplication errors during reloads."""
    # Use internal registry maps to find existing collector by name
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Counter(name, documentation, labelnames)

negotiation_total = _get_counter(
    "negotiation_total", "Total number of negotiations initiated", ["service"]
)

negotiation_accepted_total = _get_counter(
    "negotiation_accepted_total",
    "Total number of negotiations successfully accepted",
    ["service"],
)
