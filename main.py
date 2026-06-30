import os
import httpx
import json
import time
import uuid
import asyncio
import urllib.parse
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from eth_utils import keccak
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, get_db, AsyncSessionLocal, User, ValueChainAnalytics, SystemLog
from bot_logic import (
    build_prompt, analyze_with_llm, generate_signals, 
    send_telegram_alert, generate_chat_reply, 
    calculate_win_rate, calculate_roi, calculate_max_drawdown,
    calculate_profit_factor, calculate_sharpe_ratio
)
from sosovalue_client import (
    fetch_news_from_api, deduplicate_and_categorize, fetch_market_snapshot
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
SODEX_SPOT_API = os.getenv("SODEX_SPOT_API", "https://mainnet-gw.sodex.dev/api/v1/spot")
VAULT_MANAGER_URL = os.getenv("VAULT_MANAGER_URL")
VAULT_ADDRESS = os.getenv("VAULT_ADDRESS")

SSI_CONTRACTS = {
    "MAG7.ssi": "0x9E6A46f294bB67c20F1D1E7AfB0bBEf614403B55",
    "DEFI.ssi": "0x164ffdaE2fe3891714bc2968f1875ca4fA1079D0",
    "MEME.ssi": "0xdd3acDBDc7b358Df453a6CB6bCA56C92aA5743aA",
    "USSI": "0x3a46ed8FCeb6eF1ADA2E4600A522AE7e24D2Ed18"
}

background_tasks = set()

async def background_analysis_loop():
    await log_to_db("System initialized. Agentic background loop started.", "INFO")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await perform_analysis(db)
        except Exception as e:
            print(f"Background Loop Error: {e}")
            await log_to_db(f"Analysis Error: {str(e)}", "ERROR")
        await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(background_analysis_loop())
    background_tasks.add(task)
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def log_to_db(message: str, level: str = "INFO"):
    try:
        async with AsyncSessionLocal() as session:
            session.add(SystemLog(message=message, level=level))
            await session.commit()
    except Exception as e:
        print(f"Failed to write log to DB: {e}")

@app.get("/api/logs")
async def get_system_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SystemLog).order_by(SystemLog.timestamp.desc()).limit(20)
    )
    records = result.scalars().all()
    
    return [
        f"[{r.timestamp.strftime('%H:%M:%S')}] {r.message}"
        for r in reversed(records)
    ]

@app.get("/api/signals")
async def get_recent_signals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ValueChainAnalytics)
        .order_by(ValueChainAnalytics.timestamp.desc())
        .limit(6)
    )
    records = result.scalars().all()
    
    return [
        {
            "time": r.timestamp.strftime("%H:%M:%S") if r.timestamp else "N/A",
            "asset": r.asset,
            "score": r.confidence or 0,
            "sentiment": "Bullish" if r.sentiment == "BUY" else "Bearish" if r.sentiment == "SELL" else "Neutral",
            "action": r.sentiment or "HOLD",
            "status": "Logged"
        }
        for r in records
    ]

@app.get("/api/metrics")
async def get_performance_metrics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ValueChainAnalytics.pnl_percentage)
        .filter(ValueChainAnalytics.signal_accuracy.isnot(None))
        .filter(ValueChainAnalytics.pnl_percentage.isnot(None))
        .order_by(ValueChainAnalytics.timestamp.asc())
    )
    
    raw_pnls = result.scalars().all()
    pnls = [float(pnl) for pnl in raw_pnls if pnl is not None]
    
    equity = 1000.0
    equity_curve = [equity]
    
    for pnl in pnls:
        trade_return = equity * 0.10 * (pnl / 100.0) 
        equity += trade_return
        equity_curve.append(equity)
        
    current_equity = equity_curve[-1] if len(equity_curve) > 1 else 1000.0
    
    return {
        "kpis": {
            "win_rate": calculate_win_rate(pnls),
            "roi": calculate_roi(1000.0, current_equity),
            "max_drawdown": calculate_max_drawdown(equity_curve),
            "profit_factor": calculate_profit_factor(pnls), 
            "sharpe_ratio": calculate_sharpe_ratio(pnls),   
            "total_trades": len(pnls)
        },
        "equity_curve": equity_curve,
        "trade_pnls": pnls 
    }

