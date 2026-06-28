import json
import os
import httpx
from groq import Groq
from pydantic import BaseModel, ValidationError

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

class SentimentAnalysis(BaseModel):
    asset: str
    sentiment: str
    confidence: int
    narrative_tags: list[str]
    rationale: str
    key_factors: list[str]  # Added structured bullet points for transparency
    source_headline: str

def build_prompt(news_batch: list[dict]) -> str:
    articles = []
    for n in news_batch:
        matched = n.get("matched_currencies")
        asset = matched[0].get("symbol", matched[0].get("name", "N/A")) if matched and isinstance(matched, list) else "N/A"
        if asset == "N/A":
            continue
            
        content = n.get("content", "No Content")
        sector_tags = n.get("sector_tags", [])
        sectors_str = ", ".join(sector_tags) if sector_tags else "Uncategorized"
        
        articles.append(f"- {n.get('title', 'No Title')} (Asset: {asset} | Sectors: {sectors_str}) | Content: {content}")
        
        if len(articles) >= 10:
            break

    return f"""
You are an autonomous SoSoValue Agentic System operating on the ValueChain.
Analyze the following financial data to provide actionable intelligence for a beginner trader.

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
- "rationale": A beginner-friendly, 1-sentence explanation of WHY this trade is suggested. Avoid complex jargon.
- "key_factors": An array of 2-3 short, bullet-point phrases highlighting the specific catalysts (e.g., "Institutional inflow detected", "Major protocol upgrade").
- "source_headline": The exact title of the primary article driving this sentiment.

Return the result as a JSON object containing a single key "data", which holds an array of these article objects.
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
                    "content": "You are the SentiTrade-AI Agent, powered by SoSoValue. Explain on-chain finance and your logic in simple, beginner-friendly terms."
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
                {"role": "system", "content": "You are a precise JSON responder. Always format your response as a valid JSON object containing a 'data' array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)
        
        extracted_list = []
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                extracted_list = data["data"]
            elif "articles" in data and isinstance(data["articles"], list):
                extracted_list = data["articles"]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        extracted_list = v
                        break
        
        return [item for item in extracted_list if isinstance(item, dict)]
        
    except Exception as e:
        print(f"LLM Parsing Error: {e}")
        return []

def generate_signals(analyses: list[dict]) -> list[dict]:
    signals = []
    for a in analyses:
        if not isinstance(a, dict):
            continue 
        try:
            sa = SentimentAnalysis(**a)
            if sa.confidence >= 80 and sa.sentiment in ("bullish", "bearish"):
                signals.append({
                    "asset": sa.asset,
                    "action": "BUY" if sa.sentiment == "bullish" else "SELL",
                    "confidence": sa.confidence,
                    "rationale": sa.rationale,
                    "key_factors": sa.key_factors,
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
    confidence_bar = "🟢" * filled_blocks + "⚪" * empty_blocks
    
    action_emoji = "🟢 BUY" if signal['action'].upper() == "BUY" else "🔴 SELL"
    volatility_formatted = f"{volatility:.2f}%"
    
    factors_text = "\n".join([f"• {f}" for f in signal.get('key_factors', [])])
    
    callback_data_approve = f"approve_{clean_asset}_{signal['action']}_{adjusted_confidence}"
    
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "⚡ Route via SoDEX", 
                    "callback_data": callback_data_approve
                },
                {
                    "text": "❌ Dismiss", 
                    "callback_data": f"reject_{clean_asset}"
                }
            ]
        ]
    }
    
    alert_text = (
        f"🎯 **New AI Trade Setup Discovered**\n\n"
        f"🪙 **Asset:** {signal['asset']}\n"
        f"⚡ **Action:** {action_emoji}\n"
        f"🧠 **AI Confidence:** {adjusted_confidence}%\n"
        f"{confidence_bar}\n\n"
        f"📖 **The Logic (Why?):**\n_{signal['rationale']}_\n\n"
        f"🔍 **Key Catalysts:**\n{factors_text}\n\n"
        f"📊 **Risk (24h Volatility):** {volatility_formatted}\n"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": alert_text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)