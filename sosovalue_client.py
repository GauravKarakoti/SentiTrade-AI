import os
import time
import asyncio
import httpx
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

REDIS_URL = os.getenv("REDIS_URL")
SOSOVALUE_API_KEY = os.getenv("SOSOVALUE_API_KEY")
SOSOVALUE_BASE_URL = os.getenv("SOSOVALUE_BASE_URL")

redis_client = Redis.from_url(
    REDIS_URL, 
    decode_responses=True,
    ssl_cert_reqs="none"
)

# Rate limiter params
RATE_LIMIT_CAPACITY = 10
RATE_LIMIT_REFILL_RATE = 2  # Tokens per second

async def acquire_token():
    """Atomic Redis token bucket rate limiting via Lua script."""
    lua_script = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local requested = 1
    
    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(bucket[1])
    local last_refill = tonumber(bucket[2])
    
    if not tokens then
        tokens = capacity
        last_refill = now
    else
        local time_passed = math.max(0, now - last_refill)
        tokens = math.min(capacity, tokens + (time_passed * refill_rate))
    end
    
    if tokens >= requested then
        tokens = tokens - requested
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)
        return 1
    else
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        return 0
    end
    """
    while True:
        now = time.time()
        allowed = await redis_client.eval(
            lua_script, 1, "soso_api_bucket", RATE_LIMIT_CAPACITY, RATE_LIMIT_REFILL_RATE, now
        )
        if allowed == 1:
            break
        await asyncio.sleep(0.5)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
)
async def make_api_request(url: str, params: dict = None):
    await acquire_token()
    headers = {"x-soso-api-key": SOSOVALUE_API_KEY}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

async def fetch_news_from_api() -> list[dict]:
    if not SOSOVALUE_API_KEY:
        raise ValueError("CRITICAL: SOSOVALUE_API_KEY is not set.")
    url = f"{SOSOVALUE_BASE_URL}/v1/news"
    data = await make_api_request(url, {"limit": 20})
    return data.get("data", {}).get("list", []) if isinstance(data.get("data"), dict) else []

async def deduplicate_and_categorize(news_items: list[dict]) -> list[dict]:
    """Filters news using MGET to save Upstash commands, maps native tags."""
    if not news_items:
        return []

    # 1. Prepare keys for a single batch read
    valid_items = [item for item in news_items if item.get("id")]
    keys = [f"news:{item['id']}" for item in valid_items]
    
    if not keys: 
        return []

    # 2. Fetch all keys from Upstash in ONE single command
    existing_flags = await redis_client.mget(keys)
    
    new_items = []
    keys_to_set = {}

    # 3. Figure out which ones are actually new
    for item, exists in zip(valid_items, existing_flags):
        if not exists:  # If Redis returned None, it's a new article
            nid = str(item.get("id"))
            
            # Map native API tags straight to sector_tags
            item["sector_tags"] = item.get("tags", ["General"])
            
            new_items.append(item)
            keys_to_set[f"news:{nid}"] = "1"

    # 4. Save only the brand new ones.
    if keys_to_set:
        # We use a pipeline to efficiently execute the writes
        async with redis_client.pipeline() as pipe:
            for key, val in keys_to_set.items():
                pipe.setex(key, 86400, val) # Set value with 24h TTL
            await pipe.execute()
            
    return new_items

async def fetch_currency_id(clean_asset: str) -> str:
    url = f"{SOSOVALUE_BASE_URL}/v1/currencies"
    data = await make_api_request(url)
    currencies = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(currencies, list):
        for currency in currencies:
            if currency.get("symbol", "").upper() == clean_asset:
                return currency.get("currency_id", "")
    return ""

async def fetch_market_snapshot(asset: str) -> dict:
    clean_asset = asset.replace("$", "").upper()
    cache_key = f"market_snapshot_cache:{clean_asset}"
    
    try:
        cid = await fetch_currency_id(clean_asset)
        if not cid: return {}
        
        url = f"{SOSOVALUE_BASE_URL}/v1/currencies/{cid}/market-snapshot"
        data = await make_api_request(url)
        payload = data.get("data", data) if isinstance(data, dict) else data
        
        # Update cache (5 min TTL = 300 seconds)
        await redis_client.hset(cache_key, mapping={
            "price": str(payload.get("price", payload.get("current_price", 0.0))),
            "volatility": str(payload.get("change_pct_24h", 0.0))
        })
        await redis_client.expire(cache_key, 300)
        return payload
        
    except Exception as e:
        # Fallback Mechanism: Use cached values if API fails
        cached_data = await redis_client.hgetall(cache_key)
        if cached_data:
            print(f"Market data API failed. Using cached fallback for {asset}...")
            return {
                "price": float(cached_data.get("price", 0.0)),
                "change_pct_24h": float(cached_data.get("volatility", 0.0))
            }
        # If cache is missing or expired, raise to pause signals
        raise Exception(f"Market data failed and no cache available for {asset}: {str(e)}")