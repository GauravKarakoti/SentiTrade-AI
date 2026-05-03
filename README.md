# SentiTrade-AI: The Agentic Gateway to Intelligent Finance 🧠🌐

**Market Narratives, Autonomously Analyzed. Executed at the Speed of AI.**

SoSoValue is redefining how we interact with financial data in the Web3 era. SentiTrade-AI stands at the intersection of **AI x Web3**, acting as an intelligent agentic system that transforms raw blockchain data into actionable intelligence. By integrating decentralized exchange capabilities with AI-driven insights, this platform empowers the **One-Person economy** to build, scale, and navigate on-chain finance with precision.

## 📖 Overview

SentiTrade AI continuously monitors structured crypto news and market data from the SoSoValue terminal, uses a large language model to extract sentiment and narrative strength, and automatically executes trades on the SoDEX orderbook. It includes:

At the heart of SentiTrade-AI lies the **ValueChain**—a seamless ecosystem where data flows efficiently across decentralized systems. This agent goes beyond traditional limitations:
- **Agentic Analysis:** Continuously monitors structured crypto news and market data from the SoSoValue terminal, autonomously analyzing sentiment and narrative strength.
- **ValueChain Integration:** Real-time, transparent data flow handling, unlocking deeper insights in the digital economy.
- **SoDEX Routing:** Executes trades on the SoDEX orderbook, pushing boundaries by blending decentralized execution with intelligent AI routing.
- **One-Person Empowerment:** A Web Dashboard and Telegram Bot providing institutional-level research and autonomous execution for individual operators.
- **Premium Signal Subscriptions:** Monetized access to high-confidence trade signals, gated via monthly subscription logic, allowing creators to generate recurring revenue.

## 🎯 Target Users & Business Model

Solo crypto traders, small funds, and DeFi enthusiasts. 

**Monetization:** Operates as a SaaS via Telegram, charging users a monthly subscription fee (in crypto or fiat) to access real-time AI signal alerts and 1-click SoDEX routing.

## 🔁 Core Agentic Workflow 

1. **ValueChain Data Input** – Fetch curated news and live prices from the SoSoValue API.
2. **Autonomous AI Engine** – LLMs act, analyze, and assist by classifying sentiment and narrative tags autonomously.
3. **Actionable Intelligence** – Translates narrative conviction into high-confidence SoDEX trade signals.
4. **On-Chain Execution** – Agent routes and places buy/sell orders securely on SoDEX.
5. **Continuous Learning** – Stores analytics back into the ValueChain for future reference.

## 🧩 APIs & Infrastructure

| Component          | Endpoint / Usage                            |
|--------------------|---------------------------------------------|
| SoSoValue API      | `GET /v1/news/list` – ValueChain data feed  |
| SoSoValue API      | `GET /v1/coins/market-data` – Analytics     |
| SoDEX API          | `POST /order` – Intelligent trade routing   |
| AI Model           | Groq / Llama 3.3 (Agentic processing)       |

## 🏗️ Tech Stack

- **Backend:** Python 3.14, FastAPI
- **AI:** Groq
- **Blockchain:** SoSoValue, SoDEX
- **Database:** PostgreSQL (trades, signals)
- **MiniApp:** HTML/CSS + JavaScript
- **Bot:** Telegram Bot API (python-telegram-bot)

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/GauravKarakoti/sentitrade-ai.git
cd sentitrade-ai
```

### 2. Environment variables
Copy `.env.example` to `.env` and fill in:
```text
SOSOVALUE_API_KEY=your_soso_key
GROQ_API_KEY=your_groq_key
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/sentitrade
MINI_APP_URL=[https://your-domain.com](https://your-domain.com)
SODEX_SPOT_API=[https://mainnet-gw.sodex.dev/api/v1/spot](https://mainnet-gw.sodex.dev/api/v1/spot)
```

### 3. Run the Ecosystem
```bash
uvicorn main:app --host 0.0000 --port 8000 --reload
```
This starts the API server, background worker, Redis, and PostgreSQL.

### 4. Access the dashboard
Interact with the agent via Telegram at `t.me/SentiTradeAIBot`.

## 🧪 Wave Progress
- Wave 1 (Concept): Defined user flows, data schema, AI prompt design, and SoSoValue API integration plan.
- Wave 2 (Build): Implemented core sentiment engine, SoSoValue API connector, SoDEX execution module, and working prototype dashboard.
- Wave 3 (Build): Refined risk controls, UX polish, Telegram bot addition, stress testing, and final submission.

## 🛡️ Disclaimer
SentiTrade-AI is an experimental agentic system. The future of finance is intelligent, decentralized, and user-driven. Always test on testnet first.

## 👥 Team
- Gaurav Karakoti – Full-stack & AI (Telegram: [@GauravKarakoti](https://t.me/GauravKarakoti))
