import os
import httpx
import json
import time
import uuid
import urllib.parse
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from eth_utils import keccak

from db import init_db, get_db, User, ValueChainAnalytics
from bot_logic import (
    fetch_news_from_api, deduplicate, build_prompt, 
    analyze_with_llm, generate_signals, send_telegram_alert,
    generate_chat_reply, fetch_asset_volatility, fetch_asset_price
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
SODEX_SPOT_API = os.getenv("SODEX_SPOT_API", "https://mainnet-gw.sodex.dev/api/v1/spot")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

async def get_historical_performance(db: AsyncSession, asset: str) -> dict:
    """Calculates performance stats for a specific asset from logged analytics."""
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
    """Evaluates the outcome of signals older than 1 hour to update historical stats."""
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
        current_price = await fetch_asset_price(record.asset)
        if current_price > 0:
            price_change = current_price - record.entry_price
            pnl_pct = (price_change / record.entry_price) * 100
            
            # Record Accuracy (Positive PnL on BUY, Negative PnL on SELL equals success)
            if record.sentiment == "BUY":
                record.pnl_percentage = pnl_pct
                record.signal_accuracy = pnl_pct > 0
            else: # SELL
                record.pnl_percentage = -pnl_pct
                record.signal_accuracy = pnl_pct < 0
                
            record.forward_price_change = price_change
            
    if pending_signals:
        await db.commit()

@app.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        update = await request.json()
    except Exception:
        return {"status": "error"}

    if "callback_query" in update:
        callback_query = update["callback_query"]
        callback_id = callback_query["id"]
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data.startswith("reject_"):
            await delete_telegram_message(chat_id, message_id)
            await answer_callback_query(callback_id, "Signal discarded.")
            
        elif data.startswith("approve_"):
            parts = data.split("_")
            asset = parts[1]
            formatted_asset = f"${asset}"
            action = parts[2] if len(parts) > 2 else "BUY"
            confidence = parts[3] if len(parts) > 3 else "80"
            
            await answer_callback_query(callback_id, "Initializing Routing...")
            
            stats = await get_historical_performance(db, formatted_asset)

            query_params = urllib.parse.urlencode({
                "intent": "connect",
                "asset": formatted_asset,
                "action": action,
                "confidence": confidence,
                "winRate": stats["winRate"],
                "avgPnl": stats["avgPnl"],
                "maxDrawdown": stats["maxDrawdown"]
            })
            
            web_app_url = f"{MINI_APP_URL}?{query_params}"
            
            keyboard = {"keyboard": [[{"text": "🔗 Connect Wallet", "web_app": {"url": web_app_url}}]], "resize_keyboard": True, "one_time_keyboard": True}
            await send_direct_message(
                chat_id, 
                f"⚡ **Agentic Execution: {formatted_asset}**\n\n"
                f"Win Rate: {stats['winRate']}\n"
                f"Avg PnL: {stats['avgPnl']}\n\n"
                f"Review metrics and authorize to continue.", 
                reply_markup=keyboard
            )
        return {"status": "ok"}

    if "message" in update and "web_app_data" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        
        try:
            web_app_payload = json.loads(update["message"]["web_app_data"]["data"])
            status = web_app_payload.get("status")

            if status == "connected":
                user_address = web_app_payload.get("address")
                asset = web_app_payload.get("asset", "Unknown")
                action = web_app_payload.get("action", "BUY")
                confidence = web_app_payload.get("confidence", "80")
                
                await send_direct_message(chat_id, f"⏳ **Analyzing ValueChain...**\nPreparing AI-driven SoDEX order for {asset}.")
                
                try:
                    order_data = await prepare_sodex_order(asset=asset, action=action, address=user_address)
                    sodex_chain_id = 138565 if "testnet" in SODEX_SPOT_API else 286623

                    query_params = urllib.parse.urlencode({
                        "intent": "sign_sodex",
                        "hash": order_data["payload_hash"],
                        "nonce": order_data["nonce"],
                        "payload": order_data["compact_json"],
                        "address": user_address,
                        "sodexChainId": sodex_chain_id,
                        "asset": asset,
                        "action": action,
                        "confidence": confidence
                    })
                    
                    web_app_url = f"{MINI_APP_URL}?{query_params}"
                    
                    keyboard = {
                        "keyboard": [[{"text": f"🔐 Authorize Agentic Trade", "web_app": {"url": web_app_url}}]],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    }

                    success_msg = f"✅ **SoSoValue Agent Ready**\nAsset: {asset}\n\n⚠️ **Action Required:**\nSign the payload to authorize execution on the ValueChain."
                    await send_direct_message(chat_id, success_msg, reply_markup=keyboard)
                    
                except Exception as e:
                    await send_direct_message(chat_id, f"❌ **ValueChain Error:** {str(e)}")

            elif status == "sodex_signed":
                signature = web_app_payload.get("signature", "")
                raw_payload = web_app_payload.get("payload")
                user_address = web_app_payload.get("address")
                original_nonce = str(web_app_payload.get("nonce"))

                if signature.startswith("0x01"):
                    typed_sig = signature
                elif signature.startswith("0x"):
                    typed_sig = "0x01" + signature[2:]
                else:
                    typed_sig = "0x01" + signature
                
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-Key": user_address,  
                    "X-API-Sign": typed_sig,  
                    "X-API-Nonce": original_nonce
                }

                parsed_payload = json.loads(raw_payload)
                request_body = json.dumps(parsed_payload["params"], separators=(',', ':'))

                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{SODEX_SPOT_API}/trade/orders/batch", content=request_body, headers=headers)
                    resp_data = resp.json()
                    
                    if resp.status_code == 200 and resp_data.get("data", [{}])[0].get("code") == 0:
                        order_id = resp_data["data"][0].get("orderID", "Unknown")
                        remove_keyboard = {"remove_keyboard": True}
                        await send_direct_message(chat_id, f"🎉 **Intelligent Trade Executed!**\nSoDEX Order ID: `{order_id}`\n\n*Welcome to the future of finance.*", reply_markup=remove_keyboard)
                    else:
                        error_detail = resp_data.get("data", [{}])[0].get("error", resp.text)
                        remove_keyboard = {"remove_keyboard": True}
                        await send_direct_message(chat_id, f"❌ **SoDEX Execution Failed:**\n`{error_detail}`", reply_markup=remove_keyboard)
                        
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
                    "🤖 **Welcome to SentiTrade-AI!**\n\n"
                    "I am your agentic gateway to intelligent finance. I analyze market narratives and help you execute trades seamlessly.\n\n"
                    "**Here is how to get started:**\n"
                    "1️⃣ **Wait for Signals:** I will automatically send you AI-analyzed trade signals based on real-time news.\n"
                    "2️⃣ **Manage Risk:** Use `/volatility 15` to set your maximum volatility guard (default is 15%). Signals above this threshold are blocked.\n"
                    "3️⃣ **Execute Trades:** When you receive a signal, click 'Route via SoDEX' to securely authorize the trade via our MiniApp.\n\n"
                    "Use `/subscribe` anytime to unlock premium features and faster alerts!"
                )
                await send_direct_message(chat_id, welcome_message)
            else:
                user.is_active = True
                await db.commit()
                await send_direct_message(chat_id, "Agentic alerts reactivated. Use /subscribe to unlock premium SoDEX routing alerts.")
        
        elif text == "/help":
            help_message = (
                "📚 **SentiTrade-AI Command Directory**\n\n"
                "Here are the commands you can use to control your agentic experience:\n\n"
                "🔹 `/start` - Activate the agent and view the onboarding guide.\n"
                "🔹 `/help` - View this list of available commands.\n"
                "🔹 `/volatility <percentage>` - Set your risk guard (e.g., `/volatility 15`). Automatically blocks signals for assets exceeding this 24h volatility limit.\n"
                "🔹 `/subscribe` - Unlock the premium ValueChain stream and SoDEX routing alerts.\n"
                "🔹 `/stop` - Take the agent offline and stop receiving all alerts.\n\n"
                "💡 *Tip: You can also chat with me directly! Send any message to ask about market narratives, SoDEX routing, or on-chain finance.*"
            )
            await send_direct_message(chat_id, help_message)

        elif text == "/stop":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                await send_direct_message(chat_id, "Agent offline. You have opted out of the ValueChain stream.")
        
        elif text == "/subscribe":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_subscribed = True 
                await db.commit()
                await send_direct_message(chat_id, "🎉 **Subscription Activated!** You will now receive agentic SoDEX trade signals.")
        
        elif text.startswith("/volatility"):
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                try:
                    new_threshold = int(text.split(" ")[1])
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
async def run_analysis(db: AsyncSession = Depends(get_db)):
    try:
        # Run the backfilling sweep to evaluate past signal accuracy 
        await backfill_signal_performance(db)

        news_items = await fetch_news_from_api()
        new_news = await deduplicate(news_items, db)
        if not new_news: return {"status": "no_new_data"}

        analyses = analyze_with_llm(build_prompt(new_news))
        signals = generate_signals(analyses)

        if signals:
            result = await db.execute(select(User.chat_id, User.is_subscribed, User.volatility_guard_threshold).filter(User.is_active == True))
            active_users = result.all()
            premium_users = [{"chat_id": r[0], "vol_guard": r[2]} for r in active_users if r[1]]
            free_users = [{"chat_id": r[0], "vol_guard": r[2]} for r in active_users if not r[1]]

            for index, signal in enumerate(signals):
                entry_price = await fetch_asset_price(signal["asset"])
                
                db.add(ValueChainAnalytics(
                    asset=signal["asset"],
                    sentiment=signal["action"],
                    confidence=signal["confidence"],
                    rationale=signal["rationale"],
                    source_article=signal["source_headline"],
                    entry_price=entry_price
                ))
                
                volatility = await fetch_asset_volatility(signal["asset"])
                signal["volatility"] = volatility

                target_users = premium_users.copy()
                if index == 0: target_users.extend(free_users)

                for user in target_users:
                    if volatility <= user["vol_guard"]:
                        await send_telegram_alert(user["chat_id"], signal)

            if len(signals) > 1:
                missed_count = len(signals) - 1
                upsell_msg = f"🔒 **{missed_count} more high-confidence signals** were just generated!\n\nUse `/subscribe` to unlock the full ValueChain stream and premium SoDEX routing alerts."
                for chat_id in free_users:
                    await send_direct_message(chat_id, upsell_msg)
        
        await db.commit()
        return {"status": "success", "agentic_actions_routed": len(signals)}

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
            raise ValueError(f"Wallet `{address[:6]}...` is not initialized on SoDEX. Please connect to the SoDEX dApp and deposit funds to activate your trading account first. \n\n 👉 https://sodex.com/")

        symbols_resp = await client.get(
            f"{SODEX_SPOT_API}/markets/symbols",
            params={"symbol": target_symbol_name}
        )
        
        symbols_data = symbols_resp.json()
        print(f"SoDEX Symbol Query Response: {symbols_data}")
        
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