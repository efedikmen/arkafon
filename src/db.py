import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Float, Date
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pydantic import BaseModel, EmailStr
from typing import List, Optional

# DB URL is env-driven so we can swap SQLite -> Postgres in deployment.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "ARKAFON_DATABASE_URL", "sqlite:///./arkafon.db")

_engine_kwargs = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    portfolios = relationship("Portfolio", back_populates="owner")


class Portfolio(Base):
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, default="Ana Sepetim")
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="portfolios")
    items = relationship(
        "PortfolioItem", back_populates="portfolio", cascade="all, delete")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"))
    fund_code = Column(String, index=True)
    # Per-lot acquisition data (PR4 introduces these from the FE).
    acquired_at = Column(Date, nullable=True)
    acquisition_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    portfolio = relationship("Portfolio", back_populates="items")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class BasketUpdate(BaseModel):
    funds: List[str]
    name: Optional[str] = None
