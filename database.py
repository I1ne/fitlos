from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:./fitness.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    yclients_id = Column(Integer, unique=True, index=True)   # ID из CRM
    name = Column(String)
    phone = Column(String)
    email = Column(String)
    is_resident = Column(Boolean, default=False)   # резидент ЖК
    churn_risk = Column(Float, default=0.0)        # риск оттока 0..1
    last_visit = Column(DateTime)
    created_at = Column(DateTime)

class ChatLog(Base):
    __tablename__ = "chat_logs"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, index=True)       # ссылка на Client.id
    source = Column(String)                       # "MAX" или "Telegram"
    message = Column(Text)
    is_from_client = Column(Boolean, default=True)
    timestamp = Column(DateTime)
    ai_summary = Column(Text, nullable=True)      # сжатое содержание

# Создать таблицы (при первом запуске)
Base.metadata.create_all(bind=engine)