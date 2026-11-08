"""Act as a controlled Codex executable while exercising the real private MCP transport."""

import asyncio
import json
import os
import signal
from pathlib import Path
import sys
import tomllib
import time

CONFIG_PATH = "__SCENARIO_PATH__"


# Merge repeated dotted TOML settings without losing earlier server fields.
def merge_config(target, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict):
            merge_config(target.setdefault(key, {}), value)
        else:
            target[key] = value


# Exercise configured internal tools and produce realistic JSONL plus final output.
async def main():
    scenario = json.loads(Path(CONFIG_PATH).read_text())
    arguments = sys.argv[1:]
    config = {}
    for index, argument in enumerate(arguments):
        if argument in ("-c", "--config"):
            entry = tomllib.loads(arguments[index + 1])
            merge_config(config, entry)
    mcp_config = next(iter(config["mcp_servers"].values()))
    headers = dict(mcp_config.get("http_headers", {}))
    for key, variable in mcp_config.get("env_http_headers", {}).items():
        headers[key] = os.environ[variable]
    prompt = sys.stdin.read()
    schema_path = Path(arguments[arguments.index("--output-schema") + 1])
    marker = Path(scenario["marker"])
    record = {"argv": arguments, "cwd": os.getcwd(), "headers": headers,
              "url": mcp_config["url"], "pid": os.getpid(), "tools": [],
              "prompt": prompt, "config": config, "schema": json.loads(schema_path.read_text()),
              "leaked_secrets": {name: value for name, value in os.environ.items()
                                 if value == "runtime-test-secret-must-not-reach-child"}}
    marker.write_text(json.dumps(record))
    marker.with_name(f"{marker.stem}-pid-{os.getpid()}.json").write_text(json.dumps(record))
    if scenario.get("release"):
        while not Path(scenario["release"]).exists():
            await asyncio.sleep(0.01)
    if scenario.get("mode") == "hang":
        await asyncio.sleep(120)
    if scenario.get("mode") == "fail":
        print("controlled process failure", file=sys.stderr)
        sys.exit(23)
    if scenario.get("mode") in {"descendant", "descendant_ignores_term", "descendant_holds_pipes"}:
        ready_path = marker.with_name(marker.stem + "-descendant-ready")
        descendant = os.fork()
        if descendant == 0:
            if scenario["mode"] in {"descendant_ignores_term", "descendant_holds_pipes"}:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if scenario["mode"] != "descendant_holds_pipes":
                for descriptor in (0, 1, 2):
                    os.close(descriptor)
            ready_path.write_text(str(os.getpid()))
            while True:
                time.sleep(60)
        record["descendant_pid"] = descendant
        marker.write_text(json.dumps(record))
        while not ready_path.exists():
            await asyncio.sleep(0.01)
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport = StreamableHttpTransport(mcp_config["url"], headers=headers)
    async with Client(transport) as client:
        record["tools"] = [tool.name for tool in await client.list_tools()]
        for call in scenario.get("calls", []):
            result = await client.call_tool(call["name"], call.get("arguments", {}),
                                            raise_on_error=False)
            record.setdefault("results", []).append({"name": call["name"],
                "is_error": result.is_error, "data": result.data,
                "text": str(result.content)})
    marker.write_text(json.dumps(record))
    if scenario.get("mode") == "fail_after_tools":
        sys.exit(24)
    final = scenario["final"]
    for index, argument in enumerate(arguments):
        if argument in ("--output-last-message", "-o") and scenario.get("mode") != "jsonl_only":
            Path(arguments[index + 1]).write_text(json.dumps(final))
    print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}), flush=True)
    print(json.dumps({"type": "item.completed", "item": {"type": "reasoning",
        "text": "PRIVATE_REASONING_SENTINEL_MUST_NOT_BE_ACTIVITY"}}), flush=True)
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message",
        "text": json.dumps(final)}}), flush=True)
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1,
        "cached_input_tokens": 0, "output_tokens": 1}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
