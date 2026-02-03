from prometheus_client import REGISTRY, Counter

# Negotiation Metrics
# Using a helper to avoid duplicated timeseries errors during structural migrations
def get_or_create_counter(name, documentation, labelnames):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Counter(name, documentation, labelnames)

negotiation_total = get_or_create_counter(
    "negotiation_total", "Total number of negotiations initiated", ["service"]
)

negotiation_accepted_total = get_or_create_counter(
    "negotiation_accepted_total",
    "Total number of negotiations successfully accepted",
    ["service"],
)
