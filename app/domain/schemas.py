"""
schemas.py — Pydantic v2 request/response models used at the API boundary.

These are the only objects that undergo validation on assignment.
They are intentionally separate from the internal dataclasses in models.py.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.core.enums import OrderSide, SimulationMode


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateOrderRequest(BaseModel):
    client_order_id: str = Field(
        ...,
        description="Unique caller-assigned ID used for idempotency. "
                    "Re-submitting with the same ID returns the existing order.",
    )
    symbol: str = Field(..., description="Ticker symbol, e.g. AAPL")
    side: OrderSide = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0, description="Number of shares / contracts")
    price: float = Field(..., gt=0, description="Limit price per share / contract")
    venue: str = Field(default="SIMULATED_EXCHANGE", description="Target execution venue")

    @field_validator("symbol")
    @classmethod
    def normalise_symbol(cls, v: str) -> str:
        return v.upper().strip()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OrderResponse(BaseModel):
    id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    filled_quantity: int
    avg_fill_price: Optional[float]
    status: str
    venue: Optional[str]
    rejection_reason: Optional[str]
    simulate_mode: Optional[str]
    created_at: str
    updated_at: str


class ExecutionResponse(BaseModel):
    id: str
    order_id: str
    exec_quantity: int
    exec_price: float
    venue: str
    liquidity_flag: Optional[str]
    exec_time: str
    cumulative_filled: int


class AuditEventResponse(BaseModel):
    id: str
    order_id: Optional[str]
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    details: Optional[str]
    created_at: str
