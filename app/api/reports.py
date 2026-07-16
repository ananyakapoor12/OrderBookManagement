"""
reports.py — HTTP routes for post-trade reporting and reconciliation.

Route summary
-------------
POST  /reports/trade-file   Generate and download a trade execution CSV
GET   /reports/positions    Return the current net position book as JSON
POST  /reports/reconcile    Run reconciliation checks and return pass/fail results
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.reporting import trade_file, position_report, reconciliation

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post(
    "/trade-file",
    summary="Generate trade file CSV",
    description=(
        "Exports all execution records to a timestamped CSV file "
        "suitable for sending to a prime broker or fund administrator."
    ),
)
def generate_trade_file():
    path = trade_file.generate()
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(
            status_code=404,
            detail="No executions found. Submit and send at least one order first.",
        )
    return FileResponse(
        path=path,
        media_type="text/csv",
        filename=os.path.basename(path),
    )


@router.get(
    "/positions",
    summary="Get current position book",
    description="Returns net quantity and average cost for every symbol with executed trades.",
)
def get_positions():
    return position_report.generate()


@router.post(
    "/reconcile",
    summary="Run post-trade reconciliation",
    description=(
        "Checks that internal order fill totals match the sum of execution records. "
        "Returns an overall PASS/FAIL verdict plus a per-order breakdown."
    ),
)
def run_reconciliation():
    return reconciliation.run()
