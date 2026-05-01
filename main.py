import os
import httpx
import json
import time
import uuid
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from eth_utils import keccak

from db import init_db, get_db, User, ValueChainAnalytics
from bot_logic import (
    fetch_news_from_api, deduplicate, build_prompt, 
    analyze_with_llm, generate_signals, send_telegram_alert,
    generate_chat_reply
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
SODEX_SPOT_API = os.getenv("SODEX_SPOT_API", "https://mainnet-gw.sodex.dev/api/v1/spot")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

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
            await answer_callback_query(callback_id, "Signal discarded from ValueChain.")
            
        elif data.startswith("approve_"):
            asset = data.split("_")[1]
            await answer_callback_query(callback_id, "Initializing Agentic Routing...")
            
            web_app_url = f"{MINI_APP_URL}?intent=connect&asset={asset}"
            
            keyboard = {
                "keyboard": [
                    [
                        {
                            "text": "🔗 Connect Wallet to Access SoDEX", 
                            "web_app": {"url": web_app_url}
                        }
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            await send_direct_message(
                chat_id, 
                f"⚡ **Agentic Execution: {asset}**\n\nTo navigate on-chain finance with precision, please connect your wallet.",
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
                
                await send_direct_message(chat_id, f"⏳ **Analyzing ValueChain...**\nPreparing AI-driven SoDEX order for {asset}.")
                
                try:
                    order_data = await prepare_sodex_order(asset=asset, action="BUY", address=user_address)
                    sodex_chain_id = 138565 if "testnet" in SODEX_SPOT_API else 286623

                    query_params = urllib.parse.urlencode({
                        "intent": "sign_sodex",
                        "hash": order_data["payload_hash"],
                        "nonce": order_data["nonce"],
                        "payload": order_data["compact_json"],
                        "address": user_address,
                        "sodexChainId": sodex_chain_id 
                    })
                    
                    web_app_url = f"{MINI_APP_URL}?{query_params}"
                    
                    keyboard = {
                        "keyboard": [
                            [
                                {
                                    "text": f"🔐 Authorize Agentic Trade", 
                                    "web_app": {"url": web_app_url}
                                }
                            ]
                        ],
                        "resize_keyboard": True,
                        "one_time_keyboard": True
                    }

                    success_msg = f"✅ **SoSoValue Agent Ready**\nAsset: {asset}\n\n⚠️ **Action Required:**\nSign the payload to authorize execution on the ValueChain."
                    await send_direct_message(chat_id, success_msg, reply_markup=keyboard)
                    
                except Exception as e:
                    await send_direct_message(chat_id, f"❌ **ValueChain Error:** {str(e)}")

            elif status == "sodex_signed":
                signature = web_app_payload.get("signature")
                raw_payload = web_app_payload.get("payload")
                nonce = web_app_payload.get("nonce")
                user_address = web_app_payload.get("address")
                
                typed_sig = "0x01" + signature[2:]
                
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-Key": user_address,
                    "X-API-Sign": typed_sig,
                    "X-API-Nonce": str(nonce)
                }
                
                params_only = json.loads(raw_payload)["params"]
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{SODEX_SPOT_API}/trade/orders/batch", json=params_only, headers=headers)
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
                await send_direct_message(chat_id, "Welcome to the SoSoValue Ecosystem! SentiTrade-AI will now route actionable intelligence to you.")
            else:
                user.is_active = True
                await db.commit()
                await send_direct_message(chat_id, "Agentic alerts reactivated.")
        elif text == "/stop":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                await send_direct_message(chat_id, "Agent offline. You have opted out of the ValueChain stream.")
        else:
            reply_text = generate_chat_reply(text)
            await send_direct_message(chat_id, reply_text)

    return {"status": "ok"}


@app.post("/run-analysis")
async def run_analysis(db: AsyncSession = Depends(get_db)):
    try:
        news_items = await fetch_news_from_api()
        new_news = await deduplicate(news_items, db)
        
        if not new_news:
            return {"status": "no_new_data"}

        prompt = build_prompt(new_news)
        analyses = analyze_with_llm(prompt)
        signals = generate_signals(analyses)

        if signals:
            result = await db.execute(select(User.chat_id).filter(User.is_active == True))
            active_chat_ids = [row[0] for row in result.all()]

            for signal in signals:
                # NEW: Log to ValueChainAnalytics
                db.add(ValueChainAnalytics(
                    asset=signal["asset"],
                    sentiment=signal["action"],
                    confidence=signal["confidence"],
                    rationale=signal["rationale"]
                ))

                for chat_id in active_chat_ids:
                    await send_telegram_alert(chat_id, signal)
        
        await db.commit()
        return {"status": "success", "agentic_actions_routed": len(signals)}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
async def prepare_sodex_order(asset: str, action: str, address: str, amount_usd: float = 100.0) -> dict:
    """Prepares the SoDEX order payload and hash for EIP-712 signing."""
    
    clean_asset = asset.replace('$', '').upper()
    target_symbol_name = f"v{clean_asset}_vUSDC"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        state_resp = await client.get(f"{SODEX_SPOT_API}/accounts/{address}/state")
        state_resp.raise_for_status()
        state_data = state_resp.json()
        
        if state_data.get("code") != 0 or not state_data.get("data"):
            raise ValueError(f"Wallet address {address[:6]} not recognized. Have you initialized your SoDEX account?")
        
        # Cast the string ID to an integer
        sodex_account_id = int(state_data["data"]["aid"])
        
        # --- NEW: Catch uninitialized (zero) accounts ---
        if sodex_account_id == 0:
            raise ValueError(f"Wallet `{address[:6]}...` is not initialized on SoDEX. Please connect to the SoDEX dApp and deposit funds to activate your trading account first. \n\n 👉 https://sodex.com/")

        # 2. Fetch Dynamic Symbol ID via Direct Query
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

    # 3. Prepare the Order Structure
    # --- FIX: Reverted to strict matching (symbolID, clOrdID) per SoDEX API docs ---
    order_item = {
        "symbolID": symbol_id,             
        "clOrdID": str(uuid.uuid4())[:36], 
        "side": 1 if action == "BUY" else 2,
        "type": 2,        # 2 = MARKET
        "timeInForce": 3, # 3 = IOC
    }
    
    if action == "BUY":
        order_item["funds"] = str(amount_usd)
    else:
        order_item["quantity"] = "1.0"

    payload = {
        "type": "newOrder",
        "params": {
            "accountID": sodex_account_id, # Must be integer!
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

# --- Telegram Utility Functions ---

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