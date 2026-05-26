# SentiTrade-AI: The Agentic Finance & Strategy Assistant 🧠🌐

**Market Narratives, Autonomously Analyzed. Executed at the Speed of AI.**

Most platforms provide data and expect you to figure out the rest. SentiTrade-AI is built differently. It stands at the intersection of **AI x Web3**, acting as a real agentic finance application that transforms raw blockchain data into actionable intelligence. 

Moving beyond traditional dashboards, this platform serves as your personal **research terminal, strategy assistant, and automated trading tool**. By integrating the SoSoValue ecosystem with AI-driven insights, it empowers the **One-Person economy** to make confident decisions, discover opportunities, and automate workflows from insight to execution.

## 📖 Overview

SentiTrade-AI continuously monitors structured crypto news and market data, uses a large language model to extract sentiment and narrative strength, and safely executes trades on the SoDEX orderbook. It includes:

At the heart of SentiTrade-AI lies the **ValueChain**—a seamless ecosystem where data flows efficiently across decentralized systems. This agent goes beyond traditional limitations:
- **Agentic Analysis:** Continuously monitors structured crypto news and market data from the SoSoValue terminal, autonomously analyzing sentiment and narrative strength.
- **ValueChain Integration:** Real-time, transparent data flow handling, unlocking deeper insights in the digital economy.
- **SoDEX Routing:** Executes trades on the SoDEX orderbook, pushing boundaries by blending decentralized execution with intelligent AI routing.
- **One-Person Empowerment:** A Web Dashboard and Telegram Bot providing institutional-level research and autonomous execution for individual operators.
- **Premium Signal Subscriptions:** Monetized access to high-confidence trade signals, gated via monthly subscription logic, allowing creators to generate recurring revenue.

## 📖 Core Value & Architecture

We deliver **real user value** by emphasizing complete workflows:
- **AI Integration (Insight & Discovery):** Continuously monitors the SoSoValue terminal, autonomously analyzing sentiment and narrative strength to discover hidden market opportunities.
- **Risk Management at the Core:** Built-in 24h volatility guards and historical backtesting metrics ensure that capital is protected before routing any signal.
- **Complete Workflows (Insight to Execution):** Seamlessly handles real-time data from the ValueChain, translates it into high-confidence signals, and executes securely on the SoDEX orderbook with a single click.
- **Working Demos for Solo Builders:** A fully functional Web Dashboard and Telegram Bot providing institutional-level research and autonomous execution for individual operators.

## 🎯 Target Users & Business Model

Solo crypto traders, small funds, and DeFi enthusiasts who need an intelligent strategy assistant rather than just another data feed.

**Monetization:** Operates as a SaaS via Telegram, charging users a monthly subscription fee to access real-time AI signal alerts and 1-click SoDEX routing.

## 🔁 Complete Agentic Workflow 

1. **Insight Generation** – Fetch curated news and live prices from the SoSoValue API.
2. **AI Strategy Assistant** – Groq-powered LLMs classify sentiment and narrative tags autonomously.
3. **Risk Management** – Filters signals against user-defined volatility thresholds.
4. **On-Chain Execution** – Agent routes and places buy/sell orders securely on SoDEX.
5. **Continuous Learning** – Stores analytics and PnL back into the ValueChain for historical backtesting.

## 🧩 APIs & Infrastructure

| Component          | Endpoint / Usage                            |
|--------------------|---------------------------------------------|
| SoSoValue API      | `GET /v1/news/list` – ValueChain data feed  |
| SoSoValue API      | `GET /v1/coins/market-data` – Analytics     |
| SoDEX API          | `POST /order` – Intelligent trade routing   |
| AI Model           | Groq (Agentic processing)                   |

## 🏗️ Tech Stack

- **Backend:** Python 3.11+, FastAPI
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
Copy `.env.example` to `.env` and configure your API keys.

### 3. Run the Ecosystem
```bash
uvicorn main:app --host 0.0000 --port 8000 --reload
ngrok http 8000
```
- This starts the API server, background worker, Redis, and PostgreSQL.
- Set up your webhook at `https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<NGROK_URL>/webhook`

### 4. Access the dashboard
Interact with the agent via Telegram at `t.me/SentiTradeAIBot`.

## 🧪 Wave Progress & Step-by-Step Build
- Wave 1 (Concept & Strategy): Defined user flows, data schema, AI prompt design, and SoSoValue API integration plan.
- Wave 2 (Insight Integration): Implemented core sentiment engine using Groq, SoSoValue API connector, and working prototype dashboard.
- Wave 3 (Execution & Polish): Built complete workflows from insight to execution, refined risk controls (volatility guards), Telegram bot addition, and stress testing the SoDEX routing.

## 🛡️ Disclaimer
SentiTrade-AI is an experimental agentic system. The future of finance is intelligent, decentralized, and user-driven. Always test on testnet first.

## 👥 Team
- Gaurav Karakoti – Full-stack & AI (Telegram: [@GauravKarakoti](https://t.me/GauravKarakoti))
