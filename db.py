import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, BigInteger, Boolean, Integer, DateTime
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://").replace("sslmode=require", "ssl=require")

if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL is not set in the .env file.")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    chat_id = Column(BigInteger, primary_key=True, index=True)
    is_active = Column(Boolean, default=True)
    is_subscribed = Column(Boolean, default=False) 
    subscription_end = Column(DateTime, nullable=True)

class NewsCache(Base):
    __tablename__ = "news_cache"
    news_id = Column(String, primary_key=True, index=True)

# NEW: ValueChain tracking for the Agentic System
class ValueChainAnalytics(Base):
    __tablename__ = "valuechain_analytics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset = Column(String, index=True)
    sentiment = Column(String)
    confidence = Column(Integer)
    rationale = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sodex_routed = Column(Boolean, default=False)

async def init_db():
    """Creates tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Dependency for FastAPI to get DB sessions."""
    async with AsyncSessionLocal() as session:
        yield session