"""Module entry point so the CLI can be launched with `python -m app`."""

from app.cli import main


if __name__ == "__main__":
    raise SystemExit(main())