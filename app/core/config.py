import os

# SQLite file path; override via env var for testing or deployment
DATABASE_URL: str = os.getenv("DATABASE_URL", "oms.db")

# Hard limits applied during order validation
MAX_ORDER_QUANTITY: int = int(os.getenv("MAX_ORDER_QUANTITY", 10_000_000))
MAX_ORDER_NOTIONAL: float = float(os.getenv("MAX_ORDER_NOTIONAL", 500_000_000.0))

# Directory where generated CSV reports are written
REPORTS_DIR: str = os.getenv("REPORTS_DIR", "reports")
