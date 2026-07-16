import sqlite3
import app.core.config as config


def get_connection() -> sqlite3.Connection:
    """
    Open a connection to the SQLite database defined in config.
    - row_factory=sqlite3.Row lets us access columns by name.
    - WAL journal mode improves concurrent read performance.
    - Foreign key enforcement is off by default in SQLite; we enable it per connection.
    """
    conn = sqlite3.connect(config.DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    Create all tables if they do not already exist.
    Safe to call on every startup — uses IF NOT EXISTS.
    """
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id                TEXT PRIMARY KEY,
            client_order_id   TEXT UNIQUE NOT NULL,
            symbol            TEXT NOT NULL,
            side              TEXT NOT NULL,
            quantity          INTEGER NOT NULL,
            price             REAL NOT NULL,
            filled_quantity   INTEGER NOT NULL DEFAULT 0,
            avg_fill_price    REAL,
            status            TEXT NOT NULL,
            venue             TEXT,
            rejection_reason  TEXT,
            simulate_mode     TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS executions (
            id                TEXT PRIMARY KEY,
            order_id          TEXT NOT NULL,
            exec_quantity     INTEGER NOT NULL,
            exec_price        REAL NOT NULL,
            venue             TEXT NOT NULL,
            liquidity_flag    TEXT,
            exec_time         TEXT NOT NULL,
            cumulative_filled INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS positions (
            symbol       TEXT PRIMARY KEY,
            net_quantity INTEGER NOT NULL,
            avg_price    REAL NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id          TEXT PRIMARY KEY,
            order_id    TEXT,
            event_type  TEXT NOT NULL,
            from_status TEXT,
            to_status   TEXT,
            details     TEXT,
            created_at  TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()
