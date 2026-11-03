import pytest
from fastapi.testclient import TestClient

from app import llm
from app.config import settings
from app.main import app
from app.trip import negotiate_plan

PROFILE = {
    "destination": "Goa",
    "nights": 4,
    "travellers": 3,
    "budget_total": 60000,
    "stairs_free": True,
    "interests": ["quiet"],
}


@pytest.fixture(autouse=True)
def live_model_setup(monkeypatch, tmp_path):
    """Pretend a real provider is configured, with a throwaway cache. The tests fake the model."""
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_fast_model", "fast-model")
    monkeypatch.setattr(settings, "llm_strong_model", "strong-model")
    monkeypatch.setattr(settings, "llm_cache", True)
    monkeypatch.setattr(settings, "llm_fallback", True)
    monkeypatch.setattr(llm, "CACHE_PATH", tmp_path / "cache.db")
    llm.reset()
    yield
    llm.reset()


def test_successful_replies_are_cached(monkeypatch):
    calls = []

    def fake_live(prompt, system, model):
        calls.append(prompt)
        return "hello from the model"

    monkeypatch.setattr(llm, "_live", fake_live)

    assert llm.generate("hi") == "hello from the model"
    assert llm.generate("hi") == "hello from the model"  # replayed from the cache
    assert len(calls) == 1

    status = llm.status()
    assert status["live"] == 1
    assert status["cache"] == 1


def test_a_dead_model_falls_back_to_the_mock(monkeypatch):
    calls = []

    def dead(prompt, system, model):
        calls.append(1)
        raise ConnectionError("no network")

    monkeypatch.setattr(llm, "_live", dead)

    reply = llm.generate("Ask for 5250 rupees per unit", system="x")
    assert "5250" in reply  # the offline mock answered

    # The live model is skipped during the cooldown instead of being tried again.
    llm.generate("Ask for 6000 rupees per unit", system="x")
    assert len(calls) == 1

    status = llm.status()
    assert status["fallback"] == 2
    assert status["offline"] is True


def test_the_model_is_retried_after_the_cooldown(monkeypatch):
    state = {"up": False}

    def flaky(prompt, system, model):
        if not state["up"]:
            raise TimeoutError("slow")
        return "back online"

    monkeypatch.setattr(llm, "_live", flaky)

    llm.generate("Ask for 100 rupees per unit")  # falls back
    assert llm.status()["offline"] is True

    state["up"] = True
    monkeypatch.setattr(llm, "_down_until", 0.0)  # pretend the cooldown has passed
    assert llm.generate("Ask for 200 rupees per unit") == "back online"
    assert llm.status()["offline"] is False


def test_fallback_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "llm_fallback", False)

    def dead(prompt, system, model):
        raise ConnectionError("no network")

    monkeypatch.setattr(llm, "_live", dead)
    with pytest.raises(ConnectionError):
        llm.generate("Ask for 100 rupees per unit")


def test_a_whole_trip_survives_a_dead_model(monkeypatch):
    def dead(prompt, system, model):
        raise TimeoutError("slow")

    monkeypatch.setattr(llm, "_live", dead)

    trip = negotiate_plan(PROFILE)
    assert trip["final_total"] == 39700  # the offline mock negotiates like the mock provider
    assert llm.status()["live"] == 0
    assert llm.status()["fallback"] > 0


def test_missing_key_is_a_config_error_not_a_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.generate("hi")


def test_health_reports_the_model_status():
    body = TestClient(app).get("/health").json()
    assert set(body["llm_calls"]) == {"live", "cache", "fallback", "offline"}