# SentiTrade-AI: Autonomous On-Chain Finance Business & Strategy Engine 🧠🌐

**A Proud Submission for the SoSoValue Buildathon — Wave 3 Builder Race**  
`#SoSoValue` `#ValueChain` `#SoDEX` `#Buildathon` `#BuilderRace`

**From Ideas to Demos. From Building Products to Going to Market.**

SentiTrade-AI stands at the intersection of **AI × Web3** to deliver a complete, revenue-generating **"research-to-execution"** on-chain finance business. Powered by **SoSoValue APIs**, **ValueChain**, **SoDEX Builder Codes**, and **ERC-4626 Tokenized SSI Index Vaults**, SentiTrade-AI transforms real-time market narratives into verified trades that generate recurring **SoDEX Builder Fee revenue** alongside premium subscriptions and vault management fees.

---

## 💰 Wave 3 Builder Race: Sustainable On-Chain Business Model

In Wave 3, SentiTrade-AI goes beyond a standalone demo to operate as a sustainable on-chain business with three integrated revenue and user-acquisition engines:

1. **SoDEX Builder Codes & Builder Fee Revenue (`SODEX_BUILDER_CODE=SENTITRADE`):**
   - Every token trade routed through the SentiTrade Telegram MiniApp and SoDEX Spot API (`POST /trade/orders/batch`) embeds our **SoDEX Builder Code** (`SENTITRADE`) in both the signed order payload and HTTP headers (`X-SoDEX-Builder-Code`).
   - Every executed order attributes trading volume to SentiTrade-AI and earns **10 bps (0.10%) Builder Fees** recorded in our PostgreSQL `BuilderFeeLedger`.
2. **On-Chain SSI Vault Builder Fees (`SentiTradeVault.sol`):**
   - Sector-wide macro signals route capital into SoSoValue SSI Index tokens (`$MAG7.ssi`, `$DEFI.ssi`, `$MEME.ssi`) via our `vSENTI` ERC-4626 Vault, collecting a transparent 10 bps on-chain Builder Fee on every rebalance.
3. **Real User Growth & Referral Loop (`/start ref_<chat_id>` & `/builder`):**
   - Built-in Telegram referral links and a freemium-to-premium funnel (`0.005 ETH/month` on Base) incentivize traders to onboard friends and execute gasless trades on **ValueChain**.

---

## 📖 Overview

At the heart of SentiTrade-AI lies the **ValueChain**—an end-to-end execution pipeline where curated intelligence converts directly into attributed on-chain volume:
- **Agentic Analysis:** Continuously monitors structured crypto news and market data from the SoSoValue terminal, autonomously scoring sentiment and narrative strength using Groq (`llama-3.3-70b-versatile`).
- **Dual-Routing Architecture:** Automatically distinguishes between macro **SECTOR** rotations (routed to `$MAG7.ssi`, `$DEFI.ssi`, `$MEME.ssi` via the `vSENTI` ERC-4626 Vault) and single **TOKEN** catalysts (routed directly to the **SoDEX** orderbook with our Builder Code).
- **Live Builder Revenue Telemetry:** Real-time dashboard and `/builder` bot command tracking active users, attributed SoDEX volume, and cumulative Builder Fee revenue.

---

## 🏆 SoSoValue Buildathon Wave 3 Alignment

- **Bringing in Real Users:** Frictionless Telegram onboarding (`/start`), viral referral tracking (`?start=ref_<id>`), and 1-click MiniApp wallet signing.
- **Generating Builder Fee Revenue:** Native integration of **SoDEX Builder Codes** across spot batch orders and on-chain vault rebalances, backed by the `BuilderFeeLedger` database table and `/api/builder-race` endpoint.
- **Structured Financial Intelligence:** Uses Redis token-bucket rate limiting and Upstash batch deduplication (`MGET`) to ingest live SoSoValue news and market snapshots.
- **On-Chain Index Infrastructure:** Shareholder-gated (`vSENTI`) ERC-4626 vault rebalancing across `$MAG7.ssi`, `$DEFI.ssi`, and `$MEME.ssi`.

---

## 🔁 Complete Research-to-Revenue Workflow

1. **Insight Generation** – Fetch curated news and live prices via the SoSoValue API with Redis token-bucket rate limiting.
2. **AI Strategy Assistant** – Groq LLM classifies sentiment into `SECTOR` (SSI Index) or `TOKEN` (SoDEX Spot) setups with >85% confidence gating.
3. **Risk Management** – Filters signals against each user's personalized 24h volatility guard threshold (`/volatility`).
4. **Builder-Tagged Execution** – Prepares Keccak-hashed SoDEX order payloads tagged with `builderCode: "SENTITRADE"` for 1-click user signing on ValueChain (`chainId: 286623`).
5. **Revenue & Quant Attribution** – Logs Builder Fees earned (`builder_fee_ledger`) and backfills 1-hour forward PnL for live Sharpe Ratio, Profit Factor, and Win Rate verification.

---

## 🧩 APIs & Infrastructure

| Component | Endpoint / Usage |
| :--- | :--- |
| **SoSoValue News API** | `GET /v1/news` – Curated ValueChain macro & sector news feed |
| **SoSoValue Market API** | `GET /v1/currencies/{id}/market-snapshot` – Real-time price & 24h volatility |
| **SoDEX Spot API** | `POST /api/v1/spot/trade/orders/batch` – Builder-Code-tagged order execution |
| **Builder Race Telemetry** | `GET /api/builder-race` – Real users, attributed volume & Builder Fee ledger |
| **ERC-4626 Vault Node** | `POST /api/execute-rebalance` – Shareholder-gated SSI rebalance with Builder Fee |

---

## 🏗️ Tech Stack

- **Backend:** Python 3.11+, FastAPI, Async SQLAlchemy, Tenacity
- **AI Engine:** Groq (`llama-3.3-70b-versatile`) with strict Pydantic schema validation
- **Blockchain & Execution:** SoSoValue API, ValueChain, SoDEX (Builder Codes), Base (ERC-4626 `SentiTradeVault.sol`, Ethers.js v6)
- **Database & Caching:** PostgreSQL (`users`, `valuechain_analytics`, `builder_fee_ledger`), Upstash Redis (Lua token bucket & `MGET` deduplication)
- **Frontend & Bot:** React + Vite + Tailwind CSS Dashboard, Telegram Bot API & WebApp MiniApp

---

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
* **Wave 1 (Concept & Strategy)**: Defined user flows, structured financial intelligence schema, AI prompt design, and API integration plans.
* **Wave 2 (Prototype & Vault MVP)**: Implemented core sentiment engine, SoSoValue API connector, ERC-4626 `vSENTI` Vault, and discovery dashboard.
* **Wave 3 (Builder Race — Go-To-Market & Revenue Engine)**: Integrated **SoDEX Builder Codes**, launched the `BuilderFeeLedger` revenue tracker, added on-chain vault Builder Fee collection, built viral Telegram referral onboarding, and deployed live commercial KPI telemetry.

## 🛡️ Disclaimer
SentiTrade-AI is an experimental agentic system. The future of finance is intelligent, decentralized, and user-driven. Always test on testnet first.

## 👥 Team
- Gaurav Karakoti – Full-stack & AI (Telegram: [@GauravKarakoti](https://t.me/GauravKarakoti))
