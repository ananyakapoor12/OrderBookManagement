from enum import Enum


class OrderStatus(str, Enum):
    """All valid lifecycle states for an order."""
    NEW = "NEW"
    SENT = "SENT"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SimulationMode(str, Enum):
    """Controls how the mock venue responds when an order is sent."""
    FULL_FILL = "FULL_FILL"
    PARTIAL_THEN_FILL = "PARTIAL_THEN_FILL"
    REJECT = "REJECT"
    RANDOM = "RANDOM"


class EventType(str, Enum):
    """Categories written to the audit_events table."""
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_SENT = "ORDER_SENT"
    EXECUTION_RECEIVED = "EXECUTION_RECEIVED"
    ORDER_REJECTED = "ORDER_REJECTED"
    STATUS_TRANSITION = "STATUS_TRANSITION"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DUPLICATE_DETECTED = "DUPLICATE_DETECTED"
