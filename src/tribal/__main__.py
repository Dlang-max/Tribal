"""Run Tribal's management server or a project MCP worker."""

from __future__ import annotations

import argparse
import os

import uvicorn

from tribal.application import build_management_app, build_worker_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tribal")
    parser.add_argument("mode", choices=("management", "worker"))
    args = parser.parse_args()
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as exc:
        parser.error("PORT must be an integer")
        raise exc  # pragma: no cover - argparse.error exits
    if not 1 <= port <= 65535:
        parser.error("PORT must be between 1 and 65535")

    app = build_management_app() if args.mode == "management" else build_worker_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