async def get_historical_performance(db: AsyncSession, asset: str) -> dict:
    result = await db.execute(
        select(ValueChainAnalytics)
        .filter(ValueChainAnalytics.asset == asset)
        .filter(ValueChainAnalytics.signal_accuracy != None)
    )
    records = result.scalars().all()
    
    if not records:
        return {"winRate": "N/A", "avgPnl": "0.0%", "maxDrawdown": "0.0%"}
    
    total = len(records)
    wins = len([r for r in records if r.signal_accuracy is True])
    total_pnl = sum([r.pnl_percentage or 0 for r in records])
    
    return {
        "winRate": f"{int((wins / total) * 100)}%",
        "avgPnl": f"{'+' if (total_pnl / total) >= 0 else ''}{(total_pnl / total):.2f}%",
        "maxDrawdown": f"{min([r.pnl_percentage or 0 for r in records]):.2f}%"
    }

async def backfill_signal_performance(db: AsyncSession):
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    result = await db.execute(
        select(ValueChainAnalytics)
        .filter(ValueChainAnalytics.signal_accuracy == None)
        .filter(ValueChainAnalytics.entry_price != None)
        .filter(ValueChainAnalytics.entry_price > 0)
        .filter(ValueChainAnalytics.timestamp <= one_hour_ago)
    )
    pending_signals = result.scalars().all()
    
    for record in pending_signals:
        try:
            market_data = await fetch_market_snapshot(record.asset)
            current_price = float(market_data.get("price", 0.0))
            if current_price > 0:
                price_change = current_price - record.entry_price
                pnl_pct = (price_change / record.entry_price) * 100
                
                if record.sentiment == "BUY":
                    record.pnl_percentage = pnl_pct
                    record.signal_accuracy = pnl_pct > 0
                else: 
                    record.pnl_percentage = -pnl_pct
                    record.signal_accuracy = pnl_pct < 0
                    
                record.forward_price_change = price_change
        except Exception:
            pass
            
    if pending_signals:
        await db.commit()

async def perform_analysis(db: AsyncSession):
    await backfill_signal_performance(db)

    news_items = await fetch_news_from_api()
    new_news = await deduplicate_and_categorize(news_items)
    if not new_news: 
        return {"status": "no_new_data"}

    await log_to_db(f"Ingested {len(new_news)} new macro updates. Routing to LLM...", "INFO")

    analyses = analyze_with_llm(build_prompt(new_news))
    signals = generate_signals(analyses)
    
    if signals:
        await log_to_db(f"LLM Processing complete. {len(signals)} agentic signals generated.", "INFO")
        result = await db.execute(select(User).filter(User.is_active == True))
        active_users = result.scalars().all()
        
        premium_users = [{"chat_id": u.chat_id, "vol_guard": u.volatility_guard_threshold, "wallet": getattr(u, 'wallet_address', None)} for u in active_users if u.is_subscribed]
        free_users = [{"chat_id": u.chat_id, "vol_guard": u.volatility_guard_threshold, "wallet": getattr(u, 'wallet_address', None)} for u in active_users if not u.is_subscribed]

        for index, signal in enumerate(signals):
            try:
                market_data = await fetch_market_snapshot(signal["asset"])
                entry_price = float(market_data.get("price", 0.0))
                volatility = abs(float(market_data.get("change_pct_24h", 0.0)))
                
                db.add(ValueChainAnalytics(
                    asset=signal["asset"],
                    sentiment=signal["action"],
                    confidence=signal["confidence"],
                    rationale=signal["rationale"],
                    source_article=signal["source_headline"],
                    entry_price=entry_price
                ))
                
                signal["volatility"] = volatility

                target_users = premium_users.copy()
                if index == 0: target_users.extend(free_users)

                for user in target_users:
                    if volatility <= user["vol_guard"]:
                        if signal.get("signal_type") == "SECTOR":
                            if not user.get("wallet"):
                                continue 
                            try:
                                async with httpx.AsyncClient(timeout=10.0) as client:
                                    resp = await client.get(f"{VAULT_MANAGER_URL}/api/vault-balance/{user['wallet']}")
                                    if resp.status_code == 200 and float(resp.json().get("shares", 0)) > 0:
                                        await send_telegram_alert(user["chat_id"], signal, is_sector=True)
                            except Exception as e:
                                print(f"Vault balance check failed: {e}")
                        else:
                            await send_telegram_alert(user["chat_id"], signal, is_sector=False)
                            
            except Exception as e:
                print(f"Skipping signal for {signal['asset']} due to error: {e}")

        if len(signals) > 1:
            with_count = len(signals) - 1
            upsell_msg = f"🔒 **{with_count} more high-confidence signals** were just generated!\n\nUse `/subscribe` to unlock the full ValueChain stream."
            for user in free_users:
                await send_direct_message(user["chat_id"], upsell_msg)
    
    await db.commit()
    return {"status": "success", "agentic_actions_routed": len(signals)}

