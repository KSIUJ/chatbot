from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from backend.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    zweryfikowany = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)