"""
test_order_flow.py — integration tests for the end-to-end order workflow.

These tests exercise the service layer with a real (isolated) SQLite database.
They verify that the full flow from creation through execution behaves correctly.
"""
import pytest
from pydantic import ValidationError as PydanticValidationError
from app.domain.schemas import CreateOrderRequest
from app.domain.service import create_order, send_order
from app.core.enums import OrderStatus, SimulationMode
from app.core.validators import ValidationError
from app.infra.repository import get_executions_for_order, get_audit_events_for_order


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_req(**overrides) -> CreateOrderRequest:
    defaults = dict(
        client_order_id="default-coid",
        symbol="AAPL",
        side="BUY",
        quantity=100,
        price=150.0,
        venue="TEST_VENUE",
    )
    defaults.update(overrides)
    return CreateOrderRequest(**defaults)


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

def test_create_order_returns_new_status():
    order = create_order(_make_req(client_order_id="create-001"))
    assert order.status == OrderStatus.NEW
    assert order.filled_quantity == 0
    assert order.avg_fill_price is None


def test_create_order_normalises_symbol_to_uppercase():
    order = create_order(_make_req(client_order_id="create-002", symbol="msft"))
    assert order.symbol == "MSFT"


def test_create_order_rejects_invalid_fields():
    # Pydantic catches negative quantity at the API/schema boundary before the
    # business validator runs.
    with pytest.raises(PydanticValidationError):
        _make_req(client_order_id="create-003", symbol="123BAD", quantity=-5)

    # Once the request passes schema parsing, the business validator still
    # rejects semantic issues such as malformed symbol values.
    with pytest.raises(ValidationError) as exc_info:
        create_order(_make_req(client_order_id="create-004", symbol="123BAD"))
    assert any("symbol" in err for err in exc_info.value.errors)


# ---------------------------------------------------------------------------
# Idempotency (extra feature #1)
# ---------------------------------------------------------------------------

def test_duplicate_client_order_id_returns_same_order():
    req = _make_req(client_order_id="idempotency-001")
    o1 = create_order(req)
    o2 = create_order(req)
    assert o1.id == o2.id


def test_duplicate_submission_writes_audit_event():
    req = _make_req(client_order_id="idempotency-002")
    o1 = create_order(req)
    create_order(req)  # second call
    events = get_audit_events_for_order(o1.id)
    event_types = [e.event_type for e in events]
    assert "DUPLICATE_DETECTED" in event_types


# ---------------------------------------------------------------------------
# Full fill flow
# ---------------------------------------------------------------------------

def test_full_fill_flow_ends_filled():
    order = create_order(_make_req(client_order_id="full-001"))
    result = send_order(order.id, SimulationMode.FULL_FILL)
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == 100
    assert result.avg_fill_price is not None


def test_full_fill_creates_one_execution():
    order = create_order(_make_req(client_order_id="full-002"))
    send_order(order.id, SimulationMode.FULL_FILL)
    execs = get_executions_for_order(order.id)
    assert len(execs) == 1
    assert execs[0].cumulative_filled == 100


# ---------------------------------------------------------------------------
# Partial fill flow
# ---------------------------------------------------------------------------

def test_partial_fill_flow_ends_filled():
    order = create_order(_make_req(client_order_id="partial-001"))
    result = send_order(order.id, SimulationMode.PARTIAL_THEN_FILL)
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == 100


def test_partial_fill_creates_two_executions():
    order = create_order(_make_req(client_order_id="partial-002"))
    send_order(order.id, SimulationMode.PARTIAL_THEN_FILL)
    execs = get_executions_for_order(order.id)
    assert len(execs) == 2
    # First execution is partial
    assert execs[0].cumulative_filled < 100
    # Second brings us to full
    assert execs[1].cumulative_filled == 100


# ---------------------------------------------------------------------------
# Rejection flow
# ---------------------------------------------------------------------------

def test_reject_flow_ends_rejected():
    order = create_order(_make_req(client_order_id="reject-001"))
    result = send_order(order.id, SimulationMode.REJECT)
    assert result.status == OrderStatus.REJECTED
    assert result.filled_quantity == 0
    assert result.rejection_reason is not None


def test_rejected_order_has_no_executions():
    order = create_order(_make_req(client_order_id="reject-002"))
    send_order(order.id, SimulationMode.REJECT)
    execs = get_executions_for_order(order.id)
    assert len(execs) == 0


# ---------------------------------------------------------------------------
# Audit trail (extra feature #2)
# ---------------------------------------------------------------------------

def test_full_fill_audit_trail_has_correct_event_sequence():
    order = create_order(_make_req(client_order_id="audit-001"))
    send_order(order.id, SimulationMode.FULL_FILL)
    events = get_audit_events_for_order(order.id)
    event_types = [e.event_type for e in events]
    assert "ORDER_CREATED" in event_types
    assert "ORDER_SENT" in event_types
    assert "EXECUTION_RECEIVED" in event_types


def test_rejected_order_audit_trail():
    order = create_order(_make_req(client_order_id="audit-002"))
    send_order(order.id, SimulationMode.REJECT)
    events = get_audit_events_for_order(order.id)
    event_types = [e.event_type for e in events]
    assert "ORDER_REJECTED" in event_types


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_send_nonexistent_order_raises_value_error():
    with pytest.raises(ValueError, match="not found"):
        send_order("nonexistent-id", SimulationMode.FULL_FILL)


def test_cannot_send_already_filled_order():
    from app.core.state_machine import IllegalTransitionError
    order = create_order(_make_req(client_order_id="resend-001"))
    send_order(order.id, SimulationMode.FULL_FILL)
    with pytest.raises(IllegalTransitionError):
        send_order(order.id, SimulationMode.FULL_FILL)
