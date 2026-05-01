import os
import httpx
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import init_db, get_db, User
from bot_logic import (
    fetch_news_from_api, deduplicate, build_prompt, 
    analyze_with_llm, generate_signals, send_telegram_alert,
    generate_chat_reply
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

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
            
            MINI_APP_URL = os.getenv("MINI_APP_URL")
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
                f"⚡ **Initiating {asset} Swap**\n\nPlease connect your wallet to designate a settlement address.",
                reply_markup=keyboard
            )

        return {"status": "ok"}

    # --- HANDLE WEB APP DATA RETURNED FROM MINI APP ---
    if "message" in update and "web_app_data" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        
        try:
            web_app_payload = json.loads(update["message"]["web_app_data"]["data"])
            status = web_app_payload.get("status")

            # --- STEP 2: WALLET CONNECTED -> GENERATE SIDESHIFT ORDER ---
            if status == "connected":
                user_address = web_app_payload.get("address")
                asset = web_app_payload.get("asset", "Unknown")
                
                await send_direct_message(chat_id, f"⏳ **Executing Trade...**\nGenerating SideShift order for {asset} to settle at `{user_address[:6]}...{user_address[-4:]}`.")
                
                try:
                    # Pass the dynamic address to the trade function
                    trade_result = await execute_sideshift_trade(asset=asset, action="BUY", settle_address=user_address)
                    
                    shift_id = trade_result.get("id", "Unknown")
                    deposit_address = trade_result.get("depositAddress", "N/A")
                    deposit_coin = trade_result.get("depositCoin", "").upper()
                    
                    MINI_APP_URL = os.getenv("MINI_APP_URL")
                    wei_value = "10000000000000000" # Placeholder for 0.01 ETH
                    
                    # Generate the actual signing URL
                    web_app_url = f"{MINI_APP_URL}?to={deposit_address}&token={deposit_coin}&chain=Ethereum&chainId=1&intent=swap&value={wei_value}&data=0x"
                    
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {
                                    "text": f"🔐 Sign & Send {deposit_coin}", 
                                    "web_app": {"url": web_app_url}
                                }
                            ]
                        ]
                    }

                    success_msg = (
                        f"✅ **SideShift Order Created**\n"
                        f"Asset: {asset}\n"
                        f"Destination: `{user_address}`\n\n"
                        f"⚠️ **Action Required:**\n"
                        f"Click below to securely sign the transaction via your wallet."
                    )
                    
                    await send_direct_message(chat_id, success_msg, reply_markup=keyboard)
                    
                except httpx.HTTPStatusError as e:
                    error_msg = e.response.text if e.response else str(e)
                    await send_direct_message(chat_id, f"❌ **Swap Failed**\nAsset: {asset}\nError: SideShift rejected the request.\nDetails: {error_msg}")
                except Exception as e:
                    await send_direct_message(chat_id, f"❌ **Execution Error**\nCould not reach SideShift: {str(e)}")

            # --- STEP 3: TRANSACTION SUBMITTED ---
            elif status == "submitted":
                tx_hash = web_app_payload.get("hash", "Unknown")
                success_msg = (
                    f"🎉 **Transaction Submitted Successfully!**\n\n"
                    f"🔍 **Tx Hash:** `{tx_hash}`\n"
                    f"[View on Explorer](https://etherscan.io/tx/{tx_hash})"
                )
                await send_direct_message(chat_id, success_msg)
                
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
                await send_direct_message(chat_id, "Welcome to SentiTrade-AI! You will now receive high-confidence trade signals.")
            else:
                user.is_active = True
                await db.commit()
                await send_direct_message(chat_id, "Welcome back to SentiTrade-AI! Alerts are reactivated.")
        elif text == "/stop":
            result = await db.execute(select(User).filter(User.chat_id == chat_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_active = False
                await db.commit()
                await send_direct_message(chat_id, "You have opted out of SentiTrade-AI alerts.")
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
        
        # Commit the new cached news IDs to Neon
        await db.commit()
        return {"status": "success", "signals_generated": len(signals)}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# UPDATE: Pass settle_address as a parameter instead of env variable
async def execute_sideshift_trade(asset: str, action: str = "BUY", amount_usd: float = 100.0, settle_address: str = None) -> dict:
    sideshift_api_url = "https://sideshift.ai/api/v2/shifts/variable"
    sideshift_secret = os.getenv("SIDESHIFT_SECRET", "")
    affiliateID = os.getenv("AFFILIATE_ID", "")

    if not settle_address:
        raise ValueError("Settle address is required to execute a swap.")

    clean_asset = asset.replace("$", "").lower()

    if action == "BUY":
        deposit_coin = "usdt"
        deposit_network = "ethereum"
        settle_coin = clean_asset
        settle_network = "ethereum" 
    else: 
        deposit_coin = clean_asset
        deposit_network = "ethereum"
        settle_coin = "usdt"
        settle_network = "ethereum"

    payload = {
        "depositCoin": deposit_coin,
        "depositNetwork": deposit_network,
        "settleCoin": settle_coin,
        "settleNetwork": settle_network,
        "settleAddress": settle_address,
        "affiliateId": affiliateID
    }

    headers = {"Content-Type": "application/json"}
    if sideshift_secret:
        headers["x-sideshift-secret"] = sideshift_secret

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(sideshift_api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

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