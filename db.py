import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, BigInteger, Boolean

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

class NewsCache(Base):
    __tablename__ = "news_cache"
    news_id = Column(String, primary_key=True, index=True)

async def init_db():
    """Creates tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Dependency for FastAPI to get DB sessions."""
    async with AsyncSessionLocal() as session:
        yield session