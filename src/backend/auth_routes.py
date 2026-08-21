from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .auth.dependencies import get_current_user, oauth2_scheme
from .auth.email_utils import generuj_kod, kod_wygasa, wyslij_kod_weryfikacyjny
from .auth.jwt_utils import create_access_token, decode_token
from .database import (
    EmailAlreadyRegisteredError,
    EmailNotAllowedError,
    create_user,
    get_db,
    get_user_by_email,
    hash_password,
    verify_password,
)
from .models import BlacklistedToken, EmailCode, User
from .rate_limit import limiter
from .request import LoginRequest, RegisterRequest, VerifyMailRequest
from .response import AuthMessageResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthMessageResponse)
@limiter.limit("5/hour")
def register(request: Request, dane: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = create_user(db, email=dane.email, password=dane.haslo)
    except EmailNotAllowedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rejestracja tylko dla adresów @uj.edu.pl")
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Konto z tym mailem już istnieje")

    kod = generuj_kod()
    db.add(EmailCode(user_id=user.id, kod=kod, typ="verify", expires_at=kod_wygasa(), used=False))
    db.commit()

    wyslij_kod_weryfikacyjny(user.email, kod)
    return {"detail": "Konto utworzone. Sprawdź maila po kod weryfikacyjny."}


@router.post("/verify-mail", response_model=AuthMessageResponse)
@limiter.limit("10/hour")
def verify_mail(request: Request, dane: VerifyMailRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, dane.email)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono użytkownika")

    kod_rekord = (
        db.query(EmailCode)
        .filter(EmailCode.user_id == user.id, EmailCode.typ == "verify", EmailCode.used == False)
        .order_by(EmailCode.expires_at.desc())
        .first()
    )
    if not kod_rekord or kod_rekord.kod != dane.kod:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nieprawidłowy kod")
    expires_at = kod_rekord.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kod wygasł, poproś o nowy")

    user.zweryfikowany = True
    kod_rekord.used = True
    db.commit()
    return {"detail": "Mail zweryfikowany, możesz się zalogować"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/hour")
def login(request: Request, dane: LoginRequest, db: Session = Depends(get_db)):
    user = get_user_by_email(db, dane.email)
    if not user or not user.password_hash or not verify_password(dane.haslo, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieprawidłowy email lub hasło")
    if not user.zweryfikowany:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Zweryfikuj maila przed zalogowaniem")

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout", response_model=AuthMessageResponse)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    db.add(BlacklistedToken(token=token, expires_at=exp))
    db.commit()
    return {"detail": "Wylogowano"}

