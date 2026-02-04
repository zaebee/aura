from .main import HiveAggregator

def generate_embedding(text: str) -> list[float]:
    """Legacy wrapper for generate_embedding.
    In the Crystalline State, this should be called via Reasoning Protein."""
    from config import get_settings
    from config.llm import get_raw_key
    from langchain_mistralai import MistralAIEmbeddings

    settings = get_settings()
    embeddings = MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=get_raw_key(settings.llm.api_key),
    )
    return embeddings.embed_query(text)

__all__ = ["HiveAggregator", "generate_embedding"]
