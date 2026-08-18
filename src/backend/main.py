#uvicorn src.backend.main:app --reload
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from RAG.context_builder import build_context

from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    add_message,
    create_conversation as db_create_conversation,
    get_conversation as db_get_conversation,
    get_db,
    get_messages,
    init_db,
)
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


@app.on_event("startup")
def on_startup() -> None:
    init_db()

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
def create_conversation(db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = db_create_conversation(db)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[],
    )


@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Konwersacja nie znaleziona")

    messages = get_messages(db, conversation_id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[_to_message_response(m) for m in messages],
    )


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if payload.conversation_id is not None:
        conversation = db_get_conversation(db, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        conversation = db_create_conversation(db)

    # 1. save user query to db
    add_message(db, conversation.id, MessageRole.USER, payload.message)

    # 2. RAG - build context from vector db
    context_prompt, image_paths = build_context(payload.message, top_k=5)

    # 3. LLM call (waiting for mikolaj's code)
    # eventually it'll look like: answer_text = ask_qwen(payload.message, context_prompt)
    
    # for now, just mock the response with lengths:
    answer_text = f"found context of length {len(context_prompt)} and {len(image_paths)} images."

    # 4. save assistant reply to db
    assistant_message = add_message(db, conversation.id, MessageRole.ASSISTANT, answer_text)
    
    # for now, let's use image paths as sources (or an empty list)
    assistant_message.sources = image_paths

    return ChatResponse(
        conversation_id=conversation.id,
        message=_to_message_response(assistant_message),
    )