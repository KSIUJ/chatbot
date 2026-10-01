"""Aplikacja FastAPI: czat, historia rozmow, logowanie i statystyki.

Za nginxem endpointy sa pod /api/* (nginx obcina prefiks), backend widzi
sciezki bez /api.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import get_auth_settings, require_member, router as auth_router, verify_origin
from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    ANONYMOUS_CONVERSATIONS_COUNTER,
    PROMPTS_COUNTER,
    SessionLocal,
    add_message,
    count_users,
    create_conversation as db_create_conversation,
    delete_last_assistant_message,
    get_conversation as db_get_conversation,
    get_counter,
    get_db,
    get_messages,
)
from .history import (
    HistorySettings,
    conversation_lock,
    delete_user_conversation,
    get_history_settings,
    list_user_conversations,
    make_room_for_new_conversation,
    retention_loop,
)
from .llm.generate import answer as rag_answer
from .models import Conversation, Message, MessageRole, User
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationList,
    ConversationResponse,
    ConversationSummary,
    HealthResponse,
    MessageResponse,
    StatsResponse,
)


def start_retention_task() -> asyncio.Task[None]:
    """Petla kasujaca wygasle rozmowy (testy podmieniaja to na no-op)."""
    return asyncio.create_task(retention_loop(SessionLocal, get_history_settings()))


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Brak/bledna konfiguracja OIDC albo CHAT_HISTORY_* zatrzymuje start z opisem bledu
    get_auth_settings()
    get_history_settings()
    task = start_retention_task()
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


# verify_origin sprawdza naglowek Origin przy kazdym POST/PUT/PATCH/DELETE
app = FastAPI(title=APP_NAME, dependencies=[Depends(verify_origin)], lifespan=lifespan)

# CORS potrzebny tylko gdy frontend i API sa na roznych originach (w Dockerze
# i w vite z proxy jest jeden origin). Z ciasteczkami nie wolno uzyc "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(auth_router)


def _generate_answer(message: str, history: list[dict[str, str]]) -> tuple[str, list[str]]:
    """Odpowiedz RAG + LLM i lista plikow zrodlowych."""
    result = rag_answer(message, history=history)
    return result["answer"], result["files"]


def _get_owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    """Rozmowa tylko dla wlasciciela - cudza albo anonimowa wyglada jak
    nieistniejaca (404), wiec nie da sie zgadywac id."""
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


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


@app.get("/conversations", response_model=ConversationList)
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    history: HistorySettings = Depends(get_history_settings),
) -> ConversationList:
    """Historia w sidebarze: najnowsze rozmowy uzytkownika i limity retencji."""
    return ConversationList(
        conversations=[
            ConversationSummary(id=c.id, title=c.title, last_message_at=c.last_message_at)
            for c in list_user_conversations(db, user.id, history.max_per_user)
        ],
        max_per_user=history.max_per_user,
        retention_days=history.retention_days,
    )


@app.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> ConversationResponse:
    """Rozmowa razem z wiadomosciami."""
    conversation = _get_owned_conversation(db, conversation_id, user)

    messages = get_messages(db, conversation_id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[_to_message_response(m) for m in messages],
    )


@app.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, db: Session = Depends(get_db), user: User = Depends(require_member)
) -> Response:
    if not delete_user_conversation(db, user.id, conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    history_settings: HistorySettings = Depends(get_history_settings),
) -> ChatResponse:
    """Pytanie do czatu. Id nowej rozmowy nadaje klient (32 hex), wiec
    ponowienie po bledzie albo przerwaniu trafia do tej samej rozmowy."""
    conversation_id = payload.conversation_id or uuid4().hex
    # zapytania o te sama rozmowe ida po kolei
    with conversation_lock(conversation_id):
        conversation = db.get(Conversation, conversation_id, populate_existing=True)
        if conversation is None:
            return _start_conversation(db, user, conversation_id, payload.message, history_settings)
        if conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="conversation not found")
        return _continue_conversation(db, conversation, payload)


def _start_conversation(
    db: Session, user: User, conversation_id: str, question: str, history_settings: HistorySettings
) -> ChatResponse:
    # najpierw odpowiedz: blad LLM nie moze skasowac najstarszej rozmowy
    # ani zostawic pustej
    answer_text, sources = _generate_answer(question, [])

    # po osiagnieciu limitu nowa rozmowa wypycha najstarsza
    make_room_for_new_conversation(db, user.id, history_settings.max_per_user)
    conversation = db_create_conversation(db, user_id=user.id, conversation_id=conversation_id)
    add_message(db, conversation.id, MessageRole.USER, question)
    assistant_message = add_message(db, conversation.id, MessageRole.ASSISTANT, answer_text, sources)
    return ChatResponse(conversation_id=conversation.id, message=_to_message_response(assistant_message))


def _continue_conversation(db: Session, conversation: Conversation, payload: ChatRequest) -> ChatResponse:
    previous = get_messages(db, conversation.id)
    if payload.regenerate:
        # regeneracja powtarza ostatnie pytanie - ani odrzucona odpowiedz,
        # ani samo pytanie nie trafiaja do historii
        if previous and previous[-1].role == MessageRole.ASSISTANT:
            previous = previous[:-1]
        if previous and previous[-1].role == MessageRole.USER:
            previous = previous[:-1]
    history = [{"role": m.role.value, "content": m.content} for m in previous]

    # zapis dopiero po udanej odpowiedzi - blad LLM zostawia rozmowe bez zmian
    answer_text, sources = _generate_answer(payload.message, history)

    if payload.regenerate:
        # stara odpowiedz znika w tym samym commicie, w ktorym zapisuje sie nowa
        delete_last_assistant_message(db, conversation.id)
    else:
        add_message(db, conversation.id, MessageRole.USER, payload.message)
    assistant_message = add_message(db, conversation.id, MessageRole.ASSISTANT, answer_text, sources)

    return ChatResponse(
        conversation_id=conversation.id,
        message=_to_message_response(assistant_message),
    )


@app.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    """Zbiorcze statystyki uzycia."""
    return StatsResponse(
        accounts_created=count_users(db),
        anonymous_conversations=get_counter(db, ANONYMOUS_CONVERSATIONS_COUNTER),
        total_prompts=get_counter(db, PROMPTS_COUNTER),
    )
