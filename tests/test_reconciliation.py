"""
test_reconciliation.py — tests for the post-trade reconciliation checks.
"""
import pytest
from app.domain.schemas import CreateOrderRequest
from app.domain.service import create_order, send_order
from app.core.enums import SimulationMode
from app.reporting.reconciliation import run


def _make_order(coid: str, symbol: str = "AAPL", qty: int = 100, price: float = 150.0) -> object:
    req = CreateOrderRequest(
        client_order_id=coid,
        symbol=symbol,
        side="BUY",
        quantity=qty,
        price=price,
    )
    return create_order(req)


def test_reconciliation_passes_with_no_filled_orders():
    """No eligible orders → empty check list → PASS."""
    result = run()
    assert result["overall_result"] == "PASS"
    assert result["total_checks"] == 0


def test_reconciliation_passes_for_full_fill():
    order = _make_order("recon-full-001")
    send_order(order.id, SimulationMode.FULL_FILL)
    result = run()
    assert result["overall_result"] == "PASS"
    assert result["failures"] == 0


def test_reconciliation_passes_for_partial_then_fill():
    order = _make_order("recon-partial-001")
    send_order(order.id, SimulationMode.PARTIAL_THEN_FILL)
    result = run()
    assert result["overall_result"] == "PASS"
    assert result["failures"] == 0


def test_reconciliation_excludes_rejected_orders():
    """Rejected orders have no fills and should not appear in reconciliation checks."""
    order = _make_order("recon-reject-001")
    send_order(order.id, SimulationMode.REJECT)
    result = run()
    assert result["total_checks"] == 0


def test_reconciliation_passes_for_multiple_symbols():
    for i, symbol in enumerate(["AAPL", "MSFT", "GOOG"]):
        order = _make_order(f"recon-multi-{i}", symbol=symbol)
        send_order(order.id, SimulationMode.FULL_FILL)

    result = run()
    assert result["overall_result"] == "PASS"
    assert result["failures"] == 0


def test_reconciliation_detects_forced_mismatch(monkeypatch):
    """
    Induce a mismatch by directly patching the repository to return a wrong
    filled_quantity, then verify reconciliation catches and flags the break.
    """
    import app.infra.repository as repo
    import app.reporting.reconciliation as recon
    from app.domain.models import Order

    order = _make_order("recon-mismatch-001", qty=100)
    send_order(order.id, SimulationMode.FULL_FILL)

    # Tamper: return an order that claims filled_quantity=50 but execution summed to 100
    original_list = repo.list_all_orders

    def patched_list():
        orders = original_list()
        tampered = []
        for o in orders:
            if o.client_order_id == "recon-mismatch-001":
                # Build a copy with wrong filled_quantity
                o = Order(
                    id=o.id, client_order_id=o.client_order_id,
                    symbol=o.symbol, side=o.side, quantity=o.quantity,
                    price=o.price, filled_quantity=50,  # <-- tampered
                    avg_fill_price=o.avg_fill_price, status=o.status,
                    venue=o.venue, rejection_reason=o.rejection_reason,
                    simulate_mode=o.simulate_mode,
                    created_at=o.created_at, updated_at=o.updated_at,
                )
            tampered.append(o)
        return tampered

    monkeypatch.setattr(repo, "list_all_orders", patched_list)
    monkeypatch.setattr(recon, "list_all_orders", patched_list)

    result = run()
    assert result["overall_result"] == "FAIL"
    assert result["failures"] > 0
    fail_check = next(c for c in result["checks"] if c["result"] == "FAIL")
    assert "BREAK" in fail_check["details"]
