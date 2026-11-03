import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing

from app.config import ROOT_DIR, settings

CACHE_PATH = ROOT_DIR / "data" / "llm_cache.db"  # ignored by git (*.db)
COOLDOWN_SECONDS = 60  # after a live failure, skip the live model for this long

_client = None
_down_until = 0.0
stats = {"live": 0, "cache": 0, "fallback": 0}


def reset() -> None:
    """Clear the counters and the cooldown. Used by tests."""
    global _down_until
    _down_until = 0.0
    for key in stats:
        stats[key] = 0


def status() -> dict:
    """How the replies were produced, and whether the live model is currently skipped."""
    return {**stats, "offline": time.monotonic() < _down_until}


def _mock(prompt: str, system: str) -> str:
    """Free, instant, offline stand-in for a real model. Used for testing and as the fallback."""
    if "Extract trip details" in system:  # profile extraction
        text = prompt.split("Traveller says:", 1)[-1]
        out = {}
        for city in ("Goa", "Jaipur"):
            if city.lower() in text.lower():
                out["destination"] = city
        m = re.search(r"(\d+)\s*(?:nights?|days?)", text, re.I)
        if m:
            out["nights"] = int(m.group(1))
        m = re.search(r"(\d+)\s*(?:people|persons|travellers|travelers|adults|of us)", text, re.I)
        if m:
            out["travellers"] = int(m.group(1))
        m = re.search(
            r"(?:₹|\brs\.?\s?)\s*(\d[\d,]*)\s*(k?)|(\d[\d,]*)\s*(k?)\s*(?:rupees|rs\b|budget)",
            text,
            re.I,
        )
        if m:
            num = (m.group(1) or m.group(3)).replace(",", "")
            is_k = (m.group(2) or m.group(4) or "").lower() == "k"
            out["budget_total"] = int(num) * (1000 if is_k else 1)
        if re.search(r"stairs|step-free|wheelchair", text, re.I):
            out["stairs_free"] = True
        out["interests"] = [
            w
            for w in ("quiet", "heritage", "food", "nightlife", "beach", "adventure", "romantic", "luxury")
            if w in text.lower()
        ]
        return json.dumps(out)

    if "Reply with JSON only" in system:  # supplier agent
        list_price = int(re.search(r"List price: (\d+)", system).group(1))
        floor = int(re.search(r"lowest price is (\d+)", system).group(1))
        perks = re.search(r"willing to give: (.+?)\. Offer", system).group(1).split(", ")
        rnd = int(re.search(r"Negotiation round (\d+)", prompt).group(1))
        price = max(floor, round(list_price * (1 - 0.07 * rnd), -1))
        perk = perks[0]
        message = f"I can do {int(price)} rupees per unit with {perk.replace('_', ' ')} included."
        return (
            '{"message": "' + message + '", "price": ' + str(int(price))
            + ', "perks": ["' + perk + '"]}'
        )

    # traveller agent
    target = re.search(r"Ask for (\d+) rupees", prompt).group(1)
    return f"We would like {target} rupees per unit with the requested perks, please."


# ------------------------------------------------------------------ cache


def _key(model: str, system: str, prompt: str) -> str:
    raw = json.dumps([settings.llm_provider, model, system, prompt])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_connect() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_cache "
        "(key TEXT PRIMARY KEY, reply TEXT NOT NULL, created REAL NOT NULL)"
    )
    return conn


def _cache_get(key: str) -> str | None:
    try:
        with closing(_cache_connect()) as conn:
            row = conn.execute("SELECT reply FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None  # a broken cache must never break the app


def _cache_put(key: str, reply: str) -> None:
    try:
        with closing(_cache_connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, reply, created) VALUES (?, ?, ?)",
                (key, reply, time.time()),
            )
            conn.commit()
    except sqlite3.Error:
        pass


# ------------------------------------------------------------- live model


def _get_client():
    """Create the provider client once and reuse it."""
    global _client
    if _client is not None:
        return _client

    if settings.llm_provider == "gemini":
        from google import genai
        from google.genai import types

        _client = genai.Client(
            api_key=settings.llm_api_key,
            http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)),
        )
    else:
        import anthropic

        _client = anthropic.Anthropic(
            api_key=settings.llm_api_key, timeout=settings.llm_timeout_seconds
        )
    return _client


def _live(prompt: str, system: str, model: str) -> str:
    """One real call to the configured provider."""
    client = _get_client()

    if settings.llm_provider == "gemini":
        from google.genai import types

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system or None),
        )
        return response.text or ""

    # claude
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


def generate(prompt: str, system: str = "", strong: bool = False) -> str:
    """Send a prompt to the configured model and return the reply text.

    strong=False uses the cheap, fast model (for haggling).
    strong=True uses the stronger model (for final itineraries).

    Order: the free mock when LLM_PROVIDER=mock; otherwise the cache, then the live
    model, then the offline mock if the live model fails.
    """
    global _down_until

    if settings.llm_provider == "mock":
        return _mock(prompt, system)

    # Setup mistakes fail loudly. Only a model that is down falls back.
    if settings.llm_provider not in ("gemini", "claude"):
        raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not set in .env")
    model = settings.llm_strong_model if strong else settings.llm_fast_model
    if not model:
        raise RuntimeError("LLM_FAST_MODEL / LLM_STRONG_MODEL is not set in .env")

    key = _key(model, system, prompt)
    if settings.llm_cache:
        hit = _cache_get(key)
        if hit is not None:
            stats["cache"] += 1
            return hit

    if time.monotonic() >= _down_until:
        try:
            reply = _live(prompt, system, model)
            if not reply.strip():
                raise RuntimeError("empty reply")
            stats["live"] += 1
            if settings.llm_cache:
                _cache_put(key, reply)
            return reply
        except Exception as exc:
            if not settings.llm_fallback:
                raise
            _down_until = time.monotonic() + COOLDOWN_SECONDS
            # Only the error type is printed, never its message.
            print(f"[llm] live model failed ({type(exc).__name__}); offline fallback for {COOLDOWN_SECONDS}s")
    elif not settings.llm_fallback:
        raise RuntimeError("The live model is temporarily unavailable")

    stats["fallback"] += 1
    return _mock(prompt, system)