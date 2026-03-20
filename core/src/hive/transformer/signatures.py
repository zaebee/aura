import dspy


class AppraiseAndVerifyRWA(dspy.Signature):
    """
    Appraise a physical Real-World Asset and verify KYC/AML compliance before
    issuing a stablecoin vault intent.

    You are the Hive's institutional compliance officer and asset appraiser.
    You must act as a strict Swiss Banker: compliance is checked first, appraisal
    second. No vault intent may be issued without passing both gates.

    Compliance rules (checked in order, first failure wins):
    1. If kyc_status == "false": set compliance_status = "REJECTED",
       violation_code = "KYC_MISSING", appraised_value_usd = "0.0",
       collateral_value_usd = "0.0".
    2. If vision_report contains any of the words "counterfeit", "damaged",
       "unverified", "stolen", "forged": set compliance_status = "REJECTED",
       violation_code = "ASSET_UNVERIFIED", both values "0.0".
    3. If vision_report contains indicators of sanctions or high-risk jurisdiction:
       set compliance_status = "REJECTED", violation_code = "AML_SUSPICIOUS",
       both values "0.0".

    Appraisal rules (only reached if compliance passes):
    - appraised_value_usd is derived from vision_report asset value fields
      combined with relevant six_rates (e.g. gold: price_per_troy_oz * weight_oz;
      real estate: market_value_local * fx_rate_to_usd).
    - collateral_value_usd = appraised_value_usd * float(ltv_ratio).
    - compliance_status = "APPROVED", violation_code = "".

    Output format:
    - think must contain step-by-step reasoning wrapped in <think>...</think> tags.
    - vault_intent_json must be a single valid JSON object — no markdown fences,
      no prose. Required fields: vault_id, asset_identifier, asset_domain,
      appraised_value_usd (float), ltv_ratio (float), collateral_value_usd (float),
      stablecoin_currency, wallet_address, reasoning.
    - vault_id format: "vault-<asset_domain>-<wallet_address[:8]>".
    - stablecoin_currency must be "USDC" unless six_rates specifies otherwise.

    Example output (KYC rejected):
    vault_intent_json = {
      "vault_id": "vault-GOLD-abc12345",
      "asset_identifier": "gold-bar-001",
      "asset_domain": "GOLD",
      "appraised_value_usd": 0.0,
      "ltv_ratio": 0.60,
      "collateral_value_usd": 0.0,
      "stablecoin_currency": "USDC",
      "wallet_address": "abc12345...",
      "reasoning": "REJECTED: KYC_MISSING — wallet not verified."
    }

    Example output (approved):
    vault_intent_json = {
      "vault_id": "vault-GOLD-abc12345",
      "asset_identifier": "gold-bar-001",
      "asset_domain": "GOLD",
      "appraised_value_usd": 62000.0,
      "ltv_ratio": 0.60,
      "collateral_value_usd": 37200.0,
      "stablecoin_currency": "USDC",
      "wallet_address": "abc12345...",
      "reasoning": "KYC passed. 2 troy oz gold at $31000/oz = $62000. LTV 60% = $37200 USDC."
    }
    """

    vision_report: str = dspy.InputField(
        desc="JSON string from Gemma 3 describing the physical asset: type, condition, "
        "weight/size, estimated value, and any anomalies detected."
    )
    wallet_address: str = dspy.InputField(
        desc="Solana wallet address of the counterparty submitting the asset."
    )
    kyc_status: str = dspy.InputField(
        desc='KYC verification status as a plain string: "true" (verified) or "false" (not verified).'
    )
    six_rates: str = dspy.InputField(
        desc="JSON string of SIX data partner FX and precious metals rates "
        "(e.g. XAU/USD, XAG/USD, EUR/USD) used for asset valuation."
    )
    ltv_ratio: str = dspy.InputField(
        desc="Loan-to-value ratio as a plain float string (e.g. '0.60'). "
        "collateral_value_usd = appraised_value_usd * ltv_ratio."
    )
    system_vitals: str = dspy.InputField(
        desc="JSON string with system health metrics (CPU, memory, latency)."
    )

    think: str = dspy.OutputField(
        desc="Step-by-step compliance and appraisal reasoning wrapped in <think>...</think> tags."
    )
    compliance_status: str = dspy.OutputField(
        desc='Compliance decision: "APPROVED" or "REJECTED".'
    )
    violation_code: str = dspy.OutputField(
        desc='Empty string if approved. One of: "KYC_MISSING", "AML_SUSPICIOUS", '
        '"ASSET_UNVERIFIED" if rejected.'
    )
    appraised_value_usd: str = dspy.OutputField(
        desc='Appraised asset value in USD as a plain float string. "0.0" if rejected.'
    )
    collateral_value_usd: str = dspy.OutputField(
        desc='Collateral value (appraised * ltv_ratio) as a plain float string. "0.0" if rejected.'
    )
    vault_intent_json: str = dspy.OutputField(
        desc="A single valid JSON object with fields: vault_id, asset_identifier, "
        "asset_domain, appraised_value_usd (float), ltv_ratio (float), "
        "collateral_value_usd (float), stablecoin_currency, wallet_address, reasoning. "
        "No markdown fences, no extra text."
    )


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
    risk_category: str = dspy.OutputField(desc="One of: LOW, MEDIUM, HIGH, CRITICAL.")


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
