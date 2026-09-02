from __future__ import annotations

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func

from .models import Base, Conversation, DEFAULT_CONTEXT_COUNT, Message, MessageFeedback, MessageRole, User

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chatbot.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Tworzy wszystkie tabele w bazie, jesli jeszcze nie istnieja"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency dla FastAPI. Uzycie:

        from fastapi import Depends
        from .database import get_db

        @app.post("/chat")
        def chat(payload: ChatRequest, db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Konta / logowanie - na razie tylko maile z domeny uj.edu.pl

ALLOWED_EMAIL_DOMAIN = "uj.edu.pl"


class EmailNotAllowedError(Exception):
    """Email does not end with @uj.edu.pl"""


class EmailAlreadyRegisteredError(Exception):
    """Account with this email already exists"""


def is_allowed_email(email: str) -> bool:
    """Sprawdza czy mail jest z UJ"""
    email = email.strip().lower()
    return email.endswith("@" + ALLOWED_EMAIL_DOMAIN) or email.endswith("." + ALLOWED_EMAIL_DOMAIN)


# hashowanie hasla

import hashlib
import hmac


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, password_hash: str) -> bool:
    salt_hex, digest_hex = password_hash.split("$")
    salt = bytes.fromhex(salt_hex)
    new_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(new_digest.hex(), digest_hex)


# USERS

def create_user(
    db: Session,
    email: str,
    username: str | None = None,
    password: str | None = None,
    context_count: int | None = None,
) -> User:
    """Zaklada konto. Rzuca EmailNotAllowedError / EmailAlreadyRegisteredError
    jesli cos jest nie tak"""
    if not is_allowed_email(email):
        raise EmailNotAllowedError(f"Email {email!r} is not from the uj.edu.pl domain")

    if get_user_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError(f"An account for {email!r} already exists")

    user = User(
        email=email.strip().lower(),
        username=username,
        password_hash=hash_password(password) if password else None,
        context_count=context_count if context_count is not None else DEFAULT_CONTEXT_COUNT,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)

def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email.strip().lower())
    return db.execute(stmt).scalar_one_or_none()

def set_user_context_count(db: Session, user_id: str, context_count: int) -> User:
    """Zmienia liczbe kontekstow wybrana przez uzytkownika"""
    user = get_user(db, user_id)
    if user is None:
        raise KeyError(f"User {user_id} does not exist")

    user.context_count = context_count
    db.commit()
    db.refresh(user)
    return user

def count_users(db: Session) -> int:
    return db.execute(select(func.count()).select_from(User)).scalar_one()

def count_registered_users(db: Session) -> int:
    """Liczba faktycznie zalozonych (zweryfikowanych) kont."""
    stmt = select(func.count()).select_from(User).where(User.zweryfikowany == True)
    return db.execute(stmt).scalar_one()


# CONVERSATIONS

def create_conversation(db: Session, user_id: str | None = None) -> Conversation:
    conversation = Conversation(user_id=user_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: str) -> Conversation | None:
    return db.get(Conversation, conversation_id)


def list_conversations_for_user(db: Session, user_id: str) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())

def count_conversations(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Conversation)).scalar_one()

def count_anonymous_conversations(db: Session) -> int:
    """Liczba konwersacji zaczetych bez logowania (brak user_id)."""
    stmt = select(func.count()).select_from(Conversation).where(Conversation.user_id.is_(None))
    return db.execute(stmt).scalar_one()


# MESSAGES

def add_message(
    db: Session,
    conversation_id: str,
    role: MessageRole,
    content: str,
    sources: list[str] | None = None,
) -> Message:
    conversation = get_conversation(db, conversation_id)
    if conversation is None:
        raise KeyError(f"Konwersacja {conversation_id} nie istnieje")

    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources or [],
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_messages(db: Session, conversation_id: str) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(db.execute(stmt).scalars().all())

def set_message_feedback(db: Session, message_id: str, feedback: MessageFeedback | None) -> Message:
    """Ustawia/kasuje lapke w gore lub w dol na wiadomosci. feedback=None czysci ocene."""
    message = db.get(Message, message_id)
    if message is None:
        raise KeyError(f"Message {message_id} does not exist")

    message.feedback = feedback
    db.commit()
    db.refresh(message)
    return message

def count_prompts(db: Session) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.role == MessageRole.USER)
    return db.execute(stmt).scalar_one()