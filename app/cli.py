"""
cli.py — interactive command-line interface for the OMS prototype.

The CLI is meant for local demos and recruiter walkthroughs. It supports both
subcommands and an interactive menu so the user can either type commands
directly or be guided through the workflow step by step.

Run with:
    python -m app
or:
    python -m app.cli
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Optional

from pydantic import ValidationError as PydanticValidationError

from app.core.enums import OrderSide, SimulationMode
from app.core.state_machine import IllegalTransitionError
from app.core.validators import ValidationError
from app.domain.schemas import CreateOrderRequest
from app.domain.service import create_order_with_result, send_order
from app.infra import repository
from app.infra.db import init_db
from app.reporting import position_report, reconciliation, trade_file


def _runtime_setup() -> None:
    """Initialise the SQLite database and output directory if needed."""
    init_db()
    os.makedirs("reports", exist_ok=True)


def _serialize(value: Any) -> Any:
    """Convert dataclasses, enums, and nested structures into JSON-friendly values."""
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, str):
        return value.value
    return value


def _print_json(value: Any) -> None:
    print(json.dumps(_serialize(value), indent=2))


def _prompt(message: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw or (default or "")


def _prompt_int(message: str, default: Optional[int] = None) -> int:
    while True:
        raw = _prompt(message, str(default) if default is not None else None)
        try:
            return int(raw)
        except ValueError:
            print("Enter a valid integer.")


def _prompt_float(message: str, default: Optional[float] = None) -> float:
    while True:
        raw = _prompt(message, str(default) if default is not None else None)
        try:
            return float(raw)
        except ValueError:
            print("Enter a valid number.")


def _prompt_enum(message: str, enum_cls, default: Optional[str] = None):
    while True:
        raw = _prompt(message, default)
        try:
            return enum_cls(raw.upper())
        except ValueError:
            allowed = ", ".join(item.value for item in enum_cls)
            print(f"Enter one of: {allowed}")


def _handle_validation_error(exc: ValidationError) -> int:
    print("Validation failed:")
    for error in exc.errors:
        print(f"- {error}")
    return 1


def _handle_pydantic_validation_error(exc: PydanticValidationError) -> int:
    print("Validation failed:")
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "Invalid input")
        print(f"- {location}: {message}" if location else f"- {message}")
    return 1


def cmd_create(args: argparse.Namespace) -> int:
    try:
        req = CreateOrderRequest(
            client_order_id=args.client_order_id,
            symbol=args.symbol,
            side=args.side,
            quantity=args.quantity,
            price=args.price,
            venue=args.venue,
        )
        result = create_order_with_result(req)
    except PydanticValidationError as exc:
        return _handle_pydantic_validation_error(exc)
    except ValidationError as exc:
        return _handle_validation_error(exc)

    print("Order created" if result.created else "Existing order returned")
    _print_json(result.order)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    try:
        order = send_order(args.order_id, args.simulate_mode)
    except IllegalTransitionError as exc:
        print(f"Error: {exc}")
        print("Tip: choose a NEW order that has not already been sent or filled.")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI should surface the message cleanly
        print(f"Error: {exc}")
        return 1

    _print_json(order)
    return 0


def cmd_list_orders(_: argparse.Namespace) -> int:
    _print_json(repository.list_all_orders())
    return 0


def cmd_get_order(args: argparse.Namespace) -> int:
    order = repository.get_order_by_id(args.order_id)
    if not order:
        print(f"Order {args.order_id!r} not found")
        return 1
    _print_json(order)
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    if not repository.get_order_by_id(args.order_id):
        print(f"Order {args.order_id!r} not found")
        return 1
    _print_json(repository.get_audit_events_for_order(args.order_id))
    return 0


def cmd_executions(args: argparse.Namespace) -> int:
    if not repository.get_order_by_id(args.order_id):
        print(f"Order {args.order_id!r} not found")
        return 1
    _print_json(repository.get_executions_for_order(args.order_id))
    return 0


def cmd_positions(_: argparse.Namespace) -> int:
    _print_json(position_report.generate())
    return 0


def cmd_reconcile(_: argparse.Namespace) -> int:
    _print_json(reconciliation.run())
    return 0


def cmd_trade_file(_: argparse.Namespace) -> int:
    path = trade_file.generate()
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oms",
        description="Interactive OMS prototype CLI",
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="Create a new order")
    create_parser.add_argument("--client-order-id", required=True)
    create_parser.add_argument("--symbol", required=True)
    create_parser.add_argument("--side", type=lambda value: value.upper(), required=True)
    create_parser.add_argument("--quantity", type=int, required=True)
    create_parser.add_argument("--price", type=float, required=True)
    create_parser.add_argument("--venue", default="SIMULATED_EXCHANGE")
    create_parser.set_defaults(func=cmd_create)

    send_parser = subparsers.add_parser("send", help="Send an order to the venue simulator")
    send_parser.add_argument("order_id")
    send_parser.add_argument(
        "--simulate-mode",
        type=lambda value: SimulationMode(value.upper()),
        default=SimulationMode.FULL_FILL,
    )
    send_parser.set_defaults(func=cmd_send)

    list_parser = subparsers.add_parser("list", help="List all orders")
    list_parser.set_defaults(func=cmd_list_orders)

    get_parser = subparsers.add_parser("get", help="Get one order by id")
    get_parser.add_argument("order_id")
    get_parser.set_defaults(func=cmd_get_order)

    events_parser = subparsers.add_parser("events", help="Show audit trail for an order")
    events_parser.add_argument("order_id")
    events_parser.set_defaults(func=cmd_events)

    exec_parser = subparsers.add_parser("executions", help="Show executions for an order")
    exec_parser.add_argument("order_id")
    exec_parser.set_defaults(func=cmd_executions)

    pos_parser = subparsers.add_parser("positions", help="Show the current position book")
    pos_parser.set_defaults(func=cmd_positions)

    recon_parser = subparsers.add_parser("reconcile", help="Run reconciliation checks")
    recon_parser.set_defaults(func=cmd_reconcile)

    trade_parser = subparsers.add_parser("trade-file", help="Generate the trade file CSV")
    trade_parser.set_defaults(func=cmd_trade_file)

    return parser


def interactive_menu() -> int:
    actions: dict[str, tuple[str, Callable[[], int]]] = {
        "1": ("Create order", _interactive_create_order),
        "2": ("Send order", _interactive_send_order),
        "3": ("List orders", _interactive_list_orders),
        "4": ("View order", _interactive_get_order),
        "5": ("View order events", _interactive_events),
        "6": ("View order executions", _interactive_executions),
        "7": ("Show positions", _interactive_positions),
        "8": ("Run reconciliation", _interactive_reconcile),
        "9": ("Generate trade file", _interactive_trade_file),
        "0": ("Exit", lambda: 0),
    }

    while True:
        print("\nOMS Prototype CLI")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")

        choice = _prompt("Select an option", "0")
        if choice == "0":
            return 0

        action = actions.get(choice)
        if not action:
            print("Unknown option.")
            continue

        exit_code = action[1]()
        if exit_code != 0:
            print(f"Command finished with exit code {exit_code}")


def _interactive_create_order() -> int:
    try:
        req = CreateOrderRequest(
            client_order_id=_prompt("Client order id"),
            symbol=_prompt("Symbol").upper(),
            side=_prompt_enum("Side", OrderSide, OrderSide.BUY.value),
            quantity=_prompt_int("Quantity"),
            price=_prompt_float("Price"),
            venue=_prompt("Venue", "SIMULATED_EXCHANGE"),
        )
        result = create_order_with_result(req)
    except PydanticValidationError as exc:
        return _handle_pydantic_validation_error(exc)
    except ValidationError as exc:
        return _handle_validation_error(exc)
    print("Order created" if result.created else "Existing order returned")
    _print_json(result.order)
    return 0


def _interactive_send_order() -> int:
    order_id = _prompt("Order id")
    simulate_mode = _prompt_enum("Simulation mode", SimulationMode, SimulationMode.FULL_FILL.value)
    return cmd_send(argparse.Namespace(order_id=order_id, simulate_mode=simulate_mode))


def _interactive_list_orders() -> int:
    return cmd_list_orders(argparse.Namespace())


def _interactive_get_order() -> int:
    order_id = _prompt("Order id")
    return cmd_get_order(argparse.Namespace(order_id=order_id))


def _interactive_events() -> int:
    order_id = _prompt("Order id")
    return cmd_events(argparse.Namespace(order_id=order_id))


def _interactive_executions() -> int:
    order_id = _prompt("Order id")
    return cmd_executions(argparse.Namespace(order_id=order_id))


def _interactive_positions() -> int:
    return cmd_positions(argparse.Namespace())


def _interactive_reconcile() -> int:
    return cmd_reconcile(argparse.Namespace())


def _interactive_trade_file() -> int:
    return cmd_trade_file(argparse.Namespace())


def main(argv: Optional[list[str]] = None) -> int:
    _runtime_setup()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        return interactive_menu()

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())