"""Entry point for `python -m klippbok.api`.

Starts the klippbok FastAPI server with uvicorn.

Usage:
    python -m klippbok.api
    python -m klippbok.api --project-dir /path/to/project
    python -m klippbok.api --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def build_parser(prog: str = "python -m klippbok.api") -> argparse.ArgumentParser:
    """Build the argument parser for the API server CLI.

    Args:
        prog: Program name shown in help text.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Start the klippbok FastAPI server.",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        metavar="DIR",
        help="Path to the klippbok project directory (default: select from web UI).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port to run the server on (default: 9000).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Start the klippbok API server.

    Args:
        argv: Argument list (defaults to sys.argv if None).
    """
    import uvicorn

    from klippbok.api.app import create_app

    # Configure logging so all klippbok loggers emit to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    app = create_app(project_dir=project_dir)

    print(f"Starting klippbok server")
    print(f"  Project: {project_dir or '(none — select from web UI)'}")
    print(f"  URL:     http://{args.host}:{args.port}")
    print()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    sys.exit(main())
