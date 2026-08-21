import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.jwt_utils import decode_token
from backend.database import get_db
from backend.models import BlacklistedToken, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nie udało się zweryfikować danych logowania",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if db.query(BlacklistedToken).filter(BlacklistedToken.token == token).first():
        raise credentials_exception

    try:
        payload = decode_token(token)
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token wygasł, zaloguj się ponownie",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception

    stmt = select(User).where(User.email == email)
    user = db.execute(stmt).scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not user.zweryfikowany:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konto niezweryfikowane — sprawdź maila",
        )
    return user
