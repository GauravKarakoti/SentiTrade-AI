import json
import os
import httpx
from groq import Groq
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import NewsCache

# Load environment variables
SOSOVALUE_API_KEY = os.getenv("SOSOVALUE_API_KEY")
SOSOVALUE_BASE_URL = os.getenv("SOSOVALUE_BASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# 1. ADDED 'asset' TO THE PYDANTIC MODEL
class SentimentAnalysis(BaseModel):
    asset: str
    sentiment: str
    confidence: int
    narrative_tags: list[str]
    rationale: str

async def fetch_news_from_api() -> list[dict]:
    if not SOSOVALUE_API_KEY:
        raise ValueError("CRITICAL: SOSOVALUE_API_KEY is not set.")

    headers = {"x-soso-api-key": SOSOVALUE_API_KEY}
    url = f"{SOSOVALUE_BASE_URL}/v1/news"
    params = {"limit": 20}
    
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json().get("data")
        
    return data.get("list", []) if isinstance(data, dict) else []

async def deduplicate(items: list[dict], db: AsyncSession) -> list[dict]:
    new_items = []
    
    # Fetch all cached IDs from Neon
    result = await db.execute(select(NewsCache.news_id))
    seen_ids = set(row[0] for row in result.all())

    for item in items:
        nid = str(item.get("id"))
        if nid and nid not in seen_ids:
            new_items.append(item)
            # Add to DB session (will be committed in the main loop)
            db.add(NewsCache(news_id=nid))
            seen_ids.add(nid)
            
    return new_items

def build_prompt(news_batch: list[dict]) -> str:
    articles = []
    for n in news_batch[:10]:
        # Extract the first matched currency symbol if it exists
        matched = n.get("matched_currencies")
        asset = matched[0].get("name", "N/A") if matched and isinstance(matched, list) else "N/A"
        
        # Use 'content' instead of 'summary'
        content = n.get("content", "No Content")
        
        articles.append(f"- {n.get('title', 'No Title')} (Asset: {asset}) | Content: {content}")

    return f"""
You are a crypto news sentiment analyst. Below is a list of recent headlines and summaries.
For each article, output a JSON object with:
- "asset": The specific cryptocurrency ticker symbol with a '$' prefix (e.g., "$HYPE", "$ADA"). If the text only mentions the project name (e.g., "Hyperliquid", "Cardano"), you MUST infer and output its standard ticker. Pay close attention to the provided "(Asset: ...)" hint. Only return "UNKNOWN" if no specific project can be identified at all.
- "sentiment": one of "bullish", "bearish", "neutral"
- "confidence": integer between 0 and 100
- "narrative_tags": array of relevant tags (e.g., "ETF inflow", "network outage")
- "rationale": a short sentence explaining the sentiment (max 150 characters)

Return the result as a JSON array of objects, with one object per article.
Articles:
{chr(10).join(articles)}
"""

def generate_chat_reply(user_message: str) -> str:
    """Generates a conversational response using Groq."""
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY is missing.")
        return "I am currently offline due to a missing API key."

    client = Groq(api_key=GROQ_API_KEY)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a concise, highly technical crypto trading assistant for SentiTrade-AI. Provide direct answers regarding blockchain, DeFi, and market analysis."
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.5,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM Chat error: {e}")
        return "Sorry, I encountered an error while processing your request."

def analyze_with_llm(prompt: str) -> list[dict]:
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY is missing.")
        return []

    client = Groq(api_key=GROQ_API_KEY)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a precise JSON responder. Always format your response as valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)
        
        if isinstance(data, dict) and "articles" in data: return data["articles"]
        if isinstance(data, list): return data
        for v in data.values():
            if isinstance(v, list): return v
        raise ValueError("Unexpected JSON structure returned from LLM")
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return []

# 3. UPDATED SIGNAL GENERATION TO USE THE NEW EXPLICIT ASSET FIELD
def generate_signals(analyses: list[dict]) -> list[dict]:
    signals = []
    for a in analyses:
        try:
            sa = SentimentAnalysis(**a)
            if sa.confidence >= 80 and sa.sentiment in ("bullish", "bearish"):
                signals.append({
                    "asset": sa.asset,  # <--- Now grabs the explicit asset field
                    "action": "BUY" if sa.sentiment == "bullish" else "SELL",
                    "confidence": sa.confidence,
                    "rationale": sa.rationale
                })
        except ValidationError:
            continue
    return signals

async def send_telegram_alert(chat_id: int, signal: dict):
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Execute", "callback_data": f"approve_{signal['asset']}"},
                {"text": "❌ Cancel", "callback_data": f"reject_{signal['asset']}"}
            ]
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": f"🚨 SentiTrade Signal\n📈 {signal['action']} {signal['asset']}\nConfidence: {signal['confidence']}%\nRationale: {signal['rationale']}",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)