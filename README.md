# SentiTrade AI 🧠📈

**Market Narratives, Automated. Trades at the Speed of AI.**

An autonomous AI trading agent that turns SoSoValue financial news into on-chain trades on SoDEX – built for the “one-person business empire” era of agentic finance.

## 📖 Overview

SentiTrade AI continuously monitors structured crypto news and market data from the SoSoValue terminal, uses a large language model to extract sentiment and narrative strength, and automatically executes trades on the SoDEX orderbook. It includes:

- A real-time **Sentiment Analysis Engine** powered by GPT-4o.
- A **Signal Generator** that converts narrative conviction into trade signals.
- A **Risk Management Module** with volatility checks, position sizing, and circuit breakers.
- An **Execution Layer** that submits orders to SoDEX on ValueChain.
- A **Web Dashboard** and **Telegram Bot** for monitoring and interaction.

## 🎯 Target Users

Solo crypto traders, small funds, and DeFi enthusiasts who want institutional-level research and execution without a full operations team.

## 🔁 Core Workflow (Data → Action)

1. **Data Input** – Fetch curated news and live prices from SoSoValue API.
2. **AI Analysis** – LLM classify sentiment, confidence, and narrative tags.
3. **Signal Generation** – Rule engine blends sentiment with price movement to produce a trade signal.
4. **Risk Check** – Validate signal against position limits, volatility, and daily trade caps.
5. **Execution** – Place buy/sell orders on SoDEX via ValueChain.
6. **Logging & Feedback** – Store trade history, update dashboard, send Telegram alert.

## 🧩 APIs & Data Sources

| Component          | Endpoint / Usage                            |
|--------------------|---------------------------------------------|
| SoSoValue API      | `GET /v1/news/list` – financial news feed  |
| SoSoValue API      | `GET /v1/coins/market-data` – price, vol.  |
| SoSoValue API      | `GET /v1/categories` – sector tags          |
| SoDEX API          | `POST /order` – limit/market orders         |
| SoDEX API          | `GET /orderbook` – liquidity checks         |
| OpenAI             | GPT-4o (sentiment & rationale generation)   |

## 🏗️ Tech Stack

- **Backend:** Python 3.11, FastAPI, Celery (for scheduling)
- **AI:** OpenAI GPT-4o, LangChain (optional prompt chaining)
- **Blockchain:** Web3.py, ValueChain RPC (EVM-compatible)
- **Database:** PostgreSQL (trades, signals), Redis (cache & dedup)
- **Frontend:** Next.js 14, Tailwind CSS, Recharts
- **Bot:** Telegram Bot API (python-telegram-bot)
- **DevOps:** Docker, docker-compose

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/GauravKarakoti/sentitrade-ai.git
cd sentitrade-ai
```

### 2. Environment variables
Copy `.env.example` to `.env` and fill in:
```text
SOSOVALUE_API_KEY=your_key
SODEX_PRIVATE_KEY=your_wallet_private_key
SODEX_RPC_URL=https://rpc.valuechain.com
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql://user:pass@db:5432/sentitrade
```

### 3. Run with Docker
```bash
docker-compose up -d
```
This starts the API server, background worker, Redis, and PostgreSQL.

### 4. Access the dashboard
Open `http://localhost:3000` to view the real-time dashboard.
Interact with the agent via Telegram at `t.me/SentiTradeBot`.

## 🤖 Agent Configuration
The agent’s behaviour is controlled via `config/strategy.yaml`:
- `min_confidence_threshold`: minimum sentiment score to generate a signal (default: 80)
- `max_position_pct`: max portfolio allocation per asset (0.1 = 10%)
- `daily_trade_limit`: max number of trades per 24h
- `volatility_circuit_breaker`: ATR multiplier to halt trading

## 🧪 Wave Progress
- Wave 1 (Concept): Defined user flows, data schema, AI prompt design, and SoSoValue API integration plan.
- Wave 2 (Build): Implemented core sentiment engine, SoSoValue API connector, SoDEX execution module, and working prototype dashboard.
- Wave 3 (Build): Refined risk controls, UX polish, Telegram bot addition, stress testing, and final submission.

## 🛡️ Risk Disclaimer
SentiTrade AI is experimental software. Automated trading involves substantial risk of loss. The output signals are not financial advice. Always test on testnet first.

## 👥 Team
- Gaurav Karakoti – Full-stack & AI (Telegram: [@GauravKarakoti](https://t.me/GauravKarakoti))
