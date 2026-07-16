"""
trade_file.py — generate a trade execution CSV for prime broker / fund admin.

Each row represents a single execution event. The file name is timestamped so
multiple runs during the day produce separate artefacts rather than overwriting.

In production this file would typically be:
- PGP-encrypted before transmission
- Delivered over SFTP or a secure API endpoint
- Formatted to the broker's specific FIX or CSV template
"""
import csv
import os
from datetime import datetime, timezone

import app.core.config as config
from app.infra.repository import get_all_executions, get_order_by_id

# Columns in the trade file (matches typical PB format)
COLUMNS = [
    "execution_id",
    "order_id",
    "client_order_id",
    "symbol",
    "side",
    "exec_quantity",
    "exec_price",
    "notional_value",
    "venue",
    "liquidity_flag",
    "exec_time",
    "cumulative_filled",
]


def generate() -> str:
    """
    Write all execution records to a CSV file and return the file path.
    Creates an empty file (with headers only) if there are no executions yet.
    """
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(config.REPORTS_DIR, f"trade_file_{timestamp}.csv")

    executions = get_all_executions()

    with open(filepath, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()

        for ex in executions:
            order = get_order_by_id(ex.order_id)
            writer.writerow(
                {
                    "execution_id": ex.id,
                    "order_id": ex.order_id,
                    "client_order_id": order.client_order_id if order else "",
                    "symbol": order.symbol if order else "",
                    "side": order.side.value if order else "",
                    "exec_quantity": ex.exec_quantity,
                    "exec_price": ex.exec_price,
                    "notional_value": round(ex.exec_quantity * ex.exec_price, 2),
                    "venue": ex.venue,
                    "liquidity_flag": ex.liquidity_flag or "",
                    "exec_time": ex.exec_time,
                    "cumulative_filled": ex.cumulative_filled,
                }
            )

    return filepath
