"""
repository.py — all database read/write operations.

Design rule: every function opens its own connection and closes it on return.
This keeps the code simple and safe for a prototype; in production you would
use a connection pool (e.g. SQLAlchemy with asyncpg or psycopg3).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.infra.db import get_connection
from app.domain.models import Order, Execution, Position, AuditEvent
from app.core.enums import OrderStatus, OrderSide


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_order(row) -> Order:
    return Order(
        id=row["id"],
        client_order_id=row["client_order_id"],
        symbol=row["symbol"],
        side=OrderSide(row["side"]),
        quantity=row["quantity"],
        price=row["price"],
        filled_quantity=row["filled_quantity"],
        avg_fill_price=row["avg_fill_price"],
        status=OrderStatus(row["status"]),
        venue=row["venue"],
        rejection_reason=row["rejection_reason"],
        simulate_mode=row["simulate_mode"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_execution(row) -> Execution:
    return Execution(
        id=row["id"],
        order_id=row["order_id"],
        exec_quantity=row["exec_quantity"],
        exec_price=row["exec_price"],
        venue=row["venue"],
        liquidity_flag=row["liquidity_flag"],
        exec_time=row["exec_time"],
        cumulative_filled=row["cumulative_filled"],
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def insert_order(order: Order) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO orders (
            id, client_order_id, symbol, side, quantity, price,
            filled_quantity, avg_fill_price, status, venue,
            rejection_reason, simulate_mode, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order.id, order.client_order_id, order.symbol, order.side.value,
            order.quantity, order.price, order.filled_quantity,
            order.avg_fill_price, order.status.value, order.venue,
            order.rejection_reason, order.simulate_mode,
            order.created_at, order.updated_at,
        ),
    )
    conn.commit()
    conn.close()


def get_order_by_id(order_id: str) -> Optional[Order]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return _row_to_order(row) if row else None


def get_order_by_client_id(client_order_id: str) -> Optional[Order]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
    ).fetchone()
    conn.close()
    return _row_to_order(row) if row else None


def update_order_status(
    order_id: str,
    status: OrderStatus,
    filled_qty: int,
    avg_fill_price: Optional[float],
    rejection_reason: Optional[str] = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE orders
        SET status = ?, filled_quantity = ?, avg_fill_price = ?,
            rejection_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (status.value, filled_qty, avg_fill_price, rejection_reason, _now(), order_id),
    )
    conn.commit()
    conn.close()


def list_all_orders() -> list[Order]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_order(r) for r in rows]


# ---------------------------------------------------------------------------
# Executions
# ---------------------------------------------------------------------------

def insert_execution(execution: Execution) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO executions (
            id, order_id, exec_quantity, exec_price, venue,
            liquidity_flag, exec_time, cumulative_filled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            execution.id, execution.order_id, execution.exec_quantity,
            execution.exec_price, execution.venue, execution.liquidity_flag,
            execution.exec_time, execution.cumulative_filled,
        ),
    )
    conn.commit()
    conn.close()


def get_executions_for_order(order_id: str) -> list[Execution]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM executions WHERE order_id = ? ORDER BY exec_time",
        (order_id,),
    ).fetchall()
    conn.close()
    return [_row_to_execution(r) for r in rows]


def get_all_executions() -> list[Execution]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM executions ORDER BY exec_time"
    ).fetchall()
    conn.close()
    return [_row_to_execution(r) for r in rows]


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def upsert_position(
    symbol: str,
    qty_delta: int,
    exec_price: float,
    side: OrderSide,
) -> None:
    """
    Update the net position for a symbol after an execution.

    Position logic (simplified netting):
    - BUY  → add qty_delta to net_quantity
    - SELL → subtract qty_delta from net_quantity
    - avg_price is recalculated only when adding to an open position in the
      same direction (i.e. increasing a long or increasing a short).
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM positions WHERE symbol = ?", (symbol,)
    ).fetchone()
    now = _now()

    if row is None:
        net_qty = qty_delta if side == OrderSide.BUY else -qty_delta
        avg_price = exec_price if net_qty != 0 else 0.0
        conn.execute(
            "INSERT INTO positions (symbol, net_quantity, avg_price, updated_at) VALUES (?, ?, ?, ?)",
            (symbol, net_qty, avg_price, now),
        )
    else:
        current_qty: int = row["net_quantity"]
        current_avg: float = row["avg_price"]

        if side == OrderSide.BUY:
            new_qty = current_qty + qty_delta
            if current_qty >= 0 and new_qty != 0:
                # Increasing a long position: weighted average cost
                new_avg = (current_qty * current_avg + qty_delta * exec_price) / new_qty
            elif new_qty > 0:
                new_avg = exec_price  # Flipped from short to long
            else:
                new_avg = current_avg  # Still short; keep old avg
        else:  # SELL
            new_qty = current_qty - qty_delta
            if current_qty <= 0 and new_qty != 0:
                # Increasing a short position: weighted average
                new_avg = (abs(current_qty) * current_avg + qty_delta * exec_price) / abs(new_qty)
            elif new_qty < 0:
                new_avg = exec_price  # Flipped from long to short
            else:
                new_avg = current_avg  # Still long; keep old avg

        new_avg = round(new_avg, 6) if new_qty != 0 else 0.0
        conn.execute(
            "UPDATE positions SET net_quantity = ?, avg_price = ?, updated_at = ? WHERE symbol = ?",
            (new_qty, new_avg, now, symbol),
        )

    conn.commit()
    conn.close()


def get_all_positions() -> list[Position]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM positions").fetchall()
    conn.close()
    return [
        Position(
            symbol=r["symbol"],
            net_quantity=r["net_quantity"],
            avg_price=r["avg_price"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------

def insert_audit_event(
    order_id: Optional[str],
    event_type: str,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO audit_events (id, order_id, event_type, from_status, to_status, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), order_id, event_type, from_status, to_status, details, _now()),
    )
    conn.commit()
    conn.close()


def get_audit_events_for_order(order_id: str) -> list[AuditEvent]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_events WHERE order_id = ? ORDER BY created_at",
        (order_id,),
    ).fetchall()
    conn.close()
    return [
        AuditEvent(
            id=row["id"],
            order_id=row["order_id"],
            event_type=row["event_type"],
            from_status=row["from_status"],
            to_status=row["to_status"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
