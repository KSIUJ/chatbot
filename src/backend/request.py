from pydantic import BaseModel, Field

#tu szablony requestów
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    rag_count: int | None = Field(default=None, ge=1, le=8)


class CreateConversationRequest(BaseModel):
    pass 
