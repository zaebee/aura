import dspy


class GenerateTradeRisk(dspy.Signature):
    """
    Assess the risk of a proposed trade before committing to it.

    You are the Hive's risk cortex. Given market prices, system health, and
    current treasury balances, calculate the drawdown potential and assign a
    risk score.

    Rules:
    - risk_score is a float between 0.0 (no risk) and 1.0 (maximum risk).
    - If drawdown potential exceeds risk_threshold of treasury, risk_score MUST
      be greater than risk_threshold.
    - risk_category must be one of: LOW, MEDIUM, HIGH, CRITICAL.
      - LOW:      risk_score <= (risk_threshold / 2)
      - MEDIUM:   (risk_threshold / 2) < risk_score <= risk_threshold
      - HIGH:     risk_threshold < risk_score <= (risk_threshold * 3)
      - CRITICAL: risk_score > (risk_threshold * 3)
    - think must contain your step-by-step reasoning wrapped in <think>...</think> tags.
    """

    market_context: str = dspy.InputField(
        desc="JSON string with current prices, vision analysis results, and asset domain."
    )
    system_vitals: str = dspy.InputField(
        desc="JSON string with CPU usage, memory, network latency, and system status."
    )
    current_treasury: str = dspy.InputField(
        desc="JSON string with current token balances and available liquidity."
    )
    risk_threshold: str = dspy.InputField(
        desc="Maximum acceptable risk score as a plain float string (e.g. '0.10'). "
             "Trades with risk_score above this value must be rejected."
    )

    think: str = dspy.OutputField(
        desc="Step-by-step risk reasoning wrapped in <think>...</think> tags."
    )
    risk_score: str = dspy.OutputField(
        desc="Float 0.0–1.0 as a plain string (e.g. '0.07'). Lower is safer."
    )
    risk_category: str = dspy.OutputField(
        desc="One of: LOW, MEDIUM, HIGH, CRITICAL."
    )


class GenerateTradeIntent(dspy.Signature):
    """
    Generate a structured ERC-8004 TradeIntent decision.

    You are the Hive's trade execution cortex. Given market context, system
    health, treasury state, and a completed risk assessment, produce a
    strictly formatted JSON trade intent.

    Rules:
    - Output MUST be a single valid JSON object. No markdown fences, no prose.
    - Required fields: trade_id, asset_identifier, asset_domain, proposed_price,
      currency_code, reasoning.
    - If risk_assessment contains risk_score greater than risk_threshold OR
      risk_category is HIGH or CRITICAL, you MUST set proposed_price to 0.0
      and include the string "REJECTED_HIGH_RISK" in the reasoning field.
    - trade_id must be a UUID-style string (e.g. "trade-<timestamp>-<asset>").
    - currency_code must be "USDC" unless market_context specifies otherwise.
    - reasoning must summarise the key factors driving the decision.

    Example output (low-risk accept):
    {
      "trade_id": "trade-1700000000-VEHICLE",
      "asset_identifier": "asset-123",
      "asset_domain": "VEHICLE",
      "proposed_price": 250.0,
      "currency_code": "USDC",
      "reasoning": "Market price stable, treasury sufficient, risk LOW at 0.04."
    }

    Example output (high-risk reject):
    {
      "trade_id": "trade-1700000001-VEHICLE",
      "asset_identifier": "asset-123",
      "asset_domain": "VEHICLE",
      "proposed_price": 0.0,
      "currency_code": "USDC",
      "reasoning": "REJECTED_HIGH_RISK: drawdown potential exceeds threshold."
    }
    """

    market_context: str = dspy.InputField(
        desc="JSON string with current prices, vision analysis results, and asset domain."
    )
    system_vitals: str = dspy.InputField(
        desc="JSON string with CPU usage, memory, network latency, and system status."
    )
    current_treasury: str = dspy.InputField(
        desc="JSON string with current token balances and available liquidity."
    )
    risk_assessment: str = dspy.InputField(
        desc="JSON string with risk_score, risk_category, and think from GenerateTradeRisk."
    )
    risk_threshold: str = dspy.InputField(
        desc="Maximum acceptable risk score as a plain float string (e.g. '0.10'). "
             "Trades with risk_score above this value must be rejected."
    )

    trade_intent_json: str = dspy.OutputField(
        desc=(
            "A single valid JSON object with fields: trade_id, asset_identifier, "
            "asset_domain, proposed_price (float), currency_code, reasoning. "
            "No markdown, no extra text."
        )
    )
