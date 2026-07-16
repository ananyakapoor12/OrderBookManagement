"""
orders.py — HTTP routes for order creation, sending, querying, and audit trail.

Route summary
-------------
POST   /orders/                       Create a new order (idempotent on client_order_id)
POST   /orders/{order_id}/send        Transition NEW→SENT and process venue response
GET    /orders/                        List all orders
GET    /orders/{order_id}             Fetch a single order by internal ID
GET    /orders/{order_id}/events      Full audit trail for an order (extra feature #2)
GET    /orders/{order_id}/executions  All execution fills for an order
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.enums import SimulationMode
from app.core.state_machine import IllegalTransitionError
from app.core.validators import ValidationError
from app.domain import schemas, service
from app.infra import repository

router = APIRouter(prefix="/orders", tags=["Orders"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order_to_response(order) -> schemas.OrderResponse:
    return schemas.OrderResponse(
        id=order.id,
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side=order.side.value,
        quantity=order.quantity,
        price=order.price,
        filled_quantity=order.filled_quantity,
        avg_fill_price=order.avg_fill_price,
        status=order.status.value,
        venue=order.venue,
        rejection_reason=order.rejection_reason,
        simulate_mode=order.simulate_mode,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=schemas.OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
    description=(
        "Creates a new order in NEW status. "
        "Submitting the same `client_order_id` twice returns the original order (idempotent) "
        "with HTTP 200 instead of creating a duplicate."
    ),
)
def create_order(req: schemas.CreateOrderRequest, response: Response):
    try:
        result = service.create_order_with_result(req)
        response.status_code = (
            status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        )
        return _order_to_response(result.order)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": exc.errors},
        )


@router.post(
    "/{order_id}/send",
    response_model=schemas.OrderResponse,
    summary="Send order to venue",
    description=(
        "Transitions the order from NEW → SENT, calls the simulated venue, "
        "and processes fill/rejection events. "
        "Use `simulate_mode` to control the venue's response."
    ),
)
def send_order(
    order_id: str,
    simulate_mode: SimulationMode = Query(
        default=SimulationMode.FULL_FILL,
        description="Controls venue simulation behaviour",
    ),
):
    try:
        order = service.send_order(order_id, simulate_mode)
        return _order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/",
    response_model=list[schemas.OrderResponse],
    summary="List all orders",
)
def list_orders():
    return [_order_to_response(o) for o in repository.list_all_orders()]


@router.get(
    "/{order_id}",
    response_model=schemas.OrderResponse,
    summary="Get a single order",
)
def get_order(order_id: str):
    order = repository.get_order_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id!r} not found",
        )
    return _order_to_response(order)


@router.get(
    "/{order_id}/events",
    response_model=list[schemas.AuditEventResponse],
    summary="Get full audit trail for an order",
    description=(
        "Returns every lifecycle event recorded for the order: "
        "creation, routing, executions, rejections, and duplicate detections."
    ),
)
def get_order_events(order_id: str):
    # Verify the order exists first
    if not repository.get_order_by_id(order_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id!r} not found",
        )
    events = repository.get_audit_events_for_order(order_id)
    return [
        schemas.AuditEventResponse(
            id=e.id,
            order_id=e.order_id,
            event_type=e.event_type,
            from_status=e.from_status,
            to_status=e.to_status,
            details=e.details,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get(
    "/{order_id}/executions",
    response_model=list[schemas.ExecutionResponse],
    summary="Get all execution fills for an order",
)
def get_order_executions(order_id: str):
    if not repository.get_order_by_id(order_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id!r} not found",
        )
    executions = repository.get_executions_for_order(order_id)
    return [
        schemas.ExecutionResponse(
            id=e.id,
            order_id=e.order_id,
            exec_quantity=e.exec_quantity,
            exec_price=e.exec_price,
            venue=e.venue,
            liquidity_flag=e.liquidity_flag,
            exec_time=e.exec_time,
            cumulative_filled=e.cumulative_filled,
        )
        for e in executions
    ]
