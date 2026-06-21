"""continuator serve — local HTTP API for extract, checkpoint, resume."""
from __future__ import annotations

import argparse

from continuator.console import ContinuatorConsole, sanitize_error
from continuator.platform.http_server import run_server
from continuator.runtime import ensure_runtime


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "serve",
        parents=[parent],
        help="Start local HTTP server (127.0.0.1 only)",
        description=(
            "Run a local HTTP server exposing extract, checkpoint, and resume endpoints. "
            "Binds to 127.0.0.1 by default for security."
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8741, help="Port (default: 8741)")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    console = ContinuatorConsole(verbose=args.verbose, quiet=args.quiet)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        console.step_fail("serve only supports local bind addresses (127.0.0.1)")
        return 2

    try:
        ensure_runtime()
        if not args.quiet:
            console.say(f"[bold]Serving[/bold] http://{args.host}:{args.port}")
        run_server(host=args.host, port=args.port)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        msg = sanitize_error(str(exc)) if not args.verbose else f"{type(exc).__name__}: {exc}"
        console.step_fail(msg)
        return 1
    return 0
