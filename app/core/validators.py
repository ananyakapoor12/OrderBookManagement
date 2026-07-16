import re
import app.core.config as config
from app.core.enums import OrderSide


class ValidationError(Exception):
    """Raised when one or more order fields fail validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_order(
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    client_order_id: str,
) -> None:
    """
    Run all pre-creation checks on an order.
    Collects every violation and raises ValidationError with the full list
    so the caller receives all problems at once rather than one at a time.
    """
    errors: list[str] = []

    # 1. client_order_id must be non-empty (idempotency key)
    if not client_order_id or not client_order_id.strip():
        errors.append("client_order_id is required and cannot be blank")

    # 2. symbol: 1–10 uppercase letters only
    if not symbol or not re.match(r"^[A-Za-z]{1,10}$", symbol):
        errors.append(
            f"symbol must be 1–10 alphabetic characters, got {symbol!r}"
        )

    # 3. side must be BUY or SELL
    try:
        OrderSide(side.upper())
    except (ValueError, AttributeError):
        errors.append(f"side must be BUY or SELL, got {side!r}")

    # 4. quantity: positive integer within allowed cap
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        errors.append("quantity must be a positive integer")
    elif quantity > config.MAX_ORDER_QUANTITY:
        errors.append(
            f"quantity {quantity:,} exceeds the maximum allowed "
            f"{config.MAX_ORDER_QUANTITY:,}"
        )

    # 5. price: positive number
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        errors.append("price must be a positive number")

    # 6. notional cap (only when qty and price individually passed)
    if not errors:
        notional = quantity * price
        if notional > config.MAX_ORDER_NOTIONAL:
            errors.append(
                f"notional {notional:,.2f} exceeds the maximum allowed "
                f"{config.MAX_ORDER_NOTIONAL:,.2f}"
            )

    if errors:
        raise ValidationError(errors)
