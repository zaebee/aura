from langchain_mistralai import MistralAIEmbeddings

from config import settings
from config.llm import get_raw_key


def get_embeddings_model():
    return MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=get_raw_key(settings.llm.mistral_api_key),
    )


def generate_embedding(text: str):
    model = get_embeddings_model()
    return model.embed_query(text)
