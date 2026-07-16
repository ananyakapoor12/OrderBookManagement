"""
test_validation.py — unit tests for the order validation layer.

These tests exercise every rule in validators.py independently.
No DB or HTTP layer is involved.
"""
import pytest
from app.core.validators import validate_order, ValidationError


def test_valid_order_passes():
    """A well-formed order should raise nothing."""
    validate_order("AAPL", "BUY", 100, 150.0, "client-001")


def test_valid_sell_order_passes():
    validate_order("MSFT", "SELL", 50, 300.0, "client-002")


# --- symbol ---

def test_symbol_with_digits_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL123", "BUY", 100, 150.0, "client-003")
    assert any("symbol" in e for e in exc_info.value.errors)


def test_symbol_too_long_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("TOOLONGSYMBOL", "BUY", 100, 150.0, "client-004")
    assert any("symbol" in e for e in exc_info.value.errors)


def test_empty_symbol_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("", "BUY", 100, 150.0, "client-005")
    assert any("symbol" in e for e in exc_info.value.errors)


# --- side ---

def test_invalid_side_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "HOLD", 100, 150.0, "client-006")
    assert any("side" in e for e in exc_info.value.errors)


def test_lowercase_side_is_valid():
    """Validation should accept lowercase since we normalise to upper internally."""
    validate_order("AAPL", "buy", 100, 150.0, "client-007")


# --- quantity ---

def test_zero_quantity_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 0, 150.0, "client-008")
    assert any("quantity" in e for e in exc_info.value.errors)


def test_negative_quantity_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", -10, 150.0, "client-009")
    assert any("quantity" in e for e in exc_info.value.errors)


def test_quantity_exceeds_cap_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 10_000_001, 1.0, "client-010")
    assert any("quantity" in e for e in exc_info.value.errors)


# --- price ---

def test_zero_price_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 100, 0.0, "client-011")
    assert any("price" in e for e in exc_info.value.errors)


def test_negative_price_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 100, -50.0, "client-012")
    assert any("price" in e for e in exc_info.value.errors)


# --- notional cap ---

def test_notional_exceeds_cap_is_rejected():
    # 5_000_000 shares × $200 = $1B  >  $500M cap
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 5_000_000, 200.0, "client-013")
    assert len(exc_info.value.errors) > 0


# --- client_order_id ---

def test_blank_client_order_id_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 100, 150.0, "")
    assert any("client_order_id" in e for e in exc_info.value.errors)


def test_whitespace_client_order_id_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        validate_order("AAPL", "BUY", 100, 150.0, "   ")
    assert any("client_order_id" in e for e in exc_info.value.errors)


# --- multiple errors at once ---

def test_multiple_violations_returned_together():
    """All errors should be collected in one pass, not fail-fast."""
    with pytest.raises(ValidationError) as exc_info:
        validate_order("", "HOLD", -1, -1.0, "")
    assert len(exc_info.value.errors) >= 4
