from typing import Any

import httpx
import structlog
from aura_core import SkillProtocol
from aura_core_gen.aura.core.v1 import BlockchainDiscoveryResult, Observation

logger = structlog.get_logger(__name__)


class GoldRushSkill(SkillProtocol[Any, dict[str, Any], dict[str, Any], Observation]):
    """
    GoldRush Protein (The Foraging Organ): Fetches blockchain data using the x402 protocol.
    """

    def __init__(self) -> None:
        self.settings: Any = None
        self.registry: Any = None
        self.endpoints: dict[str, str] = {}  # Map operationId to path
        self._capabilities = {
            "fetch": self._fetch,
            "discover_endpoints": self._discover_endpoints,
        }

    def get_name(self) -> str:
        return "blockchain_data"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: Any, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.registry = provider.get("registry")

    async def initialize(self) -> bool:
        await self._discover_endpoints({})
        return True

    def inject_registry(self, registry: Any) -> None:
        self.registry = registry

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"GoldRush skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _discover_endpoints(self, params: dict[str, Any]) -> Observation:
        """Parses GoldRush llms.txt for automatic mapping."""
        discovery_url = str(
            getattr(self.settings, "discovery_url", "https://goldrush.dev/llms.txt")
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(discovery_url)
                resp.raise_for_status()
                lines = resp.text.split("\n")
                current_op = None
                for line in lines:
                    if "Operation ID:" in line:
                        current_op = line.split("Operation ID:")[1].strip()
                    elif "Endpoint Path:" in line and current_op:
                        path = line.split("Endpoint Path:")[1].strip()
                        # Clean up path (remove leading /v1 if it starts with it)
                        if path.startswith("/v1"):
                            path = path[3:]
                        self.endpoints[current_op] = path
                        current_op = None
                logger.info("goldrush_discovery_complete", count=len(self.endpoints))
            return Observation(success=True)
        except Exception as e:
            logger.error(f"GoldRush discovery failed: {e}")
            return Observation(success=False, error=str(e))

    async def _fetch(self, params: dict[str, Any]) -> Observation:
        """The 402 Loop: Handles payment-gated requests."""
        operation_id = str(params.get("operation_id", ""))
        path_params = params.get("path_params", {})
        query_params = params.get("query_params", {})

        path = self.endpoints.get(operation_id)
        if not path:
            return Observation(
                success=False, error=f"Unknown operation: {operation_id}"
            )

        # Format path (e.g. /v1/{chainName}/address/{walletAddress}/balances_v2/)
        base_url = str(
            getattr(self.settings, "base_url", "https://x402.goldrush.dev/v1")
        )
        url = f"{base_url}{path.format(**path_params)}"

        async with httpx.AsyncClient() as client:
            # 1. Initial attempt
            resp = await client.get(url, params=query_params)

            if resp.status_code == 200:
                return self._to_observation(resp)

            if resp.status_code == 402:
                logger.info("goldrush_402_required", url=url)
                # 2. Extract payment instructions
                payment_instructions = resp.headers.get("X-Payment-Instructions")
                if not payment_instructions:
                    return Observation(
                        success=False, error="Missing X-Payment-Instructions"
                    )

                # Parse instructions (recipient=0x...;amount=0.05;network=base-sepolia)
                instr = {}
                for item in payment_instructions.split(";"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        instr[k.strip()] = v.strip()

                recipient = instr.get("recipient")
                amount_str = instr.get("amount")
                network = instr.get("network")

                if not all((recipient, amount_str, network)):
                    return Observation(
                        success=False,
                        error="Incomplete payment instructions in X-Payment-Instructions header.",
                    )

                try:
                    amount = float(amount_str)  # type: ignore
                except (ValueError, TypeError):
                    return Observation(
                        success=False,
                        error=f"Invalid amount in X-Payment-Instructions header: {amount_str}",
                    )

                # 3. Guard: validate recipient is sanctified and within x402 cap
                if not self.registry:
                    return Observation(
                        success=False, error="Skill registry not available"
                    )

                guard_obs = await self.registry.execute(
                    "guard",
                    "validate_x402_payment",
                    {"wallet_address": recipient, "amount": amount},
                )
                if not guard_obs.success:
                    logger.warning(
                        "goldrush_x402_blocked",
                        recipient=recipient,
                        amount=amount,
                        reason=guard_obs.error,
                    )
                    return Observation(
                        success=False,
                        error=f"x402_payment_blocked: {guard_obs.error}",
                    )

                # 4. Pay via TransactionSkill
                transaction = self.registry.get("transaction")
                if not transaction:
                    return Observation(
                        success=False, error="Transaction protein not found"
                    )

                pay_obs = await transaction.execute(
                    "transfer",
                    {
                        "network": network,
                        "recipient": recipient,
                        "amount": amount,
                        "currency": "USDC",
                    },
                )

                if not pay_obs.success:
                    return Observation(
                        success=False, error=f"Payment failed: {pay_obs.error}"
                    )

                tx_hash = pay_obs.metadata.to_dict().get("transaction_hash")
                if not tx_hash:
                    return Observation(
                        success=False,
                        error=f"Payment observation missing transaction_hash: {pay_obs.error}",
                    )
                logger.info("goldrush_payment_confirmed", tx_hash=tx_hash)

                # Accounting: Log MetabolicCost
                persistence = self.registry.get("persistence")
                if persistence:
                    await persistence.execute(
                        "log_metabolic_cost",
                        {
                            "amount": amount,
                            "currency": "USDC",
                            "network": network,
                            "endpoint": url,
                            "tx_hash": tx_hash,
                        },
                    )

                # 5. Retry with X-Payment-Proof
                retry_resp = await client.get(
                    url, params=query_params, headers={"X-Payment-Proof": tx_hash}
                )

                if retry_resp.status_code == 200:
                    return self._to_observation(retry_resp, tx_hash)
                else:
                    return Observation(
                        success=False,
                        error=f"Retry failed with {retry_resp.status_code}: {retry_resp.text}",
                    )

            return Observation(
                success=False, error=f"Request failed with status {resp.status_code}"
            )

    def _to_observation(self, resp: httpx.Response, tx_hash: str = "") -> Observation:
        obs = Observation(success=True)
        obs.blockchain_discovery = BlockchainDiscoveryResult(
            raw_json=resp.text, transaction_hash=tx_hash
        )
        return obs
