"""FastAPI application for dashboard and operator UI."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pulse.api.routes import dashboard, runs

load_dotenv()

app = FastAPI(
    title="Product Review Pulse API",
    description="Dashboard and operator endpoints for Groww weekly pulse",
    version="0.1.0",
)

_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(runs.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("pulse.api.main:app", host="0.0.0.0", port=port, reload=False)
