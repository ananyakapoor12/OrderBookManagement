from app.core.enums import OrderStatus

# Every key maps to the set of states that key is allowed to move INTO.
# Any transition not listed here is illegal and will raise immediately.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.SENT, OrderStatus.REJECTED},
    OrderStatus.SENT: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,  # more partials can arrive
        OrderStatus.FILLED,
    },
    # FILLED and REJECTED are terminal — nothing can leave them
}


class IllegalTransitionError(Exception):
    """Raised when a state transition is not permitted by the lifecycle rules."""


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    """
    Validate and apply a single state transition.

    Returns the target status on success.
    Raises IllegalTransitionError if the move is not allowed.
    """
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        allowed_labels = [s.value for s in allowed] if allowed else []
        raise IllegalTransitionError(
            f"Cannot transition from {current.value!r} to {target.value!r}. "
            f"Allowed targets from {current.value!r}: {allowed_labels}"
        )
    return target
