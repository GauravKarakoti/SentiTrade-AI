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

from db import init_db, get_db, User
from bot_logic import (
    fetch_news_from_api, deduplicate, build_prompt, 
    analyze_with_llm, generate_signals, send_telegram_alert,
    generate_chat_reply
)

# Environment Variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
# Default to mainnet, but allow override for testing
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

    # --- HANDLE BUTTON CLICKS (CALLBACK QUERIES) ---
    if "callback_query" in update:
        callback_query = update["callback_query"]
        callback_id = callback_query["id"]
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data.startswith("reject_"):
            await delete_telegram_message(chat_id, message_id)
            await answer_callback_query(callback_id, "Signal deleted.")
            
        elif data.startswith("approve_"):
            asset = data.split("_")[1]
            await answer_callback_query(callback_id, "Requesting wallet connection...")
            
            # STEP 1: Ask for connection first. Pass the asset so we remember what we are trading.
            web_app_url = f"{MINI_APP_URL}?intent=connect&asset={asset}"
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "🔗 Connect Wallet to Set Destination", 
                            "web_app": {"url": web_app_url}
                        }
                    ]
                ]
            }
            await edit_telegram_message(
                chat_id, 
                message_id, 
                f"⚡ **Initiating {asset} Trade on SoDEX**\n\nPlease connect your wallet to designate a settlement address.",
                reply_markup=keyboard
            )

        return {"status": "ok"}

    # --- HANDLE WEB APP DATA RETURNED FROM MINI APP ---
    if "message" in update and "web_app_data" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        
        try:
            web_app_payload = json.loads(update["message"]["web_app_data"]["data"])
            status = web_app_payload.get("status")

            # --- STEP 2: WALLET CONNECTED -> GENERATE SODEX ORDER ---
            if status == "connected":
                user_address = web_app_payload.get("address")
                asset = web_app_payload.get("asset", "Unknown")
                
                await send_direct_message(chat_id, f"⏳ **Executing Trade...**\nPreparing SoDEX order for {asset}.")
                
                try:
                    order_data = await prepare_sodex_order(asset=asset, action="BUY", address=user_address)
                    sodex_chain_id = 138565 if "testnet" in SODEX_SPOT_API else 286623

                    # Pass the payload hash, nonce, AND chainId to the Mini App for EIP-712 signing
                    query_params = urllib.parse.urlencode({
                        "intent": "sign_sodex",
                        "hash": order_data["payload_hash"],
                        "nonce": order_data["nonce"],
                        "payload": order_data["compact_json"],
                        "address": user_address,
                        "sodexChainId": sodex_chain_id # ADD THIS LINE
                    })
                    
                    web_app_url = f"{MINI_APP_URL}?{query_params}"
                    
                    keyboard = {
                        "inline_keyboard": [[{"text": f"🔐 Sign SoDEX Order", "web_app": {"url": web_app_url}}]]
                    }

                    success_msg = f"✅ **SoDEX Order Ready**\nAsset: {asset}\n\n⚠️ **Action Required:**\nClick below to securely sign the EIP-712 payload."
                    await send_direct_message(chat_id, success_msg, reply_markup=keyboard)
                    
                except Exception as e:
                    await send_direct_message(chat_id, f"❌ **Execution Error:** {str(e)}")

            # --- STEP 3: TRANSACTION SIGNED -> SUBMIT TO SODEX ---
            elif status == "sodex_signed":
                signature = web_app_payload.get("signature")
                raw_payload = web_app_payload.get("payload")
                nonce = web_app_payload.get("nonce")
                user_address = web_app_payload.get("address")
                
                # Append 0x01 byte prefix for SoDEX typed signatures
                typed_sig = "0x01" + signature[2:]
                
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-API-Key": user_address,
                    "X-API-Sign": typed_sig,
                    "X-API-Nonce": str(nonce)
                }
                
                # SoDEX HTTP request body contains ONLY the `params` object
                params_only = json.loads(raw_payload)["params"]
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{SODEX_SPOT_API}/trade/orders/batch", json=params_only, headers=headers)
                    resp_data = resp.json()
                    
                    if resp.status_code == 200 and resp_data.get("data", [{}])[0].get("code") == 0:
                        order_id = resp_data["data"][0].get("orderID", "Unknown")
                        await send_direct_message(chat_id, f"🎉 **Trade Executed!**\nSoDEX Order ID: `{order_id}`")
                    else:
                        error_detail = resp_data.get("data", [{}])[0].get("error", resp.text)
                        await send_direct_message(chat_id, f"❌ **SoDEX Rejection:**\n`{error_detail}`")
                        
        except json.JSONDecodeError:
            await send_direct_message(chat_id, "⚠️ Received malformed data from the signer app.")
            
        return {"status": "ok"}

    # --- EXISTING CHAT LOGIC ---
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].strip()

        if text == "/start":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if not user:
                db.add(User(chat_id=chat_id, is_active=True))
                await db.commit()
                await send_direct_message(chat_id, "Welcome to SentiTrade! You will now receive high-confidence trade signals.")
            else:
                user.is_active = True
                await db.commit()
                await send_direct_message(chat_id, "Welcome back to SentiTrade! Alerts are reactivated.")
        elif text == "/stop":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                await send_direct_message(chat_id, "You have opted out of SentiTrade alerts.")
        else:
            reply_text = generate_chat_reply(text)
            await send_direct_message(chat_id, reply_text)

    return {"status": "ok"}


