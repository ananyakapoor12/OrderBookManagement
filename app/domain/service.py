"""
service.py — business logic orchestrator.

This layer sits between the API routes and the infrastructure.
It owns:
  1. Idempotency check (extra feature #1)
  2. Validation delegation
  3. Order creation and persistence
  4. Routing to the venue simulator
  5. Execution processing loop (fills / partial fills / rejection)
  6. Audit trail writes at every significant step (extra feature #2)
  7. Position updates after each fill

The service never imports FastAPI — it has no knowledge of HTTP.
All errors bubble up as plain Python exceptions; the API layer maps them
to HTTP status codes.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.enums import OrderStatus, OrderSide, SimulationMode, EventType
from app.core.state_machine import transition, IllegalTransitionError
from app.core.validators import validate_order, ValidationError
from app.domain.models import Order, Execution, CreateOrderResult
from app.domain.schemas import CreateOrderRequest
from app.infra import repository
from app.infra.venue_simulator import simulate_venue_response


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

def create_order(req: CreateOrderRequest) -> Order:
    """Backward-compatible helper used by existing service tests and callers."""
    return create_order_with_result(req).order


def create_order_with_result(req: CreateOrderRequest) -> CreateOrderResult:
    """
    Create a new order.

    Idempotency: if an order with the same client_order_id already exists,
    return that order immediately without creating a duplicate.
    This protects against network retries and double-clicks.

    Raises ValidationError if any field check fails.
    """
    # --- Extra feature #1: Idempotency guard ---
    existing = repository.get_order_by_client_id(req.client_order_id)
    if existing:
        repository.insert_audit_event(
            order_id=existing.id,
            event_type=EventType.DUPLICATE_DETECTED.value,
            details=f"Duplicate submission detected for client_order_id={req.client_order_id!r}",
        )
        return CreateOrderResult(order=existing, created=False)

    # --- Validation ---
    try:
        validate_order(req.symbol, req.side.value, req.quantity, req.price, req.client_order_id)
    except ValidationError as exc:
        repository.insert_audit_event(
            order_id=None,
            event_type=EventType.VALIDATION_FAILED.value,
            details=f"client_order_id={req.client_order_id!r} errors: {exc.errors}",
        )
        raise

    # --- Persist ---
    order_id = str(uuid.uuid4())
    now = _now()

    order = Order(
        id=order_id,
        client_order_id=req.client_order_id,
        symbol=req.symbol,
        side=OrderSide(req.side.value),
        quantity=req.quantity,
        price=req.price,
        filled_quantity=0,
        avg_fill_price=None,
        status=OrderStatus.NEW,
        venue=req.venue,
        rejection_reason=None,
        simulate_mode=None,
        created_at=now,
        updated_at=now,
    )

    repository.insert_order(order)
    repository.insert_audit_event(
        order_id=order_id,
        event_type=EventType.ORDER_CREATED.value,
        from_status=None,
        to_status=OrderStatus.NEW.value,
        details=(
            f"symbol={req.symbol} side={req.side.value} "
            f"qty={req.quantity} price={req.price} venue={req.venue}"
        ),
    )

    return CreateOrderResult(order=order, created=True)


# ---------------------------------------------------------------------------
# Order send / execution processing
# ---------------------------------------------------------------------------

def send_order(order_id: str, simulate_mode: SimulationMode = SimulationMode.FULL_FILL) -> Order:
    """
    Transition an order from NEW → SENT, then call the venue simulator.
    Process every execution event returned and update order status accordingly.

    simulate_mode lets the caller control venue behaviour for demos and tests.
    Raises:
        ValueError             — order not found
        IllegalTransitionError — order is not in NEW state
    """
    order = repository.get_order_by_id(order_id)
    if not order:
        raise ValueError(f"Order {order_id!r} not found")

    # NEW → SENT
    sent_status = transition(order.status, OrderStatus.SENT)
    repository.update_order_status(order_id, sent_status, order.filled_quantity, order.avg_fill_price)
    repository.insert_audit_event(
        order_id=order_id,
        event_type=EventType.ORDER_SENT.value,
        from_status=order.status.value,
        to_status=sent_status.value,
        details=f"Routed to venue={order.venue!r} with simulate_mode={simulate_mode.value}",
    )

    # Refresh after status update
    order = repository.get_order_by_id(order_id)

    # --- Call the simulated venue ---
    venue_resp = simulate_venue_response(
        order_id=order_id,
        symbol=order.symbol,
        quantity=order.quantity,
        price=order.price,
        venue=order.venue or "SIMULATED_EXCHANGE",
        mode=simulate_mode,
    )

    # --- Handle rejection ---
    if not venue_resp.accepted:
        rejected_status = transition(order.status, OrderStatus.REJECTED)
        repository.update_order_status(
            order_id, rejected_status, 0, None, venue_resp.rejection_reason
        )
        repository.insert_audit_event(
            order_id=order_id,
            event_type=EventType.ORDER_REJECTED.value,
            from_status=order.status.value,
            to_status=rejected_status.value,
            details=venue_resp.rejection_reason,
        )
        return repository.get_order_by_id(order_id)

    # --- Process fill events ---
    cumulative_filled = 0
    weighted_price_sum = 0.0

    for exec_event in venue_resp.executions:
        cumulative_filled += exec_event.exec_quantity
        weighted_price_sum += exec_event.exec_quantity * exec_event.exec_price

        # Determine the next lifecycle state
        if cumulative_filled >= order.quantity:
            next_status = transition(order.status, OrderStatus.FILLED)
        else:
            next_status = transition(order.status, OrderStatus.PARTIALLY_FILLED)

        avg_fill = round(weighted_price_sum / cumulative_filled, 6)

        # Persist the execution record
        execution = Execution(
            id=exec_event.exec_id,
            order_id=order_id,
            exec_quantity=exec_event.exec_quantity,
            exec_price=exec_event.exec_price,
            venue=exec_event.venue,
            # liquidity_flag: "T" = taker (final fill), "M" = maker (partial)
            liquidity_flag="T" if exec_event.is_final else "M",
            exec_time=exec_event.exec_time,
            cumulative_filled=cumulative_filled,
        )
        repository.insert_execution(execution)

        # Update order status + fill info
        repository.update_order_status(order_id, next_status, cumulative_filled, avg_fill)

        # --- Extra feature #2: Audit trail entry for every execution ---
        repository.insert_audit_event(
            order_id=order_id,
            event_type=EventType.EXECUTION_RECEIVED.value,
            from_status=order.status.value,
            to_status=next_status.value,
            details=(
                f"exec_qty={exec_event.exec_quantity} exec_price={exec_event.exec_price} "
                f"cumulative={cumulative_filled}/{order.quantity}"
            ),
        )

        # Update position table
        repository.upsert_position(
            order.symbol, exec_event.exec_quantity, exec_event.exec_price, order.side
        )

        # Refresh order for next iteration so transitions use the latest status
        order = repository.get_order_by_id(order_id)

    return repository.get_order_by_id(order_id)
