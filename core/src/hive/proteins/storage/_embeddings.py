from langchain_mistralai import MistralAIEmbeddings

from config import get_settings
from config.llm import get_raw_key

settings = get_settings()

# Instantiate the default model once at the module level for efficiency.
_default_model = MistralAIEmbeddings(
    model="mistral-embed",
    mistral_api_key=get_raw_key(settings.llm.api_key),
)


def get_embeddings_model(model: str = "mistral-embed") -> MistralAIEmbeddings:
    if model == "mistral-embed":
        return _default_model
    return MistralAIEmbeddings(
        model=model,
        mistral_api_key=get_raw_key(settings.llm.api_key),
    )


def generate_embedding(text: str) -> list[float]:
    model = get_embeddings_model()
    return model.embed_query(text)
