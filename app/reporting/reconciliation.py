"""
reconciliation.py — post-trade reconciliation checks.

Reconciliation is a core operational control in every fund.
It ensures that what the OMS believes happened matches what was actually executed.

Checks performed
----------------
1. filled_quantity_vs_executions
   The `filled_quantity` column on the orders table must equal the sum of all
   execution quantities for that order. A mismatch indicates a data integrity bug.

2. filled_status_vs_full_quantity
   An order in FILLED status must have filled_quantity == quantity.
   A FILLED order with a residual open quantity is an unacceptable break.

In production you would also reconcile:
- Against the prime broker's execution report (give-up / take-up matching)
- Against the custodian's settlement records (T+1 / T+2)
- Currency and commission fields
"""
from datetime import datetime, timezone

from app.core.enums import OrderStatus
from app.infra.repository import list_all_orders, get_executions_for_order


def run() -> dict:
    """
    Run all reconciliation checks and return a structured report.
    Covers every FILLED or PARTIALLY_FILLED order in the system.
    """
    orders = list_all_orders()
    checks: list[dict] = []
    failure_count = 0

    eligible_statuses = {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED}

    for order in orders:
        if order.status not in eligible_statuses:
            continue

        executions = get_executions_for_order(order.id)
        summed_exec_qty = sum(e.exec_quantity for e in executions)

        # --- Check 1: filled_quantity == sum(exec_quantity) ---
        qty_match = order.filled_quantity == summed_exec_qty
        if not qty_match:
            failure_count += 1

        checks.append(
            {
                "check_name": "filled_quantity_vs_executions",
                "order_id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "order_filled_qty": order.filled_quantity,
                "sum_exec_qty": summed_exec_qty,
                "result": "PASS" if qty_match else "FAIL",
                "details": (
                    ""
                    if qty_match
                    else (
                        f"BREAK: order.filled_quantity={order.filled_quantity} "
                        f"but executions sum to {summed_exec_qty}"
                    )
                ),
            }
        )

        # --- Check 2: FILLED orders must be fully filled ---
        if order.status == OrderStatus.FILLED:
            fully_filled = order.filled_quantity == order.quantity
            if not fully_filled:
                failure_count += 1

            checks.append(
                {
                    "check_name": "filled_status_vs_full_quantity",
                    "order_id": order.id,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "expected_qty": order.quantity,
                    "filled_qty": order.filled_quantity,
                    "result": "PASS" if fully_filled else "FAIL",
                    "details": (
                        ""
                        if fully_filled
                        else (
                            f"BREAK: FILLED order has only {order.filled_quantity} "
                            f"of {order.quantity} filled"
                        )
                    ),
                }
            )

    return {
        "report_type": "RECONCILIATION_REPORT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_result": "PASS" if failure_count == 0 else "FAIL",
        "total_checks": len(checks),
        "passed": len(checks) - failure_count,
        "failures": failure_count,
        "checks": checks,
    }
