"""Aplikacja FastAPI: czat, historia rozmow, logowanie i statystyki.

Za nginxem endpointy sa pod /api/* (nginx obcina prefiks), backend widzi
sciezki bez /api.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from .auth import get_auth_settings, require_member, router as auth_router, verify_origin
from .chat import ChatTurn, ConversationNotOwned, load_history, save_exchange, to_message_response
from .chat_stream import SSE_HEADERS, chat_events
from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    ANONYMOUS_CONVERSATIONS_COUNTER,
    PROMPTS_COUNTER,
    SessionLocal,
    count_users,
    get_conversation as db_get_conversation,
    get_counter,
    get_db,
    get_messages,
    get_session_factory,
)
from .auth.service import purge_expired_sessions
from .history import (
    CleanupJob,
    HistorySettings,
    conversation_lock,
    delete_user_conversation,
    get_history_settings,
    list_user_conversations,
    purge_expired_conversations,
    retention_loop,
)
from .llm.generate import answer as rag_answer, stream_answer as rag_stream
from .models import Conversation, User
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationList,
    ConversationResponse,
    ConversationSummary,
    HealthResponse,
    StatsResponse,
)


def configure_logging() -> None:
    """Logi aplikacji (src.backend.*) od INFO na stderr. Uvicorn konfiguruje
    tylko swoje loggery, wiec bez tego Python pokazuje jedynie WARNING+ i
    np. powod odmowy logowania nie trafia do `docker compose logs`."""
    package_logger = logging.getLogger("src.backend")
    if package_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.INFO)


configure_logging()


def cleanup_jobs(settings: HistorySettings) -> dict[str, CleanupJob]:
    """Zadania sprzatania w tle: nieuzywane rozmowy i wygasle sesje logowania."""
    return {
        "conversations": lambda db: purge_expired_conversations(db, settings.retention_days),
        "sessions": purge_expired_sessions,
    }


def start_retention_task() -> asyncio.Task[None]:
    """Petla sprzatajaca w tle (testy podmieniaja to na no-op)."""
    settings = get_history_settings()
    return asyncio.create_task(
        retention_loop(SessionLocal, settings.purge_interval_hours, cleanup_jobs(settings))
    )


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


def _get_owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    """Rozmowa tylko dla wlasciciela - cudza albo anonimowa wyglada jak
    nieistniejaca (404), wiec nie da sie zgadywac id."""
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


def _new_turn(payload: ChatRequest, user: User, history_settings: HistorySettings) -> ChatTurn:
    """Tura czatu z zapytania. Id nowej rozmowy nadaje klient (32 hex), wiec
    ponowienie po bledzie albo przerwaniu trafia do tej samej rozmowy."""
    return ChatTurn(
        user_id=user.id,
        conversation_id=payload.conversation_id or uuid4().hex,
        question=payload.message,
        regenerate=payload.regenerate,
        language=payload.language,
        max_per_user=history_settings.max_per_user,
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
        messages=[to_message_response(m) for m in messages],
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
    """Pytanie do czatu, odpowiedz w calosci (JSON)."""
    turn = _new_turn(payload, user, history_settings)
    # zapytania o te sama rozmowe ida po kolei
    with conversation_lock(turn.conversation_id):
        try:
            history = load_history(db, turn)
        except ConversationNotOwned:
            raise HTTPException(status_code=404, detail="conversation not found") from None
        # najpierw odpowiedz: blad LLM zostawia rozmowe bez zmian, nie kasuje
        # najstarszej rozmowy i nie zostawia pustej
        result = rag_answer(turn.question, history=history, language=turn.language)
        assistant_message = save_exchange(db, turn, result["answer"], result["sources"])
    return ChatResponse(conversation_id=turn.conversation_id, message=to_message_response(assistant_message))


def _prepare_stream_turn(
    db: Session, payload: ChatRequest, user: User, history_settings: HistorySettings
) -> ChatTurn:
    """Tura dla strumienia; cudza rozmowa -> 404 jeszcze przed strumieniem.
    Sesja zapytania jest potem zamykana - strumien uzywa wlasnych sesji, a ta
    trzymalaby polaczenie z puli przez cale generowanie."""
    try:
        turn = _new_turn(payload, user, history_settings)
        conversation = db.get(Conversation, turn.conversation_id, populate_existing=True)
        if conversation is not None and conversation.user_id != turn.user_id:
            raise HTTPException(status_code=404, detail="conversation not found")
        return turn
    finally:
        db.close()


@app.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Zdarzenia SSE: delta, done, error"}},
)
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_member),
    history_settings: HistorySettings = Depends(get_history_settings),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> StreamingResponse:
    """Pytanie do czatu, odpowiedz strumieniowana (SSE, patrz chat_stream.py).
    Bledy logowania, originu, walidacji i 404 wracaja jako zwykle odpowiedzi
    HTTP, zanim zacznie sie strumien."""
    turn = await run_in_threadpool(_prepare_stream_turn, db, payload, user, history_settings)
    return StreamingResponse(
        chat_events(request, session_factory, turn, rag_stream),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    """Zbiorcze statystyki uzycia."""
    return StatsResponse(
        accounts_created=count_users(db),
        anonymous_conversations=get_counter(db, ANONYMOUS_CONVERSATIONS_COUNTER),
        total_prompts=get_counter(db, PROMPTS_COUNTER),
    )
