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
            # Replace the signal with an execution confirmation
            await edit_telegram_message(chat_id, message_id, f"✅ Executing trade for {asset}...")
            await answer_callback_query(callback_id, "Execution started.")

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