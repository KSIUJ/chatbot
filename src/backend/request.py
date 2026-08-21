from pydantic import BaseModel, Field

#tu szablony requestów
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None 


class CreateConversationRequest(BaseModel):
    pass 

class RegisterRequest(BaseModel):
    email: str
    haslo: str = Field(min_length=8)


class VerifyMailRequest(BaseModel):
    email: str
    kod: str


class LoginRequest(BaseModel):
    email: str
    haslo: str