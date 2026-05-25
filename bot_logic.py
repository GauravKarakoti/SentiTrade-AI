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
    source_headline: str

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
            payload = response_data.get("data", response_data) if isinstance(response_data, dict) else response_data
            vol_value = payload.get("change_pct_24h", 0.0)
            return abs(float(vol_value))
                
    except Exception as e:
        print(f"Volatility fetch error for {clean_asset}: {str(e)}")
        
    return 0.0

# NEW: Price fetching logic
async def fetch_asset_price(asset: str) -> float:
    if not SOSOVALUE_API_KEY:
        return 0.0
    
    clean_asset = asset.replace("$", "").upper()
    cid = await fetch_currency_id(clean_asset)
    if not cid:
        return 0.0
        
    headers = {"x-soso-api-key": SOSOVALUE_API_KEY}
    url = f"{SOSOVALUE_BASE_URL}/v1/currencies/{cid}/market-snapshot"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            
            response_data = resp.json()
            payload = response_data.get("data", response_data) if isinstance(response_data, dict) else response_data
            
            return float(payload.get("price", payload.get("current_price", 0.0)))
                
    except Exception as e:
        print(f"Price fetch error for {clean_asset}: {str(e)}")
        
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
        if asset == "N/A":
            continue
            
        content = n.get("content", "No Content")
        articles.append(f"- {n.get('title', 'No Title')} (Asset: {asset}) | Content: {content}")
        
        if len(articles) >= 10:
            break

    return f"""
You are an autonomous SoSoValue Agentic System operating on the ValueChain.
Analyze the following financial data to provide actionable intelligence.

CRITICAL INSTRUCTION - SSI INDEX INTEGRATION:
If an article's narrative strongly impacts an entire sector rather than a single asset, you MUST route the signal to the appropriate SoSoValue Index (SSI) token instead of a single coin to achieve passive index investing:
- Top 7 Market Cap / Broad Market Bull: output "$MAG7.ssi"
- Meme Coin Sector: output "$MEME.ssi"
- DeFi Sector: output "$DEFI.ssi"
- Macro uncertainty / Delta-neutral Hedging: output "$USSI"

For each article, output a JSON object with:
- "asset": The standard ticker with a '$' prefix (e.g., "$TON") OR the appropriate SSI Index token (e.g., "$MEME.ssi").
- "sentiment": one of "bullish", "bearish", "neutral"
- "confidence": integer between 0 and 100
- "narrative_tags": array of relevant tags (e.g., "DeFi Index Allocation")
- "rationale": a short sentence explaining the autonomous decision (max 150 chars).
- "source_headline": The exact title of the primary article driving this sentiment.

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
                    "rationale": sa.rationale,
                    "source_headline": sa.source_headline
                })
        except ValidationError:
            continue
    return signals

async def send_telegram_alert(chat_id: int, signal: dict):
    if not TELEGRAM_BOT_TOKEN:
        return
    
    clean_asset = signal['asset'].replace("$", "")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    volatility = signal.get('volatility', 0.0)
    risk_penalty = int(volatility * 0.5) 
    adjusted_confidence = max(0, signal['confidence'] - risk_penalty)
    
    filled_blocks = int(adjusted_confidence / 10)
    empty_blocks = 10 - filled_blocks
    confidence_bar = "🟩" * filled_blocks + "⬜" * empty_blocks
    
    action_emoji = "🟢 BUY" if signal['action'].upper() == "BUY" else "🔴 SELL"
    volatility_formatted = f"{volatility:.2f}%"
    
    callback_data_approve = f"approve_{clean_asset}_{signal['action']}_{adjusted_confidence}"
    
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "⚡ Route via SoDEX", 
                    "callback_data": callback_data_approve
                },
                {
                    "text": "❌ Ignore", 
                    "callback_data": f"reject_{clean_asset}"
                }
            ]
        ]
    }
    
    alert_text = (
        f"🧠 **ValueChain AI Intelligence**\n\n"
        f"**Asset:** {signal['asset']}\n"
        f"**Action:** {action_emoji}\n"
        f"**Risk-Adjusted Confidence:** {adjusted_confidence}%\n"
        f"{confidence_bar}\n\n"
        f"📰 **Source Driver:** _{signal['source_headline']}_\n"
        f"💡 **AI Rationale:** {signal['rationale']}\n"
        f"📊 **24h Volatility Risk:** {volatility_formatted}\n"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": alert_text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)