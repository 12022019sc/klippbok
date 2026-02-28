"""Top-level CLI dispatcher for the `klippbok` command.

This is the entry point registered in [project.scripts] as `klippbok`.
It dispatches to submodule CLIs for each domain (api/serve, dataset, video).

Usage:
    klippbok serve [--project-dir DIR] [--host HOST] [--port PORT]
    klippbok dataset <command> ...
    klippbok video <command> ...
    klippbok --version
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _get_version() -> str:
    """Return the installed klippbok package version."""
    try:
        from importlib.metadata import version
        return version("klippbok")
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="klippbok",
        description="klippbok -- Video dataset curation and preparation for LoRA training.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"klippbok {_get_version()}",
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    # serve subcommand
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the klippbok web GUI server.",
        description="Start the klippbok FastAPI server for the web interface.",
    )
    serve_parser.add_argument(
        "--project-dir",
        default=None,
        metavar="DIR",
        help="Path to the klippbok project directory (default: current working directory).",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1).",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000).",
    )

    # dataset subcommand (delegates to klippbok.dataset.__main__)
    subparsers.add_parser(
        "dataset",
        help="Dataset validation and organization tools. Run 'klippbok dataset --help'.",
    )

    # video subcommand (delegates to klippbok.video.__main__)
    subparsers.add_parser(
        "video",
        help="Video ingestion and scene detection tools. Run 'klippbok video --help'.",
    )

    return parser


def cmd_serve(args: argparse.Namespace) -> None:
    """Handle the serve subcommand by delegating to klippbok.api.__main__.

    Args:
        args: Parsed arguments with project_dir, host, port.
    """
    from klippbok.api.__main__ import main as api_main

    # Build argv for the api main (it uses its own parser)
    argv: list[str] = []
    if args.project_dir:
        argv.extend(["--project-dir", args.project_dir])
    argv.extend(["--host", args.host, "--port", str(args.port)])

    api_main(argv)


def main() -> None:
    """Main entry point for the klippbok CLI."""
    parser = build_parser()

    # For dataset/video subcommands, forward remaining args to their own parsers.
    # We parse only the first token to check for delegation.
    if len(sys.argv) > 1 and sys.argv[1] in ("dataset", "video"):
        subcommand = sys.argv[1]
        remaining = sys.argv[2:]

        module_name = f"klippbok.{subcommand}.__main__"
        try:
            module = importlib.import_module(module_name)
            # Build argv as if calling python -m klippbok.<subcommand>
            old_argv = sys.argv[:]
            sys.argv = [f"klippbok {subcommand}"] + remaining
            try:
                module.main()
            finally:
                sys.argv = old_argv
        except ImportError as exc:
            print(f"Error: Could not load '{subcommand}' subcommand: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(1)

    if args.subcommand == "serve":
        cmd_serve(args)
    else:
        # Fallback (shouldn't be reached given the early-exit logic above)
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
