"""
models.py — plain Python dataclasses used as in-memory representations of DB rows.

These are NOT Pydantic models — they do not validate on assignment.
Keeping them as simple dataclasses means we pay no serialisation overhead
when the data is only being passed between repository functions and the service.
Pydantic schemas (schemas.py) are used only at the API boundary.
"""
from dataclasses import dataclass
from typing import Optional

from app.core.enums import OrderStatus, OrderSide


@dataclass
class Order:
    id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    filled_quantity: int
    avg_fill_price: Optional[float]
    status: OrderStatus
    venue: Optional[str]
    rejection_reason: Optional[str]
    simulate_mode: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class Execution:
    id: str
    order_id: str
    exec_quantity: int
    exec_price: float
    venue: str
    liquidity_flag: Optional[str]
    exec_time: str
    cumulative_filled: int


@dataclass
class Position:
    symbol: str
    net_quantity: int
    avg_price: float
    updated_at: str


@dataclass
class AuditEvent:
    id: str
    order_id: Optional[str]
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    details: Optional[str]
    created_at: str
