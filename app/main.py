"""
main.py — FastAPI application entry point.

Responsibilities:
- Mount the two API routers (orders, reports)
- Run init_db() on startup so tables exist before any request arrives
- Expose a /health endpoint for quick liveness checks

Run with:
    uvicorn app.main:app --reload
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import orders, reports
from app.infra.db import init_db

app = FastAPI(
    title="Order Management System — Prototype",
    description=(
        "A lightweight OMS prototype demonstrating order creation, lifecycle "
        "management, simulated venue execution, and post-trade reporting."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins for prototype convenience (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Initialise database and report directory on every startup."""
    init_db()
    os.makedirs("reports", exist_ok=True)


app.include_router(orders.router)
app.include_router(reports.router)


@app.get("/health", tags=["System"])
def health():
    """Quick liveness check."""
    return {"status": "ok", "service": "OMS Prototype", "version": "1.0.0"}
