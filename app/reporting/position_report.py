"""
position_report.py — generate an end-of-day (or on-demand) position snapshot.

The position book is maintained live in the `positions` table after every
execution. This module reads it and enriches each row with a notional value
placeholder (market price is not available in a prototype; in production you
would multiply net_quantity by the last available market price from a data feed).

In a real fund this report would be:
- Sent to the fund administrator for NAV calculation
- Compared against the prime broker's position statement for reconciliation
- Used by the risk team for exposure monitoring
"""
from datetime import datetime, timezone

from app.infra.repository import get_all_positions


def generate() -> dict:
    """
    Return a structured position report as a Python dict (serialised to JSON
    by FastAPI automatically).
    """
    positions = get_all_positions()
    report_time = datetime.now(timezone.utc).isoformat()

    rows = []
    total_long_notional = 0.0
    total_short_notional = 0.0

    for pos in positions:
        notional = round(pos.net_quantity * pos.avg_price, 2)
        direction = "LONG" if pos.net_quantity > 0 else ("SHORT" if pos.net_quantity < 0 else "FLAT")

        if pos.net_quantity > 0:
            total_long_notional += notional
        elif pos.net_quantity < 0:
            total_short_notional += notional

        rows.append(
            {
                "symbol": pos.symbol,
                "net_quantity": pos.net_quantity,
                "direction": direction,
                "avg_price": round(pos.avg_price, 4),
                "notional_value": notional,
                "note": "Market price unavailable in prototype; notional = qty × avg_fill_price",
                "updated_at": pos.updated_at,
            }
        )

    return {
        "report_type": "POSITION_REPORT",
        "generated_at": report_time,
        "total_positions": len(rows),
        "total_long_notional": round(total_long_notional, 2),
        "total_short_notional": round(total_short_notional, 2),
        "net_notional": round(total_long_notional + total_short_notional, 2),
        "positions": rows,
    }