@app.post("/run-analysis")
async def run_analysis(db: AsyncSession = Depends(get_db)):
    """
    Endpoint to trigger the data pipeline. 
    Call this securely via a Cron Job (e.g., cron-job.org) every X minutes.
    """
    try:
        # 1. Fetch & Deduplicate
        news_items = await fetch_news_from_api()
        new_news = await deduplicate(news_items, db)
        
        if not new_news:
            return {"status": "no_new_news"}

        # 2. Analyze
        prompt = build_prompt(new_news)
        analyses = analyze_with_llm(prompt)
        signals = generate_signals(analyses)

        # 3. Broadcast to active users
        if signals:
            result = await db.execute(select(User.chat_id).filter(User.is_active == True))
            active_chat_ids = [row[0] for row in result.all()]

            for signal in signals:
                for chat_id in active_chat_ids:
                    await send_telegram_alert(chat_id, signal)
        
        # Commit the new cached news IDs
        await db.commit()
        return {"status": "success", "signals_generated": len(signals)}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    

async def prepare_sodex_order(asset: str, action: str, address: str, amount_usd: float = 100.0) -> dict:
    """Prepares the SoDEX order payload and hash for EIP-712 signing."""
    
    clean_asset = asset.replace('$', '').upper()
    # Assuming typical spot pairing format on SoDEX like vBTC_vUSDC
    target_symbol_name = f"v{clean_asset}_vUSDC"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Fetch Dynamic Account ID[cite: 4]
        state_resp = await client.get(f"{SODEX_SPOT_API}/accounts/{address}/state")
        state_resp.raise_for_status()
        state_data = state_resp.json()
        
        if state_data.get("code") != 0 or not state_data.get("data"):
            raise ValueError(f"Wallet address {address[:6]} not recognized. Have you initialized your SoDEX account?")
        
        sodex_account_id = state_data["data"]["aid"]

        # 2. Fetch Dynamic Symbol ID[cite: 4]
        symbols_resp = await client.get(f"{SODEX_SPOT_API}/markets/symbols")
        symbols_resp.raise_for_status()
        symbols_data = symbols_resp.json()
        
        if symbols_data.get("code") != 0:
            raise ValueError("Failed to fetch available markets from SoDEX.")
            
        symbol_id = None
        for sym in symbols_data.get("data", []):
            if sym.get("name") == target_symbol_name:
                symbol_id = sym.get("id")
                break
                
        if symbol_id is None:
            raise ValueError(f"Asset '{target_symbol_name}' is currently not supported on SoDEX.")

    # CRITICAL: Keys must exactly match the Go struct order per SoDEX API docs[cite: 1]
    # Order: symbolID, clOrdID, side, type, timeInForce, [price, quantity, funds]
    order_item = {
        "symbolID": symbol_id,
        "clOrdID": str(uuid.uuid4())[:36],
        "side": 1 if action == "BUY" else 2,
        "type": 2,        # 2 = MARKET[cite: 4]
        "timeInForce": 3, # 3 = IOC[cite: 4]
    }
    
    # DecimalString fields must be strings, not floats[cite: 1]
    if action == "BUY":
        order_item["funds"] = str(amount_usd)
    else:
        order_item["quantity"] = "1.0"

    payload = {
        "type": "newOrder",
        "params": {
            "accountID": sodex_account_id,
            "orders": [order_item]
        }
    }
    
    # Compact JSON serialization (no whitespace) required for signature generation[cite: 1]
    compact_json = json.dumps(payload, separators=(',', ':'))
    payload_hash = "0x" + keccak(text=compact_json).hex()
    
    # Nonce must be Unix millisecond timestamp[cite: 1]
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