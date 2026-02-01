from prometheus_client import Counter

# Negotiation Metrics
negotiation_total = Counter(
    "negotiation_total",
    "Total number of negotiations initiated",
    ["service"]
)

negotiation_accepted_total = Counter(
    "negotiation_accepted_total",
    "Total number of negotiations successfully accepted",
    ["service"]
)
