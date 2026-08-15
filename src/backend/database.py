from __future__ import annotations

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Conversation, Message, MessageRole, User

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
    """Email nie konczy sie na @uj.edu.pl"""


class EmailAlreadyRegisteredError(Exception):
    """Ktos juz ma konto na ten email"""


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
) -> User:
    """Zaklada konto. Rzuca EmailNotAllowedError / EmailAlreadyRegisteredError
    jesli cos jest nie tak"""
    if not is_allowed_email(email):
        raise EmailNotAllowedError(f"Email {email!r} nie jest z domeny uj.edu.pl")

    if get_user_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError(f"Konto dla {email!r} juz istnieje")

    user = User(
        email=email.strip().lower(),
        username=username,
        password_hash=hash_password(password) if password else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # zeby user.id/created_at byly uzupelnione wartosciami z bazy
    return user


def get_user(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email.strip().lower())
    return db.execute(stmt).scalar_one_or_none()


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