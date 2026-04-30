#!/usr/bin/env python3
"""
Wave 1 – Early Prototype: SoSoValue news → LLM sentiment → dummy trade signal (+ Telegram test)
Updated: Strictly uses live SOSOVALUE_API_KEY and Groq for blazing-fast inference.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, ValidationError

# ------------------------------------------------------------------
# Load environment variables
load_dotenv()

SOSOVALUE_API_KEY = os.getenv("SOSOVALUE_API_KEY")
SOSOVALUE_BASE_URL = os.getenv("SOSOVALUE_BASE_URL", "https://api.sosovalue.com")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File paths
CACHE_FILE = Path("news_cache.json")

# ------------------------------------------------------------------
# Pydantic schema for LLM output
class SentimentAnalysis(BaseModel):
    sentiment: str           # "bullish", "bearish", or "neutral"
    confidence: int          # 0-100
    narrative_tags: list[str] # e.g. ["ETF inflow", "partnership"]
    rationale: str           # short explanation (max 150 chars)

# ------------------------------------------------------------------
def load_cache() -> set:
    """Loads cached news IDs from a local JSON file."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        return set(data.get("seen_ids", []))
    return set()

def save_cache(seen_ids: set):
    """Saves the set of processed news IDs."""
    with open(CACHE_FILE, "w") as f:
        json.dump({"seen_ids": list(seen_ids)}, f)

def fetch_news_from_api() -> list[dict]:
    """Fetches latest news strictly from SoSoValue API (real endpoint)."""
    if not SOSOVALUE_API_KEY:
        raise ValueError("CRITICAL: SOSOVALUE_API_KEY is not set in the .env file.")

    headers = {"x-api-key": SOSOVALUE_API_KEY}
    url = f"{SOSOVALUE_BASE_URL}/v1/news/list"
    params = {"limit": 20}  # fetch enough to test dedup
    
    with httpx.Client(timeout=15) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        
    # Adjust according to actual response structure – assuming {data: [...]}
    return data.get("data", data) if isinstance(data, dict) else data

def deduplicate(items: list[dict], seen_ids: set) -> list[dict]:
    """Filters out already‑processed news items and updates the cache."""
    new_items = []
    for item in items:
        nid = item.get("newsId")
        if nid and nid not in seen_ids:
            new_items.append(item)
            seen_ids.add(nid)
    if new_items:
        print(f"🔍 Found {len(new_items)} new items out of {len(items)} total.")
    else:
        print("📭 No new news items since last check.")
    return new_items

def build_prompt(news_batch: list[dict]) -> str:
    """Creates a chat prompt requiring strict JSON output."""
    # Simplify batch: just take the first 10 items for this prototype
    articles = []
    for n in news_batch[:10]:
        articles.append(
            f"- {n.get('title', 'No Title')} (Asset: {n.get('currencyCode', 'N/A')}) | Summary: {n.get('summary', 'No Summary')}"
        )

    prompt = f"""
You are a crypto news sentiment analyst. Below is a list of recent headlines and summaries.
For each article, output a JSON object with:
- "sentiment": one of "bullish", "bearish", "neutral"
- "confidence": integer between 0 and 100
- "narrative_tags": array of relevant tags (e.g., "ETF inflow", "network outage")
- "rationale": a short sentence explaining the sentiment (max 150 characters)

Return the result as a JSON array of objects, with one object per article.
Articles:
{chr(10).join(articles)}
"""
    return prompt

def analyze_with_llm(prompt: str) -> list[dict]:
    """Sends prompt to Groq and parses the structured response."""
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY is missing. Cannot perform sentiment analysis.")
        return []

    client = Groq(api_key=GROQ_API_KEY)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # High-performance Groq model
            messages=[
                {"role": "system", "content": "You are a precise JSON responder. Always format your response as valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}  # Groq supports JSON mode on Llama 3
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)
        
        # If the returned object is a dict with a key, try to get list
        if isinstance(data, dict) and "articles" in data:
            return data["articles"]
        if isinstance(data, list):
            return data
        # Fallback: try to find any list
        for v in data.values():
            if isinstance(v, list):
                return v
        raise ValueError("Unexpected JSON structure returned from LLM")
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return []

def generate_dummy_trade(analyses: list[dict]) -> list[dict]:
    """Converts high‑confidence analyses into dummy trade signals."""
    signals = []
    for a in analyses:
        try:
            sa = SentimentAnalysis(**a)
        except ValidationError:
            continue   # skip malformed

        if sa.confidence >= 80 and sa.sentiment in ("bullish", "bearish"):
            action = "BUY" if sa.sentiment == "bullish" else "SELL"
            signals.append({
                "asset": sa.narrative_tags[0] if sa.narrative_tags else "UNKNOWN",
                "action": action,
                "confidence": sa.confidence,
                "rationale": sa.rationale
            })
    return signals

def send_telegram_test():
    """Sends a dummy trade card with Accept/Reject buttons to Telegram."""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("⚠️  Telegram not configured; skipping.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Execute", "callback_data": "approve"},
                {"text": "❌ Cancel", "callback_data": "reject"}
            ]
        ]
    }
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "🧪 Wave 1 Prototype – Dummy Trade Signal\n📈 BUY ETH at $3,000\nConfidence: 85%\nRationale: Strong ETF inflow narrative",
        "reply_markup": json.dumps(keyboard)
    }
    try:
        resp = httpx.post(url, json=payload)
        if resp.status_code == 200:
            print("📨 Telegram test message sent successfully!")
        else:
            print(f"⚠️  Telegram send failed: {resp.text}")
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")

# ------------------------------------------------------------------
# Main prototype flow
def main():
    print("🚀 SentiTrade AI - Wave 1 Prototype (Powered by Groq)")
    print("====================================================")

    # Step 1: Load cache
    seen_ids = load_cache()

    # Step 2: Fetch real-time news
    try:
        print("📡 Fetching real‑time news from SoSoValue...")
        news_items = fetch_news_from_api()
    except Exception as e:
        print(f"❌ Critical Error: {e}")
        sys.exit(1)

    # Step 3: Deduplicate
    new_news = deduplicate(news_items, seen_ids)
    if not new_news:
        print("Nothing new to process. Exiting.")
        return

    # Step 4: Build prompt and analyze with LLM
    prompt = build_prompt(new_news)
    print("🧠 Sending to Groq...")
    analyses = analyze_with_llm(prompt)

    if not analyses:
        print("No analysis returned, stopping.")
        return

    # Step 5: Show raw analyses
    for i, a in enumerate(analyses):
        print(f"  [{i+1}] {a.get('sentiment', '?')} ({a.get('confidence', 0)}) – {a.get('rationale', '')}")

    # Step 6: Generate dummy trade signals
    signals = generate_dummy_trade(analyses)
    if signals:
        print("\n📊 Dummy Trade Signals:")
        for sig in signals:
            print(f"  → {sig['action']} {sig['asset']} (confidence {sig['confidence']}%): {sig['rationale']}")
    else:
        print("\n📉 No high-confidence signals generated.")

    # Step 7: Save updated cache
    save_cache(seen_ids)
    print(f"\n💾 Cache updated. {len(seen_ids)} unique IDs stored.")

    # Step 8: Optional Telegram test
    send_telegram_test()

if __name__ == "__main__":
    main()