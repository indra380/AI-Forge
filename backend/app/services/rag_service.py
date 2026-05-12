from app.services.in_chat_rag_service import InChatRagService, get_in_chat_rag_service

# Compatibility facade for the unified chat architecture. The in-chat RAG service
# is the canonical implementation used by the chat pipeline.
RagService = InChatRagService


def get_rag_service() -> InChatRagService:
    return get_in_chat_rag_service()
