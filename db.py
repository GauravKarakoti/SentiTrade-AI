import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, BigInteger, Boolean, Integer, DateTime, Float, Text, text
from datetime import datetime

load_dotenv()

DATABASE_URL = (
    os.getenv("DATABASE_URL", "")
    .replace("postgresql://", "postgresql+asyncpg://")
    .replace("sslmode=require", "ssl=require")
)

if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL is not set in the .env file.")

SODEX_BUILDER_CODE = os.getenv("SODEX_BUILDER_CODE", "SENTITRADE")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    chat_id = Column(BigInteger, primary_key=True, index=True)

    # Maps Telegram users to EVM addresses for Vault Governance & SoDEX Execution
    wallet_address = Column(String(42), nullable=True, index=True)

    is_active = Column(Boolean, default=True)
    is_subscribed = Column(Boolean, default=False)
    subscription_end = Column(DateTime, nullable=True)
    volatility_guard_threshold = Column(Integer, default=15)

    # --- WAVE 3 BUILDER RACE: User Growth & Builder Fee Attribution ---
    builder_code = Column(String(32), default=SODEX_BUILDER_CODE)
    referred_by = Column(BigInteger, nullable=True, index=True)
    trades_count = Column(Integer, default=0)
    total_volume_usd = Column(Float, default=0.0)
    builder_fees_generated = Column(Float, default=0.0)


class ValueChainAnalytics(Base):
    __tablename__ = "valuechain_analytics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    asset = Column(String, index=True)
    sentiment = Column(String)
    confidence = Column(Integer)
    rationale = Column(String)
    source_article = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    sodex_routed = Column(Boolean, default=False)

    # Backtesting & False-Signal Tracking
    entry_price = Column(Float, nullable=True)
    forward_price_change = Column(Float, nullable=True)
    pnl_percentage = Column(Float, nullable=True)
    signal_accuracy = Column(Boolean, nullable=True)

    # --- WAVE 3 BUILDER RACE: SoDEX Builder Code & Revenue Telemetry ---
    builder_code = Column(String(32), default=SODEX_BUILDER_CODE)
    trade_volume_usd = Column(Float, default=0.0)
    builder_fee_usd = Column(Float, default=0.0)
    order_id = Column(String(64), nullable=True)


class BuilderFeeLedger(Base):
    """Tracks every real user trade & Builder Fee generated via SoDEX Builder Codes."""
    __tablename__ = "builder_fee_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=True, index=True)
    wallet_address = Column(String(42), nullable=True, index=True)
    asset = Column(String(32), index=True)
    action = Column(String(16))
    execution_venue = Column(String(32), default="SoDEX")  # "SoDEX" or "SentiTradeVault"
    builder_code = Column(String(32), default=SODEX_BUILDER_CODE, index=True)
    fee_bps = Column(Integer, default=10)
    volume_usd = Column(Float, default=0.0)
    builder_fee_usd = Column(Float, default=0.0)
    reference_id = Column(String(128), nullable=True)  # SoDEX orderID or Base/ValueChain tx_hash
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class AgentEquitySnapshot(Base):
    __tablename__ = "agent_equity_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    simulated_equity = Column(Float, default=1000.0)


class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe non-destructive schema upgrades for existing PostgreSQL deployments
        migration_statements = [
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS builder_code VARCHAR(32) DEFAULT '{SODEX_BUILDER_CODE}'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS trades_count INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS total_volume_usd FLOAT DEFAULT 0.0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS builder_fees_generated FLOAT DEFAULT 0.0",
            f"ALTER TABLE valuechain_analytics ADD COLUMN IF NOT EXISTS builder_code VARCHAR(32) DEFAULT '{SODEX_BUILDER_CODE}'",
            "ALTER TABLE valuechain_analytics ADD COLUMN IF NOT EXISTS trade_volume_usd FLOAT DEFAULT 0.0",
            "ALTER TABLE valuechain_analytics ADD COLUMN IF NOT EXISTS builder_fee_usd FLOAT DEFAULT 0.0",
            "ALTER TABLE valuechain_analytics ADD COLUMN IF NOT EXISTS order_id VARCHAR(64)",
        ]
        for stmt in migration_statements:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session