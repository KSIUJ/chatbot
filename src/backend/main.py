from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# import llm logic
from .llm.generate import answer as rag_answer

from .auth import get_auth_settings, require_member, router as auth_router, verify_origin
from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    add_message,
    create_conversation as db_create_conversation,
    delete_last_assistant_message,
    get_conversation as db_get_conversation,
    get_db,
    get_messages,
    init_db,
    count_users,
    count_anonymous_conversations,
    count_prompts,
)
from .models import Conversation, Message, MessageRole, User
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationResponse,
    HealthResponse,
    MessageResponse,
    StatsResponse,
)

# verify_origin sprawdza naglowek Origin przy kazdym POST/PUT/PATCH/DELETE
app = FastAPI(title=APP_NAME, dependencies=[Depends(verify_origin)])

# CORS potrzebny tylko gdy frontend i API sa na roznych originach (w Dockerze
# i w vite z proxy jest jeden origin). Z ciasteczkami nie wolno uzyc "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_router)


# spin up the database on app startup
@app.on_event("startup")
def on_startup() -> None:
    # Brak/bledna konfiguracja OIDC zatrzymuje start z lista brakow (AuthConfigError)
    get_auth_settings()
    init_db()


# quick wrapper to extract answer and files from rag_answer
def _generate_answer(
    message: str, rag_count: int | None = None, history: list[dict] | None = None
) -> tuple[str, list[str]]:
    kwargs = {"k_mordor": rag_count, "k_other": rag_count} if rag_count else {}
    result = rag_answer(message, history=history, **kwargs)
    return result["answer"], result["files"]


# conversation lookup limited to its owner - foreign or anonymous ones look like
# they don't exist (404), so ids can't be probed
def _get_owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


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
def create_conversation(
    db: Session = Depends(get_db), user: User = Depends(require_member)
) -> ConversationResponse:
    conversation = db_create_conversation(db, user_id=user.id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[],
    )


# endpoint to grab an existing conversation along with its history
@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> ConversationResponse:
    conversation = _get_owned_conversation(db, conversation_id, user)

    messages = get_messages(db, conversation_id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[_to_message_response(m) for m in messages],
    )


# main chat endpoint: processes user query, hits the llm, and saves the chat history
@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> ChatResponse:
    # fetch the user's conversation or create a new one if id is missing
    if payload.conversation_id is not None:
        conversation = _get_owned_conversation(db, payload.conversation_id, user)
    else:
        conversation = db_create_conversation(db, user_id=user.id)

    # regeneration replays the last question, so drop the rejected answer instead
    # of appending a duplicate turn that would later be fed back as history
    regenerating = payload.regenerate and payload.conversation_id is not None
    if regenerating:
        delete_last_assistant_message(db, conversation.id)

    previous = get_messages(db, conversation.id)
    if regenerating and previous and previous[-1].role == MessageRole.USER:
        previous = previous[:-1]
    history = [{"role": m.role.value, "content": m.content} for m in previous]

    # step 1: log user's message into the database
    if not regenerating:
        add_message(db, conversation.id, MessageRole.USER, payload.message)

    # step 2: pass the query to mikolaj's llm logic and get the answer + sources
    answer_text, sources = _generate_answer(payload.message, payload.rag_count, history)

    # step 3: save the llm's response back to the database
    assistant_message = add_message(db, conversation.id, MessageRole.ASSISTANT, answer_text)

    # step 4: attach source files to the message object (if any exist)
    assistant_message.sources = sources

    return ChatResponse(
        conversation_id=conversation.id,
        message=_to_message_response(assistant_message),
    )



# endpoint returning aggregate usage statistics for recruiters/CV purposes
@app.get("/api/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    return StatsResponse(
        accounts_created=count_users(db),
        anonymous_conversations=count_anonymous_conversations(db),
        total_prompts=count_prompts(db),
    )