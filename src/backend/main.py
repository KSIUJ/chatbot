#python -m alembic upgrade head
#uvicorn src.backend.main:app --reload
import os
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# import llm logic
from .llm.generate import answer as rag_answer

from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    add_message,
    create_conversation as db_create_conversation,
    get_conversation as db_get_conversation,
    get_db,
    get_messages,
    init_db,
    count_registered_users,
    count_anonymous_conversations,
    count_prompts,
)
from .models import Message, MessageRole
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationResponse,
    HealthResponse,
    MessageResponse,
    StatsResponse,
)

app = FastAPI(title=APP_NAME)

# setup CORS so the frontend doesn't complain about cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# spin up the database on app startup
@app.on_event("startup")
def on_startup() -> None:
    init_db()


# quick wrapper to extract answer and files from rag_answer
def _generate_answer(message: str) -> tuple[str, list[str]]:
    result = rag_answer(message)
    return result["answer"], result["files"]


# helper function to map db message model to frontend response model
def _to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        sources=message.sources,
    )


# simple healthcheck endpoint to verify if the api is alive
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


# endpoint to spin up a new, empty conversation
@app.post("/conversations", response_model=ConversationResponse)
def create_conversation(db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = db_create_conversation(db)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[],
    )


# endpoint to grab an existing conversation along with its history
@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    messages = get_messages(db, conversation_id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[_to_message_response(m) for m in messages],
    )


# main chat endpoint: processes user query, hits the llm, and saves the chat history
@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    # fetch existing conversation or create a new one if id is missing
    if payload.conversation_id is not None:
        conversation = db_get_conversation(db, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        conversation = db_create_conversation(db)

    # step 1: log user's message into the database
    add_message(db, conversation.id, MessageRole.USER, payload.message)

    # step 2: pass the query to mikolaj's llm logic and get the answer + sources
    answer_text, sources = _generate_answer(payload.message)

    # step 3: save the llm's response back to the database
    assistant_message = add_message(db, conversation.id, MessageRole.ASSISTANT, answer_text)
    
    # step 4: attach source files to the message object (if any exist)
    assistant_message.sources = sources

    return ChatResponse(
        conversation_id=conversation.id,
        message=_to_message_response(assistant_message),
    )


@app.get("/api/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    return StatsResponse(
        accounts_created=count_registered_users(db),
        anonymous_conversations=count_anonymous_conversations(db),
        total_prompts=count_prompts(db),
    )