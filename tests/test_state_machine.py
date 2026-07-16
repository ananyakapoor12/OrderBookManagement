"""
test_state_machine.py — unit tests for the lifecycle state machine.

Every allowed and disallowed transition is tested explicitly.
This makes the rules visible as executable documentation.
"""
import pytest
from app.core.state_machine import transition, IllegalTransitionError
from app.core.enums import OrderStatus


# --- Legal transitions ---

def test_new_to_sent():
    assert transition(OrderStatus.NEW, OrderStatus.SENT) == OrderStatus.SENT


def test_new_to_rejected():
    assert transition(OrderStatus.NEW, OrderStatus.REJECTED) == OrderStatus.REJECTED


def test_sent_to_partially_filled():
    assert transition(OrderStatus.SENT, OrderStatus.PARTIALLY_FILLED) == OrderStatus.PARTIALLY_FILLED


def test_sent_to_filled():
    assert transition(OrderStatus.SENT, OrderStatus.FILLED) == OrderStatus.FILLED


def test_sent_to_rejected():
    assert transition(OrderStatus.SENT, OrderStatus.REJECTED) == OrderStatus.REJECTED


def test_partially_filled_to_partially_filled():
    """Multiple partial fills arriving sequentially must be allowed."""
    assert transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED) == OrderStatus.PARTIALLY_FILLED


def test_partially_filled_to_filled():
    assert transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED) == OrderStatus.FILLED


# --- Illegal transitions ---

def test_new_to_filled_is_illegal():
    """Cannot jump directly from NEW to FILLED — must go through SENT."""
    with pytest.raises(IllegalTransitionError):
        transition(OrderStatus.NEW, OrderStatus.FILLED)


def test_new_to_partially_filled_is_illegal():
    with pytest.raises(IllegalTransitionError):
        transition(OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)


def test_filled_is_terminal():
    """FILLED is a terminal state — no transitions out."""
    for target in OrderStatus:
        if target != OrderStatus.FILLED:
            with pytest.raises(IllegalTransitionError):
                transition(OrderStatus.FILLED, target)


def test_rejected_is_terminal():
    """REJECTED is a terminal state — no transitions out."""
    for target in OrderStatus:
        with pytest.raises(IllegalTransitionError):
            transition(OrderStatus.REJECTED, target)


def test_partially_filled_to_rejected_is_illegal():
    """Once partially filled, a venue cannot retroactively reject."""
    with pytest.raises(IllegalTransitionError):
        transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.REJECTED)


def test_error_message_includes_current_and_target():
    """The error message should name both states to aid debugging."""
    try:
        transition(OrderStatus.FILLED, OrderStatus.SENT)
    except IllegalTransitionError as exc:
        assert "FILLED" in str(exc)
        assert "SENT" in str(exc)
