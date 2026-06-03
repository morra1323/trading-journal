from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=func.now())


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    exchange_trade_id = Column(String, index=True)
    exchange = Column(String)
    symbol = Column(String)
    direction = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float)
    size = Column(Float)
    pnl = Column(Float)
    pnl_percent = Column(Float)
    fee = Column(Float, default=0)
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    strategy = Column(String, nullable=True)
    session = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    mood = Column(String, nullable=True)  # уверен / тревожно / скучно / жадность / страх
    mood_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())


class ExchangeAccount(Base):
    __tablename__ = "exchange_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String)
    exchange = Column(String)
    api_key = Column(String)
    api_secret = Column(String)
    is_active = Column(Integer, default=1)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
