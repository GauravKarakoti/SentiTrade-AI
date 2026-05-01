import os
import httpx
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
    # Initialize the Neon database tables on startup
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receives incoming messages from Telegram."""
    try:
        update = await request.json()
    except Exception:
        return {"status": "error"}

    # --- NEW: HANDLE BUTTON CLICKS (CALLBACK QUERIES) ---
    if "callback_query" in update:
        callback_query = update["callback_query"]
        callback_id = callback_query["id"]
        data = callback_query["data"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]

        if data.startswith("reject_"):
            # Deletes the signal from the chat
            await delete_telegram_message(chat_id, message_id)
            # Acknowledge to stop the loading animation on the button
            await answer_callback_query(callback_id, "Signal deleted.")
            
        elif data.startswith("approve_"):
            asset = data.split("_")[1]
            
            # 1. Stop the loading animation on the button
            await answer_callback_query(callback_id, f"Initiating {asset} swap via SideShift...")
            
            # 2. Update the message text to show processing state
            await edit_telegram_message(
                chat_id, 
                message_id, 
                f"⏳ **Executing Trade...**\nGenerating direct SideShift order for {asset}."
            )

            try:
                # 3. Call the direct SideShift Logic
                trade_result = await execute_sideshift_trade(asset=asset, action="BUY")
                
                # 4. Confirm Success and provide deposit instructions
                shift_id = trade_result.get("id", "Unknown")
                deposit_address = trade_result.get("depositAddress", "N/A")
                deposit_coin = trade_result.get("depositCoin", "").upper()
                
                success_msg = (
                    f"✅ **SideShift Order Created**\n"
                    f"Asset: {asset}\n"
                    f"Order ID: `{shift_id}`\n\n"
                    f"⚠️ **Action Required:**\n"
                    f"Send your {deposit_coin} to the following address to complete the swap:\n"
                    f"`{deposit_address}`"
                )
                
                await edit_telegram_message(chat_id, message_id, success_msg)
                
            except httpx.HTTPStatusError as e:
                # 5. Handle HTTP Failures from SideShift
                error_msg = e.response.text if e.response else str(e)
                await edit_telegram_message(
                    chat_id, 
                    message_id, 
                    f"❌ **Swap Failed**\nAsset: {asset}\nError: SideShift rejected the request.\nDetails: {error_msg}"
                )
            except Exception as e:
                # 6. Handle General Failures (timeouts, connection issues)
                await edit_telegram_message(
                    chat_id, 
                    message_id, 
                    f"❌ **Execution Error**\nAsset: {asset}\nCould not reach SideShift: {str(e)}"
                )

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
                welcome_msg = "Welcome to SentiTrade-AI! You will now receive high-confidence trade signals."
            else:
                user.is_active = True
                await db.commit()
                welcome_msg = "Welcome back to SentiTrade-AI! Alerts are reactivated."
                
            await send_direct_message(chat_id, welcome_msg)

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
    
async def execute_sideshift_trade(asset: str, action: str = "BUY", amount_usd: float = 100.0) -> dict:
    """
    Triggers a cross-chain swap directly using the SideShift API.
    """
    sideshift_api_url = "https://sideshift.ai/api/v2/shifts/variable"
    
    # Optional: SideShift secret if you are using a registered affiliate/API account
    sideshift_secret = os.getenv("SIDESHIFT_SECRET", "") 
    user_wallet = os.getenv("SETTLE_WALLET_ADDRESS")

    if not user_wallet:
        raise ValueError("SETTLE_WALLET_ADDRESS is not configured in .env")

    # Clean the ticker (e.g., $ETH -> eth)
    clean_asset = asset.replace("$", "").lower()

    # Determine deposit and settle coins based on the action
    # Assuming USDT on Ethereum as the base trading pair for this example
    if action == "BUY":
        deposit_coin = "usdt"
        deposit_network = "ethereum"
        settle_coin = clean_asset
        settle_network = "ethereum" # Update this dynamically if trading cross-chain
    else: # SELL
        deposit_coin = clean_asset
        deposit_network = "ethereum"
        settle_coin = "usdt"
        settle_network = "ethereum"

    payload = {
        "depositCoin": deposit_coin,
        "depositNetwork": deposit_network,
        "settleCoin": settle_coin,
        "settleNetwork": settle_network,
        "settleAddress": user_wallet,
        # "affiliateId": "your_affiliate_id" # Uncomment if you have one
    }

    headers = {
        "Content-Type": "application/json",
    }
    if sideshift_secret:
        headers["x-sideshift-secret"] = sideshift_secret

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(sideshift_api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

# --- TELEGRAM API HELPERS ---

async def send_direct_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})

async def delete_telegram_message(chat_id: int, message_id: int):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "message_id": message_id})

async def edit_telegram_message(chat_id: int, message_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "message_id": message_id, "text": text})

async def answer_callback_query(callback_query_id: str, text: str = ""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"callback_query_id": callback_query_id, "text": text})