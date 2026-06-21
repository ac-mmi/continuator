"""continuator doctor — diagnose mock backend and missing dependencies."""
from __future__ import annotations

import argparse
import json
import sys

from continuator.extraction_status import collect_extraction_status, find_stale_mock_checkpoints, format_status_report


def register(subparsers: argparse._SubParsersAction, *, parent: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "doctor",
        parents=[parent],
        help="Diagnose why extraction may show mock output",
        description=(
            "Print active backend, dependency status, and stale mock checkpoints "
            "shipped with the repo or left from smoke tests."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    status = collect_extraction_status()
    mock_ckpts = [str(p) for p in find_stale_mock_checkpoints()]

    if args.json:
        payload = {
            "env_backend": status.env_backend,
            "effective_backend": status.effective_backend,
            "platform_default": status.platform_default,
            "transformers_ok": status.transformers_ok,
            "torch_ok": status.torch_ok,
            "mlx_ok": status.mlx_ok,
            "adapter_ready": status.adapter_ready,
            "ready_for_real_extraction": status.ready_for_real_extraction,
            "issues": status.issues,
            "fixes": status.fixes,
            "mock_checkpoints": mock_ckpts,
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(format_status_report(status))

    if status.effective_backend == "mock" or mock_ckpts:
        return 1
    if not status.ready_for_real_extraction and status.issues:
        return 1
    return 0
