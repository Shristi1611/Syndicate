import json
import re

from app.config import settings

_client = None


def _mock(prompt: str, system: str) -> str:
    """Free, instant, offline stand-in for a real model. Used for testing and demo fallback."""
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


def _get_client():
    """Create the provider client once and reuse it."""
    global _client
    if _client is not None:
        return _client

    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not set in .env")

    if settings.llm_provider == "gemini":
        from google import genai

        _client = genai.Client(api_key=settings.llm_api_key)
    elif settings.llm_provider == "claude":
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.llm_api_key)
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

    return _client


def generate(prompt: str, system: str = "", strong: bool = False) -> str:
    """Send a prompt to the configured model and return the reply text.

    strong=False uses the cheap, fast model (for haggling).
    strong=True uses the stronger model (for final itineraries).
    Set LLM_PROVIDER=mock to run with no API calls at all.
    """
    if settings.llm_provider == "mock":
        return _mock(prompt, system)

    model = settings.llm_strong_model if strong else settings.llm_fast_model
    if not model:
        raise RuntimeError("LLM_FAST_MODEL / LLM_STRONG_MODEL is not set in .env")

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