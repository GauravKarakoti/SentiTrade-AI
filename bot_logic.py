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
    key_factors: list[str]
    source_headline: str

def build_prompt(news_batch: list[dict]) -> str:
    articles = []
    for n in news_batch:
        content = n.get("content", "No Content")
        sector_tags = n.get("sector_tags", [])
        sectors_str = ", ".join(sector_tags) if sector_tags else "Uncategorized"
        headline = n.get('title', 'No Title')
        
        articles.append(f"- {headline} (Sectors: {sectors_str}) | Content: {content}")
        
        # Increased context window to 15 to catch broader macro trends
        if len(articles) >= 15:
            break

    return f"""
You are the SentiTrade AI, an autonomous asset manager operating a tokenized copy-trading vault. 
Analyze the following financial data to determine if a macro-economic sector rotation is required.

CRITICAL INSTRUCTION - SSI INDEX ROUTING:
You are managing an Ethereum ERC-4626 vault. You do not buy individual tokens. You ONLY allocate capital into SoSoValue Index (SSI) tokens to achieve passive, sector-wide exposure.
- For AI/Tech/Broad Bullishness: route to "$MAG7.ssi"
- For on-chain finance dominance: route to "$DEFI.ssi"
- For high-risk speculation waves: route to "$MEME.ssi"

Output a strict JSON object with a single key "data", holding an array of action objects.
Each object MUST contain:
- "asset": The exact string "$MAG7.ssi", "$DEFI.ssi", or "$MEME.ssi"
- "sentiment": "bullish" (Triggers BUY function) or "bearish" (Triggers SELL function)
- "confidence": Integer 0-100. Must be > 85 to trigger a vault rebalance.
- "narrative_tags": array of relevant tags (e.g., "DeFi Index Allocation", "Macro Shift")
- "rationale": A crisp, 1-sentence explanation of the macro catalyst driving this rebalance.
- "key_factors": Array of 2-3 specific catalysts (e.g., "Institutional inflow detected").
- "source_headline": The exact title of the primary article driving this sentiment.

News Feed:
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
                    "content": "You are the SentiTrade-AI Agent, powered by SoSoValue. Explain on-chain finance, vault mechanics, and your macro logic in simple, beginner-friendly terms."
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
            # Vault logic requires strict confidence threshold (>= 85) to avoid over-trading
            if sa.confidence >= 85 and sa.sentiment in ("bullish", "bearish"):
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
    
    action_emoji = "🟢 ALLOCATE (BUY)" if signal['action'].upper() == "BUY" else "🔴 LIQUIDATE (SELL)"
    volatility_formatted = f"{volatility:.2f}%"
    
    factors_text = "\n".join([f"• {f}" for f in signal.get('key_factors', [])])
    
    callback_data_approve = f"approve_{clean_asset}_{signal['action']}_{adjusted_confidence}"
    
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "⚡ Execute Vault Rebalance", 
                    "callback_data": callback_data_approve
                },
                {
                    "text": "❌ Dismiss Signal", 
                    "callback_data": f"reject_{clean_asset}"
                }
            ]
        ]
    }
    
    alert_text = (
        f"🏦 **Vault Rebalance Triggered**\n\n"
        f"🪙 **Index Target:** {signal['asset']}\n"
        f"⚡ **Strategy:** {action_emoji}\n"
        f"🧠 **AI Confidence:** {adjusted_confidence}%\n"
        f"{confidence_bar}\n\n"
        f"📖 **Macro Catalyst:**\n_{signal['rationale']}_\n\n"
        f"🔍 **Key Factors:**\n{factors_text}\n\n"
        f"📊 **Sector Volatility (24h):** {volatility_formatted}\n"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": alert_text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

# --- KPI CALCULATION FUNCTIONS ---

def calculate_win_rate(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    wins = sum(1 for pnl in pnls if pnl > 0)
    return (wins / len(pnls)) * 100

def calculate_roi(starting_equity: float, current_equity: float) -> float:
    if starting_equity == 0:
        return 0.0
    return ((current_equity - starting_equity) / starting_equity) * 100

def calculate_max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd * 100