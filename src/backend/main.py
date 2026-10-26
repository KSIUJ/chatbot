"""Aplikacja FastAPI: czat, historia rozmow, logowanie, oceny odpowiedzi,
dzienne limity pytan, panel administratora, statystyki, motyw okazjonalny
z ksi.sh i polaczenie konta z USOS.

Za nginxem endpointy sa pod /api/* (nginx obcina prefiks), backend widzi
sciezki bez /api.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from functools import partial
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from .admin import router as admin_router
from .attachments.errors import AttachmentError, attachment_error_handler
from .attachments.router import router as attachments_router
from .attachments.service import attachments_by_message, purge_stale_attachments
from .auth import get_auth_settings, require_member, router as auth_router, verify_origin
from .chat import (
    ChatTurn,
    ConversationNotOwned,
    load_history,
    model_kwargs,
    record_turn_incident,
    save_exchange,
    to_message_response,
    with_attachments,
)
from . import chat_runs
from .chat_stream import SSE_HEADERS, chat_events
from .config import API_DOCS, APP_NAME, FRONTEND_ORIGINS
from .feedback import admin_router as feedback_admin_router, conversation_feedback, router as feedback_router
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
    vacuum_free_pages,
)
from .auth.service import purge_expired_sessions
from .limits import (
    ChatDisabled,
    LimitExceeded,
    chat_disabled_handler,
    ensure_chat_enabled,
    limit_exceeded_handler,
    router as limits_router,
)
from .limits.settings import get_default_limits
from .limits.usage import (
    Clock,
    Reservation,
    consume_question,
    get_clock,
    purge_old_usage,
    refund_in_new_session,
)
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
from .rag.core.context import warm_up as rag_warm_up
from .occasion import router as occasion_router
from .occasion.settings import get_occasion_settings
from .usos import get_usos_settings, router as usos_router
from .usos.client import UsosClient
from .usos.crypto import UsosTokenCipher
from .usos.dependencies import get_usos_client, get_usos_token_cipher
from .usos.settings import UsosSettings
from .usos.tools import build_usos_toolbox
from .llm.dates import warsaw_now
from .occasion.state import get_occasion_store, refresh_loop
from .llm.generate import answer as rag_answer, stream_answer as rag_stream
from .llm.language import REFUSAL
from .feedback.service import EMPTY_STATE, purge_old_feedback
from .security import admin_router as security_admin_router
from .security.blocks import ChatBlocked, chat_blocked_handler, ensure_not_blocked
from .security.incidents import purge_old_incidents
from .security.injection import detect_injection
from .security.marker import strip_violation_marker
from .models import Conversation, MessageRole, User
from .request import ChatRequest, StopRequest
from .response import (
    ChatResponse,
    ConversationList,
    ConversationResponse,
    ConversationSummary,
    HealthResponse,
    PendingAnswer,
    PendingAnswers,
    StatsResponse,
    StopResponse,
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
    logging.getLogger("uvicorn.access").addFilter(skip_facade_requests)
    logging.getLogger("uvicorn.access").addFilter(redact_usos_callback)


def skip_facade_requests(record: logging.LogRecord) -> bool:
    """Bez wpisow o pobraniu fasady okazji w logu dostepu uvicorna: zdradzalyby,
    kiedy trwala ktora okazja (harmonogram jest tajny, patrz occasion/).
    Argumenty wpisu uvicorna: (klient, metoda, sciezka, wersja HTTP, status)."""
    args = record.args
    path = args[2] if isinstance(args, tuple) and len(args) > 2 else None
    return not (isinstance(path, str) and path.startswith("/occasion/facade/"))


_USOS_CALLBACK = "/usos/callback"


def redact_usos_callback(record: logging.LogRecord) -> bool:
    """Powrot z USOS zostaje w logu dostepu, ale bez zapytania: niesie
    jednorazowy request token i verifier (oauth_token, oauth_verifier)."""
    args = record.args
    if isinstance(args, tuple) and len(args) > 2 and isinstance(args[2], str):
        path = args[2]
        if path.startswith(_USOS_CALLBACK + "?"):
            record.args = (*args[:2], _USOS_CALLBACK + "?[redacted]", *args[3:])
    return True


configure_logging()

logger = logging.getLogger(__name__)


def cleanup_jobs(settings: HistorySettings) -> dict[str, CleanupJob]:
    """Zadania sprzatania w tle: nieuzywane rozmowy (razem z zalacznikami),
    wygasle sesje logowania, incydenty bezpieczenstwa starsze niz
    INCIDENT_RETENTION_DAYS, oceny bez zmian od FEEDBACK_RETENTION_DAYS,
    dzienne liczniki starsze niz USAGE_RETENTION_DAYS, niewyslane zalaczniki
    starsze niz doba, a na koniec VACUUM bazy SQLite."""
    return {
        "conversations": lambda db: purge_expired_conversations(db, settings.retention_days),
        "sessions": purge_expired_sessions,
        "incidents": purge_old_incidents,
        "feedback": purge_old_feedback,
        "daily_usage": purge_old_usage,
        "attachments": purge_stale_attachments,
        # na koncu: wolne strony po powyzszych DELETE
        "vacuum": vacuum_free_pages,
    }


def start_retention_task() -> asyncio.Task[None]:
    """Petla sprzatajaca w tle (testy podmieniaja to na no-op)."""
    settings = get_history_settings()
    return asyncio.create_task(
        retention_loop(SessionLocal, settings.purge_interval_hours, cleanup_jobs(settings))
    )


def _warm_up_rag() -> None:
    try:
        seconds = rag_warm_up()
    except Exception:
        # brak indeksu albo modelu nie blokuje startu - pierwsze pytanie sprobuje ponownie
        logger.exception("rag warm-up failed")
        return
    logger.info("rag warm-up done in %.1f s", seconds)


def start_warmup_task() -> asyncio.Task[None] | None:
    """Ladowanie modelu embeddingow i indeksow RAG w tle zaraz po starcie (testy
    podmieniaja to na no-op). Nie blokuje startu - healthcheck odpowiada od razu.
    RAG_WARMUP=off wylacza (np. lokalnie bez danych)."""
    if os.getenv("RAG_WARMUP", "on").strip().lower() in {"0", "off", "false", "no", "nie"}:
        return None
    return asyncio.create_task(asyncio.to_thread(_warm_up_rag))


def start_occasion_task() -> asyncio.Task[None] | None:
    """Odswiezanie motywu okazjonalnego z ksi.sh w tle (testy podmieniaja to
    na no-op). Wylaczone OCCASION_SOURCE_URL = od razu "brak okazji"."""
    settings = get_occasion_settings()
    store = get_occasion_store()
    if settings.source_url is None:
        store.set(None)
        return None
    return asyncio.create_task(
        refresh_loop(store, settings.source_url, settings.refresh_seconds, api_token=settings.api_token)
    )


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Brak/bledna konfiguracja OIDC, CHAT_HISTORY_*, limitow (CHAT_DAILY_LIMIT,
    # ATTACHMENT_*), OCCASION_* albo USOS_* zatrzymuje start z opisem bledu
    get_auth_settings()
    get_history_settings()
    get_default_limits()
    get_occasion_settings()
    get_usos_settings()
    tasks = [task for task in (start_retention_task(), start_occasion_task(), start_warmup_task()) if task is not None]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


# verify_origin sprawdza naglowek Origin przy kazdym POST/PUT/PATCH/DELETE
app = FastAPI(
    title=APP_NAME,
    dependencies=[Depends(verify_origin)],
    lifespan=lifespan,
    docs_url="/docs" if API_DOCS else None,
    redoc_url="/redoc" if API_DOCS else None,
    openapi_url="/openapi.json" if API_DOCS else None,
)
# wyczerpany dzienny limit pytan -> 429 z kodem rate_limited (przed strumieniem)
app.add_exception_handler(LimitExceeded, limit_exceeded_handler)
# czat wylaczony przez zarzad -> 503 chat_disabled (przed limitem i modelem)
app.add_exception_handler(ChatDisabled, chat_disabled_handler)
# osoba zablokowana po ostrzezeniach -> 403 chat_blocked (po wylaczniku, przed limitem)
app.add_exception_handler(ChatBlocked, chat_blocked_handler)
# odrzucony plik / zalacznik w pytaniu -> kod w detail.code (attachments/errors.py)
app.add_exception_handler(AttachmentError, attachment_error_handler)

# CORS potrzebny tylko gdy frontend i API sa na roznych originach (w Dockerze
# i w vite z proxy jest jeden origin). Z ciasteczkami nie wolno uzyc "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    # X-Filename: nazwa pliku przy POST /attachments
    allow_headers=["Content-Type", "X-Filename"],
)

app.include_router(auth_router)
app.include_router(feedback_router)
app.include_router(feedback_admin_router)
app.include_router(security_admin_router)
app.include_router(limits_router)
app.include_router(admin_router)
app.include_router(attachments_router)
app.include_router(occasion_router)
app.include_router(usos_router)


def _get_owned_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    """Rozmowa tylko dla wlasciciela - cudza albo anonimowa wyglada jak
    nieistniejaca (404), wiec nie da sie zgadywac id."""
    conversation = db_get_conversation(db, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


def _new_turn(payload: ChatRequest, user: User, history_settings: HistorySettings) -> ChatTurn:
    """Tura czatu z zapytania. Id nowej rozmowy nadaje klient (32 hex), wiec
    ponowienie po bledzie albo przerwaniu trafia do tej samej rozmowy.
    Heurystyka prob obejscia promptu dziala tu, przed wywolaniem modelu -
    niczego nie blokuje, trafienia trafiaja do incydentu na koncu tury."""
    return ChatTurn(
        user_id=user.id,
        conversation_id=payload.conversation_id or uuid4().hex,
        question=payload.message,
        regenerate=payload.regenerate,
        language=payload.language,
        max_per_user=history_settings.max_per_user,
        injection_rules=tuple(detect_injection(payload.message)),
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
    """Rozmowa razem z wiadomosciami; odpowiedzi asystenta niosa ocene
    biezacego uzytkownika (stan lapek po przeladowaniu), pytania - metadane
    wyslanych zalacznikow."""
    conversation = _get_owned_conversation(db, conversation_id, user)

    messages = get_messages(db, conversation_id)
    feedback = conversation_feedback(db, user.id, conversation_id)
    attachments = attachments_by_message(db, conversation_id)
    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=[
            to_message_response(
                m,
                feedback.get(m.id, EMPTY_STATE) if m.role == MessageRole.ASSISTANT else None,
                attachments.get(m.id, ()),
            )
            for m in messages
        ],
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
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    clock: Clock = Depends(get_clock),
) -> ChatResponse:
    """Pytanie do czatu, odpowiedz w calosci (JSON). Wiodacy znacznik
    [[NARUSZENIE]] jest zdejmowany przed zapisem i zglaszany jako incydent.
    Wyczerpany dzienny limit -> 429 (rate_limited), model nie jest wolany.
    Czat wylaczony przez zarzad -> 503 (chat_disabled) przed czymkolwiek,
    osoba zablokowana po ostrzezeniach -> 403 (chat_blocked)."""
    ensure_chat_enabled(db)
    ensure_not_blocked(user)
    turn = _new_turn(payload, user, history_settings)
    model_flagged = False
    saved = False
    # zapytania o te sama rozmowe ida po kolei
    with conversation_lock(turn.conversation_id):
        try:
            history = load_history(db, turn)
        except ConversationNotOwned:
            raise HTTPException(status_code=404, detail="conversation not found") from None
        # AttachmentError (404/422) - przed limitem i modelem
        turn = with_attachments(db, turn, payload.attachment_ids)
        # LimitExceeded -> 429; pytanie odrzucone limitem nie jest incydentem
        reservation = consume_question(db, user.id, clock())
        try:
            # najpierw odpowiedz: blad LLM zostawia rozmowe bez zmian, nie kasuje
            # najstarszej rozmowy i nie zostawia pustej
            result = rag_answer(turn.question, history=history, **model_kwargs(turn))
            answer_text, model_flagged = strip_violation_marker(result["answer"])
            if model_flagged and not answer_text.strip():
                answer_text = REFUSAL[turn.language]
            assistant_message = save_exchange(db, turn, answer_text, result["sources"])
            saved = True
        finally:
            if not saved:
                # blad serwera (model albo zapis; synchroniczny /chat nie jest
                # przerywany rozlaczeniem klienta) - pytanie wraca do limitu;
                # najpierw rollback, bo przerwany zapis trzymalby blokade SQLite
                db.rollback()
                refund_in_new_session(session_factory, reservation)
            # takze po bledzie modelu - trafienie heurystyki ma zostac zgloszone
            record_turn_incident(session_factory, turn, model_flagged, saved)
    return ChatResponse(conversation_id=turn.conversation_id, message=to_message_response(assistant_message))


def _prepare_stream_turn(
    db: Session, payload: ChatRequest, user: User, history_settings: HistorySettings, clock: Clock
) -> tuple[ChatTurn, Reservation]:
    """Tura dla strumienia; wylaczony czat -> 503 (ChatDisabled, przed
    czymkolwiek), zablokowana osoba -> 403 (ChatBlocked), cudza rozmowa ->
    404, wyczerpany limit -> 429 (LimitExceeded) - jeszcze przed strumieniem. Sesja zapytania jest potem
    zamykana - strumien uzywa wlasnych sesji, a ta trzymalaby polaczenie
    z puli przez cale generowanie."""
    try:
        ensure_chat_enabled(db)
        ensure_not_blocked(user)
        turn = _new_turn(payload, user, history_settings)
        conversation = db.get(Conversation, turn.conversation_id, populate_existing=True)
        if conversation is not None and conversation.user_id != turn.user_id:
            raise HTTPException(status_code=404, detail="conversation not found")
        # zalaczniki (404/422) przed limitem - odrzucone pytanie nic nie kosztuje
        turn = with_attachments(db, turn, payload.attachment_ids)
        return turn, consume_question(db, user.id, clock())
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
    clock: Clock = Depends(get_clock),
    usos_settings: UsosSettings = Depends(get_usos_settings),
    usos_client: UsosClient = Depends(get_usos_client),
    usos_cipher: UsosTokenCipher = Depends(get_usos_token_cipher),
) -> StreamingResponse:
    """Pytanie do czatu, odpowiedz strumieniowana (SSE, patrz chat_stream.py).
    Osoba z polaczonym kontem USOS daje modelowi narzedzia z jej danymi
    (usos/tools.py) - plan, przedmioty, oceny.
    Bledy logowania, originu, walidacji, 503 (czat wylaczony), 403 (blokada), 404 i 429 (dzienny limit) wracaja
    jako zwykle odpowiedzi HTTP, zanim zacznie sie strumien."""
    turn, reservation = await run_in_threadpool(_prepare_stream_turn, db, payload, user, history_settings, clock)
    refund = partial(refund_in_new_session, session_factory, reservation)
    tools = await run_in_threadpool(
        build_usos_toolbox, session_factory, turn.user_id, usos_settings, usos_client, usos_cipher,
        warsaw_now(clock()).date(),
    )
    stream_fn = partial(rag_stream, tools=tools) if tools is not None else rag_stream
    return StreamingResponse(
        chat_events(request, session_factory, turn, stream_fn, refund=refund),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/chat/stop", response_model=StopResponse)
def chat_stop(payload: StopRequest, user: User = Depends(require_member)) -> StopResponse:
    """Przycisk Stop: odpowiedz w toku konczy sie po biezacym kawalku, pytanie
    i dotychczasowy tekst zostaja zapisane. Samo zerwanie polaczenia (odswiezenie
    strony) odpowiedzi nie przerywa - patrz chat_stream.py."""
    return StopResponse(stopped=chat_runs.request_stop(user.id, payload.conversation_id))


@app.get("/chat/pending", response_model=PendingAnswers)
def chat_pending(response: Response, user: User = Depends(require_member)) -> PendingAnswers:
    """Odpowiedzi osoby jeszcze w toku (od najnowszej): pytanie i dotychczasowy
    tekst - frontend pokazuje je po odswiezeniu strony i czeka na zapis."""
    response.headers["Cache-Control"] = "no-store"
    items = []
    for turn in chat_runs.for_user(user.id):
        conversation_id, question, started_at, text = chat_runs.snapshot(turn)
        items.append(PendingAnswer(conversation_id=conversation_id, question=question, text=text, started_at=started_at))
    return PendingAnswers(items=items)


@app.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_member)])
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    """Zbiorcze statystyki uzycia (tylko dla zalogowanych czlonkow KSI)."""
    return StatsResponse(
        accounts_created=count_users(db),
        anonymous_conversations=get_counter(db, ANONYMOUS_CONVERSATIONS_COUNTER),
        total_prompts=get_counter(db, PROMPTS_COUNTER),
    )
