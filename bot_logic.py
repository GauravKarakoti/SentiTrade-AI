import json
import os
import httpx
from groq import Groq
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import NewsCache

SOSOVALUE_API_KEY = os.getenv("SOSOVALUE_API_KEY")
SOSOVALUE_BASE_URL = os.getenv("SOSOVALUE_BASE_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

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

async def fetch_currency_id(asset: str) -> str:
    """Fetches the SoSoValue currency_id for a given asset symbol."""
    if not SOSOVALUE_API_KEY:
        return ""

    clean_asset = asset.replace("$", "").upper()
    headers = {"x-soso-api-key": SOSOVALUE_API_KEY}
    url = f"{SOSOVALUE_BASE_URL}/v1/currencies"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            response_data = resp.json()
            # Handle potential 'data' wrapper just in case the API uses it
            currencies = response_data.get("data", response_data) if isinstance(response_data, dict) else response_data
            
            if isinstance(currencies, list):
                for currency in currencies:
                    if currency.get("symbol", "").upper() == clean_asset:
                        return currency.get("currency_id", "")
                        
    except Exception as e:
        print(f"Currency ID fetch error for {clean_asset}: {str(e)}")
        
    return ""

async def fetch_asset_volatility(asset: str) -> float:
    if not SOSOVALUE_API_KEY:
        return 0.0
    

    clean_asset = asset.replace("$", "").upper()
    cid = await fetch_currency_id(clean_asset)
    headers = {"x-soso-api-key": SOSOVALUE_API_KEY}
    url = f"{SOSOVALUE_BASE_URL}/v1/currencies/{cid}/market-snapshot"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            response_data = resp.json()
            
            # Extract the payload, handling a potential top-level 'data' wrapper just in case
            payload = response_data.get("data", response_data) if isinstance(response_data, dict) else response_data
            
            vol_value = payload.get("change_pct_24h", 0.0)
            
            # Return the absolute percentage to represent overall volatility magnitude
            return abs(float(vol_value))
                
    except Exception as e:
        print(f"Volatility fetch error for {clean_asset}: {str(e)}")
        
    return 0.0

async def deduplicate(items: list[dict], db: AsyncSession) -> list[dict]:
    new_items = []
    result = await db.execute(select(NewsCache.news_id))
    seen_ids = set(row[0] for row in result.all())

    for item in items:
        nid = str(item.get("id"))
        if nid and nid not in seen_ids:
            new_items.append(item)
            db.add(NewsCache(news_id=nid))
            seen_ids.add(nid)
            
    return new_items

def build_prompt(news_batch: list[dict]) -> str:
    articles = []
    for n in news_batch:
        matched = n.get("matched_currencies")
        asset = matched[0].get("symbol", matched[0].get("name", "N/A")) if matched and isinstance(matched, list) else "N/A"
        
        # Skip the news item if no valid asset is found
        if asset == "N/A":
            continue
            
        content = n.get("content", "No Content")
        articles.append(f"- {n.get('title', 'No Title')} (Asset: {asset}) | Content: {content}")
        
        # Stop once we have 10 valid actionable articles
        if len(articles) >= 10:
            break

    return f"""
You are an autonomous SoSoValue Agentic System operating on the ValueChain.
Analyze the following financial data to provide actionable intelligence for the One-Person economy.
For each article, output a JSON object with:
- "asset": The standard trading ticker symbol with a '$' prefix (e.g., "$TON", "$BTC"). Do NOT use the full token name.
- "sentiment": one of "bullish", "bearish", "neutral"
- "confidence": integer between 0 and 100
- "narrative_tags": array of relevant tags (e.g., "AI x Web3", "SoDEX Liquidity")
- "rationale": a short sentence explaining the autonomous decision (max 150 chars).

Return the result as a JSON array of objects, with one object per article.
Articles:
{chr(10).join(articles)}
"""

def generate_chat_reply(user_message: str) -> str:
    if not GROQ_API_KEY:
        return "I am currently offline due to a missing API key."

    client = Groq(api_key=GROQ_API_KEY)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "You are the SentiTrade-AI Agent, powered by SoSoValue. You provide intelligent, precise insights regarding the ValueChain, SoDEX routing, and on-chain finance."
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.5,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return "Sorry, I encountered an error while processing your request."

def analyze_with_llm(prompt: str) -> list[dict]:
    if not GROQ_API_KEY: return []

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
    except Exception:
        return []

def generate_signals(analyses: list[dict]) -> list[dict]:
    signals = []
    for a in analyses:
        try:
            sa = SentimentAnalysis(**a)
            if sa.confidence >= 80 and sa.sentiment in ("bullish", "bearish"):
                signals.append({
                    "asset": sa.asset,
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
    
    clean_asset = signal['asset'].replace("$", "")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "⚡ Route via SoDEX", 
                    "callback_data": f"approve_{clean_asset}"
                },
                {
                    "text": "❌ Ignore", 
                    "callback_data": f"reject_{clean_asset}"
                }
            ]
        ]
    }
    
    # Format the volatility to 2 decimal places, defaulting to 0.0 if not present
    volatility_formatted = f"{signal.get('volatility', 0.0):.2f}%"
    
    # UPDATED: Added the 24h Volatility line to the text output
    payload = {
        "chat_id": chat_id,
        "text": f"🌐 **ValueChain Intelligence**\n🤖 Action: {signal['action']} {signal['asset']}\n📈 24h Volatility: {volatility_formatted}\nConfidence: {signal['confidence']}%\nRationale: {signal['rationale']}",
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)