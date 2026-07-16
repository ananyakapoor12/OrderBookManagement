"""
main.py — FastAPI application entry point.

Responsibilities:
- Mount the two API routers (orders, reports)
- Run init_db() during app lifespan startup so tables exist before any request arrives
- Expose a /health endpoint for quick liveness checks

Run with:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import orders, reports
from app.infra.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialise runtime resources when the app starts and release none on shutdown."""
    init_db()
    os.makedirs("reports", exist_ok=True)
    yield

app = FastAPI(
    title="Order Management System — Prototype",
    description=(
        "A lightweight OMS prototype demonstrating order creation, lifecycle "
        "management, simulated venue execution, and post-trade reporting."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Allow all origins for prototype convenience (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(orders.router)
app.include_router(reports.router)


@app.get("/health", tags=["System"])
def health():
    """Quick liveness check."""
    return {"status": "ok", "service": "OMS Prototype", "version": "1.0.0"}
