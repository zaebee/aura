from langchain_mistralai import MistralAIEmbeddings

from src.config import settings
from src.config.llm import get_raw_key


def get_embeddings_model(model: str = "mistral-embed") -> MistralAIEmbeddings:
    return MistralAIEmbeddings(
        model=model,
        mistral_api_key=get_raw_key(settings.llm.api_key),
    )


def generate_embedding(text: str) -> list[float]:
    model = get_embeddings_model()
    return model.embed_query(text)
