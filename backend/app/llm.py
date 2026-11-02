from app.config import settings

_client = None


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
    """
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