from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pydantic import BaseModel, EmailStr
from typing import List

# --- SQLALCHEMY VERİTABANI BAĞLANTISI ---
# Veritabanı proje kök dizininde arkafon.db olarak oluşacak
SQLALCHEMY_DATABASE_URL = "sqlite:///./arkafon.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={
                       "check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- VERİTABANI TABLOLARI (MODELS) ---


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
    name = Column(String)  # <--- İŞTE EKSİK OLAN VE ÇÖKMEYE NEDEN OLAN SATIR
    owner = relationship("User", back_populates="portfolios")
    items = relationship(
        "PortfolioItem", back_populates="portfolio", cascade="all, delete")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"))
    fund_code = Column(String, index=True)
    portfolio = relationship("Portfolio", back_populates="items")


# Tabloları oluştur (Eğer yoksa)
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- PYDANTIC ŞEMALARI (API Girdi/Çıktı Kontrolü) ---


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
