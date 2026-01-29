from pydantic import BaseModel, HttpUrl, SecretStr


class CryptoSettings(BaseModel):
    solana_rpc_url: HttpUrl = "https://api.mainnet-beta.solana.com"
    private_key: SecretStr = ""
