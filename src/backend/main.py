
#uvicorn src.backend.main:app --reload
import os
from fastapi.staticfiles import StaticFiles
from .llm.generate import answer as rag_answer
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import APP_NAME, FRONTEND_ORIGINS
from .database import conversations
from .models import Message, MessageRole
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationResponse,
    HealthResponse,
    MessageResponse,
)

#TODO no tu zmieniajcie co chcecie to takie dla inspiracji, w miarę powinno działać

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _generate_answer(message: str) -> tuple[str, list[str]]:
    result = rag_answer(message)
    return result["answer"], result["files"]


def _to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        sources=message.sources,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/conversations", response_model=ConversationResponse)
def create_conversation() -> ConversationResponse:
    conversation = conversations.create()
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[],
    )


@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str) -> ConversationResponse:
    conversation = conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Konwersacja nie znaleziona")

    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[_to_message_response(m) for m in conversation.messages],
    )


"""Zrobione wzglednie w sensie no zwraca ladnie te wiadomosci ale nie obsluguje
conversation_id i nie zapisuje w bazie, wiec to do zmiany"""

@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """Glowny endpoint: przyjmuje wiadomosc uzytkownika, zapisuje ja w historii,
    generuje odpowiedz (na razie placeholder) i zwraca ja wraz z conversation_id.
    """
    if payload.conversation_id is not None:
        conversation = conversations.get(payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Konwersacja nie znaleziona")
    else:
        conversation = conversations.create()

    user_message = Message(role=MessageRole.USER, content=payload.message)
    conversations.add_message(conversation.id, user_message)

    answer_text, sources = _generate_answer(payload.message)
    assistant_message = Message(role=MessageRole.ASSISTANT, content=answer_text, sources=sources)
    conversations.add_message(conversation.id, assistant_message)

    return ChatResponse(
        conversation_id=conversation.id,
        message=_to_message_response(assistant_message),
    )
