from app.core.config import settings
from app.core.loggin import get_logger

logger = get_logger(__name__)


def get_llm_service(*, realtime: bool = False):
    """Return the configured RAG answer generator (same `generate_answer` interface)."""
    provider = settings.REALTIME_LLM_PROVIDER if realtime else settings.LLM_PROVIDER
    p = (provider or settings.LLM_PROVIDER).lower().strip()
    if p == "openai":
        from app.services.openai_service import OpenAIService

        model_name = (
            settings.REALTIME_OPENAI_MODEL if realtime else settings.OPENAI_MODEL
        )
        return OpenAIService(model_name=model_name)
    if p in ("gemini", "google"):
        from app.services.gemini_service import GeminiService

        model_name = (
            settings.REALTIME_GEMINI_MODEL if realtime else settings.GEMINI_MODEL
        )
        return GeminiService(model_name=model_name)
    logger.warning("Unknown LLM provider=%r; using gemini", provider)
    from app.services.gemini_service import GeminiService

    model_name = settings.REALTIME_GEMINI_MODEL if realtime else settings.GEMINI_MODEL
    return GeminiService(model_name=model_name)
