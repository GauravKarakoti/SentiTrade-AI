# SentiTrade-AI: The Agentic Finance & Strategy Assistant 🧠🌐

**A Proud Submission for the SoSoValue Buildathon**

**Market Narratives, Autonomously Analyzed. Executed at the Speed of AI.**

The vision of enabling a single builder to create a complete financial research platform, strategy assistant, and automated trading service is what makes the **SoSoValue Buildathon** so exciting. SentiTrade-AI stands at the intersection of AI x Web3 to deliver exactly that: a complete **"research-to-execution"** ecosystem. 

Moving beyond traditional dashboards, SentiTrade-AI transforms raw blockchain data into actionable intelligence, empowering the One-Person economy with institutional-grade quant workflows and trading automation.

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

## 🏆 SoSoValue Buildathon Alignment

SentiTrade-AI is built to fully utilize the SoSoValue ecosystem, directly addressing the Buildathon's core pillars:

* **Structured Financial Intelligence:** Continuously monitors curated crypto news and live market snapshots from the SoSoValue terminal API.
* **On-Chain Index Infrastructure:** Our AI agent natively understands SoSoValue Narrative Indices. It autonomously routes sector-wide narrative signals to tokens like `$MAG7.ssi`, `$MEME.ssi`, and `$USSI` for passive index investing.
* **High-Performance Trading Execution Tools:** Provides 1-click, gasless off-chain signature execution directly on the **SoDEX** orderbook.
* **AI-Friendly Workflows for Agentic Finance:** Uses Groq-powered LLMs to safely translate natural language market narratives into strictly typed, JSON-formatted trading actions and confidence scores.

## ✨ Core Focus Areas & User Value

We built this project by strictly focusing on the following criteria:
* ✅ **Real User Value:** Gives solo crypto traders, small funds, and DeFi enthusiasts a monetizable strategy assistant instead of just another data feed.
* ✅ **Clear Workflow Design:** A seamless pipeline: Insight Generation ➡️ AI Strategy ➡️ Volatility Risk Management ➡️ On-Chain Execution ➡️ Historical Backtesting.
* ✅ **AI-Enhanced Financial Applications:** Operates fully autonomously to classify sentiment and generate risk-adjusted confidence scores.
* ✅ **Opportunity Discovery & Signal Generation:** Uncovers hidden market opportunities in real-time and pushes alerts via Telegram.
* ✅ **Practical Execution Infrastructure through SoDEX:** Secure, intelligent trade routing that links directly to a user's Web3 wallet.

## 🎯 Target Users & Capabilities
Designed for builders and operators interested in:
* **Crypto Analytics & Financial Dashboards:** A fully functional Telegram MiniApp UI.
* **Trading Automation & Copy-Trading Tools:** Premium monetized signal subscriptions.
* **Quant Workflows & DeFi Infrastructure:** Built-in historical PnL tracking, win-rate analytics, and 24h volatility risk-guards.

## 🔁 Complete Agentic Workflow 
1. **Insight Generation** – Fetch curated news and live prices via the SoSoValue API.
2. **AI Strategy Assistant** – LLMs classify sentiment and narrative tags autonomously.
3. **Risk Management** – Filters signals against user-defined volatility thresholds.
4. **On-Chain Execution** – Agent prepares payloads and executes securely on SoDEX.
5. **Continuous Learning** – Stores analytics and PnL back into the database for quant backtesting.

## 🧩 APIs & Infrastructure

| Component          | Endpoint / Usage                            |
|--------------------|---------------------------------------------|
| SoSoValue API      | `GET /v1/news/list` – ValueChain data feed  |
| SoSoValue API      | `GET /v1/coins/market-data` – Analytics     |
| SoDEX API          | `POST /order` – Intelligent trade routing   |
| AI Model           | Groq (Agentic processing)                   |

## 🏗️ Tech Stack
- **Backend:** Python 3.11+, FastAPI
- **AI:** Groq (llama-3.3-70b-versatile)
- **Blockchain Infrastructure:** SoSoValue (Data & Index), SoDEX (Execution)
- **Database:** PostgreSQL (trades, signals), Redis (rate limiting & caching)
- **Interfaces:** HTML/CSS/JS (MiniApp) + Telegram Bot API

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
SentiTrade embraces a rapid iteration structure for the Buildathon:
* **Wave 1 (Concept & Strategy):** Defined user flows, structured financial intelligence schema, AI prompt design, and API integration plans.
* **Wave 2 (Prototype):** Implemented core sentiment engine, SoSoValue API connector, and prototype discovery dashboard.
* **Wave 3 (Production-Ready Demo):** Built complete "research-to-execution" workflows, refined risk controls (volatility guards), integrated Telegram bot, and stress-tested high-performance SoDEX routing.

## 🛡️ Disclaimer
SentiTrade-AI is an experimental agentic system. The future of finance is intelligent, decentralized, and user-driven. Always test on testnet first.

## 👥 Team
- Gaurav Karakoti – Full-stack & AI (Telegram: [@GauravKarakoti](https://t.me/GauravKarakoti))
