from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(title="Syndicate", version="0.1.0")

# Lets the React frontend (added later) talk to this server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_key_configured": bool(settings.llm_api_key),
    }