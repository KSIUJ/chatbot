from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None 


class CreateConversationRequest(BaseModel):
    pass 
