import os
import random
from datetime import datetime, timezone, timedelta
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

# import llm logic
from .llm.generate import answer as rag_answer

from .config import APP_NAME, FRONTEND_ORIGINS
from .database import (
    add_message,
    create_conversation as db_create_conversation,
    delete_last_assistant_message,
    get_conversation as db_get_conversation,
    get_db,
    get_messages,
    init_db,
    create_user,
    get_user_by_email,
    is_allowed_email,
    verify_password,
    hash_password,
)
from .models import Message, MessageRole, EmailCode
from .request import ChatRequest
from .response import (
    ChatResponse,
    ConversationResponse,
    HealthResponse,
    MessageResponse,
)

app = FastAPI(title=APP_NAME)

# setup CORS so the frontend doesn't complain about cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# auth schemas
class LoginRequest(BaseModel):
    email: str
    password: str
    rememberMe: bool = False

class SendCodeRequest(BaseModel):
    email: str

class VerifyAndRegisterRequest(BaseModel):
    email: str
    code: str
    password: str


# spin up the database on app startup
@app.on_event("startup")
def on_startup() -> None:
    init_db()


# quick wrapper to extract answer and files from rag_answer
def _generate_answer(
    message: str, rag_count: int | None = None, history: list[dict] | None = None
) -> tuple[str, list[str]]:
    kwargs = {"k_mordor": rag_count, "k_other": rag_count} if rag_count else {}
    result = rag_answer(message, history=history, **kwargs)
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


# endpoint to handle user login and verify password
@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = get_user_by_email(db, payload.email)
    
    # keep errors generic so we don't leak which emails are registered
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="invalid email or password")
        
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
        
    return {
        "status": "success",
        "user_id": user.id,
        "email": user.email
    }


# endpoint to generate and send a 6-digit verification code to the user's email
@app.post("/api/auth/register/send-code")
def send_registration_code(payload: SendCodeRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    
    # basic domain check
    if not is_allowed_email(email):
        raise HTTPException(status_code=400, detail="only uj.edu.pl emails are allowed")
        
    user = get_user_by_email(db, email)
    
    # if account exists and is already verified, block it
    if user and user.zweryfikowany:
        raise HTTPException(status_code=400, detail="account already exists")
        
    # if user doesn't exist at all, create a placeholder unverified user
    if not user:
        try:
            user = create_user(db=db, email=email)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
            
    # generate a random 6-digit code
    code = str(random.randint(100000, 999999))
    
    # code expires in 15 minutes
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    # save the code to the database linked to this user
    email_code = EmailCode(
        user_id=user.id,
        kod=code,
        typ="verify",
        expires_at=expires
    )
    db.add(email_code)
    db.commit()
    
    # mock sending an email (shows up in uvicorn console)
    print(f"\n[EMAIL MOCK] Verification code for {email}: {code}\n")
    
    return {"status": "success", "message": "code sent"}


# endpoint to verify the code and set the user's password
@app.post("/api/auth/register/verify")
def verify_and_register(payload: VerifyAndRegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    user = get_user_by_email(db, email)
    
    if not user:
        raise HTTPException(status_code=404, detail="user not found. request a code first.")
        
    if user.zweryfikowany:
        raise HTTPException(status_code=400, detail="account is already verified.")
        
    # fetch the latest unused verification code for this user
    stmt = (
        select(EmailCode)
        .where(EmailCode.user_id == user.id)
        .where(EmailCode.typ == "verify")
        .where(EmailCode.used == False)
        .order_by(EmailCode.expires_at.desc())
    )
    email_code = db.execute(stmt).scalars().first()
    
    if not email_code or email_code.kod != payload.code:
        raise HTTPException(status_code=400, detail="invalid code.")
        
    if email_code.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="code has expired.")
        
    # mark code as used
    email_code.used = True
    
    # set the password and mark user as verified
    user.password_hash = hash_password(payload.password)
    user.zweryfikowany = True
    db.commit()
    
    return {"status": "success", "message": "account created and verified successfully"}


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