@app.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        update = await request.json()
    except Exception:
        return {"status": "error"}

    help_message = (
        "📚 **SentiTrade-AI Command Directory**\n\n"
        "🔹 `/start` - Activate the agent and view the onboarding guide.\n"
        "🔹 `/dashboard` - View live agent performance and equity curve.\n"
        "🔹 `/vault` - View the Vault's current allocations and TVL.\n"
        "🔹 `/deposit` - Deposit USDC into the autonomous AI Vault.\n"
        "🔹 `/redeem` - Burn vSENTI to withdraw your USDC from the Vault.\n"
        "🔹 `/portfolio <address>` - Check your vSENTI balance and its current value.\n"
        "🔹 `/volatility <percentage>` - Set your risk guard (e.g., `/volatility 15`).\n"
        "🔹 `/subscribe` - Unlock the premium ValueChain stream.\n"
        "🔹 `/stop` - Take the agent offline.\n\n"
    )

    if "callback_query" in update:
        callback_query = update["callback_query"]
        callback_id = callback_query["id"]
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data.startswith("reject_"):
            await delete_telegram_message(chat_id, message_id)
            await answer_callback_query(callback_id, "Signal discarded.")
            
        elif data.startswith("approve_vault_"):
            parts = data.split("_")
            asset = parts[2]
            formatted_asset = asset if asset.startswith("$") else f"${asset}"
            action = parts[3] if len(parts) > 3 else "BUY"
            confidence = int(parts[4]) if len(parts) > 4 else 85
            
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            caller_address = getattr(user, 'wallet_address', None)
            
            if not caller_address:
                await send_direct_message(chat_id, "❌ **Access Denied:** Please connect your wallet via the `/deposit` or web portal first so we can verify your vSENTI holding.")
                return {"status": "ok"}
                
            await answer_callback_query(callback_id, "Voting to execute vault rebalance...")
            await send_direct_message(
                chat_id, 
                f"⏳ **Authorizing Vault Rebalance...**\nRouting tokenized capital to {formatted_asset}. Awaiting verification on Base."
            )

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{VAULT_MANAGER_URL}/api/execute-rebalance",
                        json={
                            "asset": formatted_asset,
                            "action": action,
                            "confidence": confidence,
                            "callerAddress": caller_address
                        }
                    )
                resp_data = resp.json()
                
                if resp.status_code == 200 and resp_data.get("success"):
                    tx_hash = resp_data.get("tx_hash")
                    explorer_link = f"https://sepolia.basescan.org/tx/{tx_hash}"
                    success_text = (
                        f"✅ **Vault Successfully Rebalanced!**\n\n"
                        f"🪙 **Index Target:** {formatted_asset}\n"
                        f"⚡ **Strategy Action:** {action}\n"
                        f"🔗 [View on Basescan]({explorer_link})"
                    )
                    await send_direct_message(chat_id, success_text)
                else:
                    error_msg = resp_data.get("error", "Unknown execution error node side.")
                    await send_direct_message(chat_id, f"❌ **Smart Contract Execution Failed:**\n`{error_msg}`")
            except httpx.RequestError as e:
                await send_direct_message(chat_id, f"🔌 **Service Error:** Could not reach Vault Execution Node.\nError: `{str(e)}`")

        elif data.startswith("approve_token_"):
            parts = data.split("_")
            asset = parts[2]
            formatted_asset = asset if asset.startswith("$") else f"${asset}"
            action = parts[3] if len(parts) > 3 else "BUY"
            confidence = int(parts[4]) if len(parts) > 4 else 85
            
            await answer_callback_query(callback_id, "Fetching AI Logic...")
            stats = await get_historical_performance(db, formatted_asset)
            
            result = await db.execute(
                select(ValueChainAnalytics.rationale)
                .filter(ValueChainAnalytics.asset == formatted_asset)
                .order_by(ValueChainAnalytics.timestamp.desc())
                .limit(1)
            )
            latest_rationale = result.scalar_one_or_none() or "AI logic applied based on recent news."

            query_params = urllib.parse.urlencode({
                "intent": "connect",
                "asset": formatted_asset,
                "action": action,
                "confidence": str(confidence),
                "winRate": stats["winRate"],
                "avgPnl": stats["avgPnl"],
                "maxDrawdown": stats["maxDrawdown"],
                "rationale": latest_rationale
            })
            
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            keyboard = {"keyboard": [[{"text": "🔗 Review & Connect Wallet", "web_app": {"url": web_app_url}}]], "resize_keyboard": True, "one_time_keyboard": True}
            await send_direct_message(
                chat_id, 
                f"⚡ **Agentic Execution: {formatted_asset}**\n\nReview the AI Logic and historical performance metrics in the Web Console before executing.", 
                reply_markup=keyboard
            )
            
        elif data == "cmd_subscribe":
            await answer_callback_query(callback_id)
            query_params = urllib.parse.urlencode({
                "intent": "subscribe",
                "target": "dev",
                "chain": "base", 
                "chainId": "8453", # Mainnet
                "amount": "0.005"
            })
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            keyboard = {"inline_keyboard": [[{"text": "💎 Pay 0.005 ETH / Month", "web_app": {"url": web_app_url}}]]}
            await send_direct_message(
                chat_id, 
                "⭐️ **Unlock SentiTrade Premium**\n\nPay 0.005 ETH on the Base network to unlock all high-confidence agentic trade signals for 30 days.", 
                reply_markup=keyboard
            )
            
        elif data == "cmd_help":
            await answer_callback_query(callback_id, "Loading help...")
            await send_direct_message(chat_id, help_message)
            
        return {"status": "ok"}

    if "message" in update and "web_app_data" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        
        try:
            web_app_payload = json.loads(update["message"]["web_app_data"]["data"])
            status = web_app_payload.get("status")
            user_address = web_app_payload.get("address")

            if user_address and status in ["deposited", "connected", "subscribed"]:
                result = await db.execute(select(User).filter(User.chat_id == chat_id))
                user = result.scalar_one_or_none()
                if user and status != "subscribed":
                    setattr(user, 'wallet_address', user_address)
                    await db.commit()

            if status == "subscribed":
                tx_hash = web_app_payload.get("tx_hash", "Unknown")
                
                result = await db.execute(select(User).filter(User.chat_id == chat_id))
                user = result.scalar_one_or_none()
                if user:
                    user.is_subscribed = True
                    user.subscription_end = datetime.utcnow() + timedelta(days=30)
                    await db.commit()
                
                explorer_link = f"https://basescan.org/tx/{tx_hash}"
                await send_direct_message(
                    chat_id, 
                    f"🎉 **Premium Activated!**\n\nPayment verified on-chain. You will now receive all agentic ValueChain trade signals for the next 30 days.\n🔗 [View Receipt on Basescan]({explorer_link})"
                )
                return {"status": "ok"}

            elif status == "deposited":
                amount = web_app_payload.get("amount", "0")
                await send_direct_message(chat_id, f"✅ **Deposit Confirmed!**\n\nSuccessfully deposited **{amount} USDC** from `{user_address[:6]}...{user_address[-4:]}` into the SentiTrade Vault.")
                return {"status": "ok"}
            
            elif status == "redeemed":
                amount = web_app_payload.get("amount", "0")
                await send_direct_message(chat_id, f"✅ **Redemption Confirmed!**\n\nSuccessfully burned **{amount} vSENTI** from `{user_address[:6]}...{user_address[-4:]}` and redeemed your USDC.")
                return {"status": "ok"}

            elif status == "connected":
                asset = web_app_payload.get("asset", "Unknown")
                action = web_app_payload.get("action", "BUY")
                confidence = web_app_payload.get("confidence", "80")
                
                await send_direct_message(chat_id, f"⏳ **Analyzing ValueChain...**\nPreparing AI-driven SoDEX order for {asset}.")
                
                try:
                    order_data = await prepare_sodex_order(asset=asset, action=action, address=user_address)
                    sodex_chain_id = 138565 if "testnet" in SODEX_SPOT_API else 286623
                    stats = await get_historical_performance(db, asset)

                    query_params = urllib.parse.urlencode({
                        "intent": "sign_sodex",
                        "hash": order_data["payload_hash"],
                        "nonce": order_data["nonce"],
                        "payload": order_data["compact_json"],
                        "address": user_address,
                        "sodexChainId": sodex_chain_id,
                        "asset": asset,
                        "action": action,
                        "confidence": confidence,
                        "winRate": stats["winRate"],          
                        "avgPnl": stats["avgPnl"],            
                        "maxDrawdown": stats["maxDrawdown"]   
                    })
                    
                    web_app_url = f"{MINI_APP_URL}?{query_params}"
                    keyboard = {"keyboard": [[{"text": f"🔐 Authorize Agentic Trade", "web_app": {"url": web_app_url}}]],"resize_keyboard": True,"one_time_keyboard": True}

                    success_msg = f"✅ **SoSoValue Agent Ready**\nAsset: {asset}\n\n⚠️ **Action Required:**\nSign the payload to authorize execution on the ValueChain."
                    await send_direct_message(chat_id, success_msg, reply_markup=keyboard)
                    
                except Exception as e:
                    await send_direct_message(chat_id, f"❌ **ValueChain Error:** {str(e)}")

            elif status == "sodex_signed":
                signature = web_app_payload.get("signature", "")
                raw_payload = web_app_payload.get("payload")
                original_nonce = str(web_app_payload.get("nonce"))

                typed_sig = signature if signature.startswith("0x01") else ("0x01" + signature[2:] if signature.startswith("0x") else "0x01" + signature)
                
                headers = {"Content-Type": "application/json", "Accept": "application/json", "X-API-Key": user_address, "X-API-Sign": typed_sig, "X-API-Nonce": original_nonce}
                parsed_payload = json.loads(raw_payload)
                request_body = json.dumps(parsed_payload["params"], separators=(',', ':'))

                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{SODEX_SPOT_API}/trade/orders/batch", content=request_body, headers=headers)
                    resp_data = resp.json()
                    
                    if resp.status_code == 200 and resp_data.get("data", [{}])[0].get("code") == 0:
                        order_id = resp_data["data"][0].get("orderID", "Unknown")
                        await send_direct_message(chat_id, f"🎉 **Intelligent Trade Executed!**\nSoDEX Order ID: `{order_id}`\n\n*Welcome to the future of finance.*", reply_markup={"remove_keyboard": True})
                    else:
                        error_detail = resp_data.get("data", [{}])[0].get("error", resp.text)
                        await send_direct_message(chat_id, f"❌ **SoDEX Execution Failed:**\n`{error_detail}`", reply_markup={"remove_keyboard": True})
                        
        except json.JSONDecodeError:
            await send_direct_message(chat_id, "⚠️ Received malformed data from the agent interface.")
            
        return {"status": "ok"}

    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].strip()

        if text == "/start":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if not user:
                db.add(User(chat_id=chat_id, is_active=True))
                await db.commit()
                
            welcome_message = (
                "👋 **Welcome to SentiTrade-AI!**\n\n"
                "I read thousands of crypto news articles and SoSoValue market data so you don't have to.\n\n"
                "When I spot a strong narrative, I score the sentiment and send you clear, actionable trade setups with **explanations you can actually understand**.\n\n"
                "**How it works:**\n"
                "🔍 **Discover:** I scan the ValueChain 24/7.\n"
                "🧠 **Analyze:** I grade sentiment and explain *why*.\n"
                "⚡ **Execute:** You review the logic and execute gasless trades via SoDEX.\n\n"
                "👇 **Tap below to unlock your premium AI feed!**"
            )
            
            keyboard = {"inline_keyboard": [[{"text": "🔓 Subscribe to AI Signals", "callback_data": "cmd_subscribe"}],[{"text": "⚙️ Help & Settings", "callback_data": "cmd_help"}]]}
            await send_direct_message(chat_id, welcome_message, reply_markup=keyboard)
            if user:
                user.is_active = True
                await db.commit()
        
        elif text == "/help":
            await send_direct_message(chat_id, help_message)
            
        elif text == "/dashboard":
            web_app_url = f"{MINI_APP_URL}?intent=dashboard"
            frontend_url = "https://senti-trade-ai-pi.vercel.app"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📱 Open Mini App", "web_app": {"url": web_app_url}}],
                    [{"text": "🌐 Open in Web Browser", "url": frontend_url}]
                ]
            }

            await send_direct_message(
                chat_id, 
                "📈 **SentiTrade-AI Performance Dashboard**\n\nSelect how you would like to view real-time agent metrics, equity curve, and win rate:", 
                reply_markup=keyboard
            )

        elif text == "/vault":
            await send_direct_message(chat_id, "🔍 **Fetching on-chain Vault data...**")
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(f"{VAULT_MANAGER_URL}/api/vault-status")
                    
                if resp.status_code == 200:
                    data = resp.json()
                    tvl = data.get("totalAssets", 0)
                    usdc_bal = data.get("usdcBalance", 0)
                    usdc_pct = data.get("usdcPercentage", 100)
                    allocations = data.get("allocations", [])
                    
                    alloc_text = ""
                    for alloc in allocations:
                        alloc_text += f"• **{alloc['asset']}**: {alloc['percentage']}% (${alloc['value']:,.2f})\n"
                        
                    msg = (
                        f"🏦 **SentiTrade Autonomous Vault**\n\n"
                        f"💵 **Total Value Locked (TVL):** `${tvl:,.2f}`\n\n"
                        f"📊 **Current Allocations:**\n"
                        f"• **USDC (Idle):** {usdc_pct}%\n"
                        f"{alloc_text}\n"
                        f"Use `/deposit` to add funds or `/redeem` to withdraw."
                    )
                    
                    query_dep = urllib.parse.urlencode({"intent": "deposit", "target": "vault", "vault": VAULT_ADDRESS, "chain": "baseSepolia", "chainId": "84532"})
                    query_red = urllib.parse.urlencode({"intent": "redeem", "target": "vault", "vault": VAULT_ADDRESS, "chain": "baseSepolia", "chainId": "84532"})
                    
                    keyboard = {"inline_keyboard": [[{"text": "💰 Deposit", "web_app": {"url": f"{MINI_APP_URL}?{query_dep}"}}, {"text": "📤 Redeem", "web_app": {"url": f"{MINI_APP_URL}?{query_red}"}}]]}
                    await send_direct_message(chat_id, msg, reply_markup=keyboard)
                else:
                    await send_direct_message(chat_id, "❌ **Error:** Could not fetch vault status.")
            except Exception as e:
                await send_direct_message(chat_id, f"🔌 **Service Disconnected:** Could not reach the Vault Execution Node.\n`{str(e)}`")

        elif text == "/deposit":
            query_params = urllib.parse.urlencode({"intent": "deposit", "target": "vault", "vault": VAULT_ADDRESS, "chain": "baseSepolia", "chainId": "84532"})
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            keyboard = {"inline_keyboard": [[{"text": "💰 Open Deposit Portal", "web_app": {"url": web_app_url}}]]}
            await send_direct_message(
                chat_id,
                "🏦 **Deposit to SentiTrade AI Vault**\n\n"
                "Deposit USDC into the autonomous hedge fund to receive yield-bearing `vSENTI` shares.\n\n"
                "Tap below to connect your wallet and execute the deposit securely on the Base Network.",
                reply_markup=keyboard
            )
            
        elif text == "/redeem":
            query_params = urllib.parse.urlencode({"intent": "redeem", "target": "vault", "vault": VAULT_ADDRESS, "chain": "baseSepolia", "chainId": "84532"})
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            keyboard = {"inline_keyboard": [[{"text": "📤 Open Redemption Portal", "web_app": {"url": web_app_url}}]]}
            await send_direct_message(
                chat_id,
                "📤 **Redeem SentiTrade Vault Shares**\n\n"
                "Burn your `vSENTI` shares to withdraw your proportional USDC from the Vault.\n\n"
                "Tap below to connect your wallet and execute the redemption securely on the Base Network.",
                reply_markup=keyboard
            )
            
        elif text.startswith("/portfolio"):
            parts = text.split(" ")
            if len(parts) < 2:
                await send_direct_message(chat_id, "⚠️ **Usage:** `/portfolio <your_wallet_address>`\nExample: `/portfolio 0x123...abc`")
                return {"status": "ok"}
            
            wallet_address = parts[1]
            if not wallet_address.startswith("0x") or len(wallet_address) != 42:
                await send_direct_message(chat_id, "❌ Invalid Ethereum wallet address format.")
                return {"status": "ok"}
            
            await send_direct_message(chat_id, "🔍 **Scanning the blockchain for your vault assets...**")
            
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(f"{VAULT_MANAGER_URL}/api/vault-balance/{wallet_address}")
                    
                if resp.status_code == 200:
                    data = resp.json()
                    shares = float(data.get("shares", 0))
                    assets = float(data.get("assets", 0))
                    
                    if shares == 0:
                        msg = (
                            f"💼 **Vault Portfolio: {wallet_address[:6]}...{wallet_address[-4:]}**\n\n"
                            f"You currently do not hold any `vSENTI` shares.\n"
                            f"Use `/deposit` to fund your account and begin earning automated yield!"
                        )
                    else:
                        msg = (
                            f"💼 **Vault Portfolio: {wallet_address[:6]}...{wallet_address[-4:]}**\n\n"
                            f"🪙 **vSENTI Balance:** `{shares:,.2f}` shares\n"
                            f"💵 **Current Value:** `${assets:,.2f} USDC`\n\n"
                            f"📈 _Your value automatically grows as the AI's rebalancing strategy generates profit._\n"
                            f"Use `/redeem` to withdraw."
                        )
                    await send_direct_message(chat_id, msg)
                else:
                    await send_direct_message(chat_id, "❌ **Error:** Could not fetch portfolio data from the network.")
            except Exception as e:
                await send_direct_message(chat_id, f"🔌 **Service Disconnected:** Could not reach the Vault Execution Node.\n`{str(e)}`")

        elif text == "/stop":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                await send_direct_message(chat_id, "Agent offline. You have opted out of the ValueChain stream.")
        
        elif text == "/subscribe":
            query_params = urllib.parse.urlencode({
                "intent": "subscribe",
                "target": "dev",
                "chain": "base", 
                "chainId": "8453", # Mainnet
                "amount": "0.005"
            })
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            keyboard = {"inline_keyboard": [[{"text": "💎 Pay 0.005 ETH / Month", "web_app": {"url": web_app_url}}]]}
            await send_direct_message(
                chat_id, 
                "⭐️ **Unlock SentiTrade Premium**\n\nPay 0.005 ETH on the Base network to unlock all high-confidence agentic trade signals for 30 days.", 
                reply_markup=keyboard
            )
        
        elif text.startswith("/volatility"):
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                try:
                    new_threshold = float(text.split(" ")[1])
                    user.volatility_guard_threshold = new_threshold
                    await db.commit()
                    await send_direct_message(
                        chat_id, 
                        f"🛡️ **Volatility Guard Updated**\nYour threshold is now set to **{new_threshold}%**.\n\nSignals for assets experiencing volatility above this limit will be automatically filtered out."
                    )
                except (IndexError, ValueError):
                    await send_direct_message(chat_id, "⚠️ **Usage:** `/volatility <percentage>` (e.g., `/volatility 15`)")
        
        else:
            reply_text = generate_chat_reply(text)
            await send_direct_message(chat_id, reply_text)

    return {"status": "ok"}

