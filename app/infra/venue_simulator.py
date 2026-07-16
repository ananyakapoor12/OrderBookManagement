"""
venue_simulator.py — mocked external trading venue.

In a real OMS this would be a FIX gateway, REST call, or message queue consumer.
Here we return deterministic execution responses so the rest of the system
(execution processing, state transitions, reporting) can be tested cleanly.

Simulation modes
----------------
FULL_FILL         — single execution for the entire order quantity
PARTIAL_THEN_FILL — two executions: first 40 %, then remaining 60 %
REJECT            — order is declined by the venue (no executions)
RANDOM            — weighted random selection among the above three
"""
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.core.enums import SimulationMode


@dataclass
class VenueExecution:
    exec_id: str
    exec_quantity: int
    exec_price: float
    venue: str
    exec_time: str
    is_final: bool  # True on the last fill that closes the order
    rejection_reason: Optional[str] = None


@dataclass
class VenueResponse:
    accepted: bool
    executions: list[VenueExecution] = field(default_factory=list)
    rejection_reason: Optional[str] = None


def simulate_venue_response(
    order_id: str,
    symbol: str,
    quantity: int,
    price: float,
    venue: str,
    mode: SimulationMode,
) -> VenueResponse:
    """
    Return a simulated venue response for the given order parameters.
    Prices include a tiny random slippage (±0.05 %) to look realistic.
    """
    now = datetime.now(timezone.utc).isoformat()

    if mode == SimulationMode.REJECT:
        return VenueResponse(
            accepted=False,
            rejection_reason="Order rejected by venue: insufficient liquidity at requested price",
        )

    if mode == SimulationMode.FULL_FILL:
        return VenueResponse(
            accepted=True,
            executions=[
                VenueExecution(
                    exec_id=str(uuid.uuid4()),
                    exec_quantity=quantity,
                    exec_price=_apply_slippage(price),
                    venue=venue,
                    exec_time=now,
                    is_final=True,
                )
            ],
        )

    if mode == SimulationMode.PARTIAL_THEN_FILL:
        first_qty = max(1, int(quantity * 0.4))
        second_qty = quantity - first_qty
        return VenueResponse(
            accepted=True,
            executions=[
                VenueExecution(
                    exec_id=str(uuid.uuid4()),
                    exec_quantity=first_qty,
                    exec_price=_apply_slippage(price),
                    venue=venue,
                    exec_time=now,
                    is_final=False,
                ),
                VenueExecution(
                    exec_id=str(uuid.uuid4()),
                    exec_quantity=second_qty,
                    exec_price=_apply_slippage(price),
                    venue=venue,
                    exec_time=datetime.now(timezone.utc).isoformat(),
                    is_final=True,
                ),
            ],
        )

    if mode == SimulationMode.RANDOM:
        chosen = random.choices(
            [SimulationMode.FULL_FILL, SimulationMode.PARTIAL_THEN_FILL, SimulationMode.REJECT],
            weights=[0.60, 0.30, 0.10],
        )[0]
        return simulate_venue_response(order_id, symbol, quantity, price, venue, chosen)

    # Fallback — treat anything unknown as a full fill
    return simulate_venue_response(order_id, symbol, quantity, price, venue, SimulationMode.FULL_FILL)


def _apply_slippage(price: float) -> float:
    """Add tiny random slippage (±0.05 %) to simulate realistic execution prices."""
    return round(price * (1 + random.uniform(-0.0005, 0.0005)), 4)