@app.post("/run-analysis")
async def run_analysis_endpoint(db: AsyncSession = Depends(get_db)):
    try:
        return await perform_analysis(db)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
async def prepare_sodex_order(asset: str, action: str, address: str, amount_usd: float = 100.0) -> dict:
    clean_asset = asset.replace('$', '').upper()
    target_symbol_name = f"v{clean_asset}_vUSDC"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        state_resp = await client.get(f"{SODEX_SPOT_API}/accounts/{address}/state")
        state_resp.raise_for_status()
        state_data = state_resp.json()
        
        if state_data.get("code") != 0 or not state_data.get("data"):
            raise ValueError(f"Wallet address {address[:6]} not recognized. Have you initialized your SoDEX account?")
        
        sodex_account_id = int(state_data["data"]["aid"])
        
        if sodex_account_id == 0:
            raise ValueError(f"Wallet `{address[:6]}...` is not initialized on SoDEX. Please connect to the SoDEX dApp and deposit funds to activate your trading account first.")

        symbols_resp = await client.get(
            f"{SODEX_SPOT_API}/markets/symbols",
            params={"symbol": target_symbol_name}
        )
        
        symbols_data = symbols_resp.json()
        
        if symbols_data.get("code") != 0:
            error_text = str(symbols_data.get("error", "")).lower()
            if "symbol not found" in error_text:
                raise ValueError(f"Trade aborted: '{clean_asset}' is not currently listed on SoDEX.")
            else:
                raise ValueError(f"SoDEX API Error: {error_text}")
            
        symbol_id = None
        data_payload = symbols_data.get("data")
        
        if isinstance(data_payload, dict) and data_payload.get("id"):
            symbol_id = data_payload.get("id")
        elif isinstance(data_payload, list) and len(data_payload) > 0:
            for sym in data_payload:
                if sym.get("name", "").upper() == target_symbol_name.upper():
                    symbol_id = sym.get("id")
                    break

        if not symbol_id:
            raise ValueError(f"Failed to locate the ID for '{clean_asset}' on SoDEX.")

    order_item = {
        "symbolID": symbol_id,            
        "clOrdID": str(uuid.uuid4())[:36], 
        "side": 1 if action == "BUY" else 2,
        "type": 2,        
        "timeInForce": 3, 
    }
    
    if action == "BUY":
        order_item["funds"] = f"{float(amount_usd):.2f}".rstrip('0').rstrip('.') 
    else:
        order_item["quantity"] = "1"

    payload = {
        "type": "batchNewOrder",
        "params": {
            "accountID": sodex_account_id,
            "orders": [order_item]
        }
    }
    
    compact_json = json.dumps(payload, separators=(',', ':'))
    payload_hash = "0x" + keccak(text=compact_json).hex()
    nonce = int(time.time() * 1000) 
    
    return {
        "compact_json": compact_json,
        "payload_hash": payload_hash,
        "nonce": nonce
    }

async def send_direct_message(chat_id: int, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)
        print("Posted", payload)

async def delete_telegram_message(chat_id: int, message_id: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "message_id": message_id})

async def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

async def answer_callback_query(callback_query_id: str, text: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"callback_query_id": callback_query_id, "text": text})