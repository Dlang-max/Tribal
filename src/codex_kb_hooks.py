#!/usr/bin/env python3
"""Remind the current Codex agent to retrieve or update Tribal knowledge."""

import argparse
import json
from pathlib import Path
import re
import shlex
import sys


ROOT = Path(__file__).resolve().parent.parent
TURN_END_REMINDER = "TRIBAL_KB_TURN_END:"


# Recognize Git invocations without treating quoted command examples as execution.
def contains_git(command):
    if not isinstance(command, str):
        return False
    lexer = shlex.shlex(command, posix=False, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    at_command = True
    try:
        for token in lexer:
            if re.fullmatch(r"[;&|()\n]+", token):
                at_command = True
                continue
            if not at_command:
                continue
            words = shlex.split(token)
            if len(words) != 1:
                return False
            word = words[0]
            if word in {"command", "env"} or re.fullmatch(r"[A-Za-z_]\w*=.*", word):
                continue
            if Path(word).name == "git":
                return True
            at_command = False
    except ValueError:
        return False
    return False


# Attach a short reminder to the current event's model context.
def additional_context(event_name, message):
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": message}}


# Return a reminder while leaving evidence gathering and MCP calls to the calling agent.
def handle(mode, event, config):
    checkout = Path(config["checkout"]).resolve()
    if (not event.get("cwd") or not Path(event["cwd"]).resolve().is_relative_to(checkout)
            or event.get("agent_id")):
        return {}
    connection = config["connection"]
    scope = f"Use repository {config['repository']} and the actual branch when relevant."
    if mode == "turn-start":
        if str(event.get("prompt", "")).startswith(TURN_END_REMINDER):
            return {}
        return additional_context("UserPromptSubmit",
            f"Ask Tribal's context agent through {connection}.seed_agent_context for context "
            f"relevant to the current task before starting. Read and use the returned context and sources. {scope}")
    if mode == "after-git":
        tool_input = event.get("tool_input", {})
        if not isinstance(tool_input, dict) or not contains_git(tool_input.get("command")):
            return {}
        return additional_context("PostToolUse",
            f"A Git command was run. Once it finishes, inspect the result and ask Tribal's KB agent "
            f"through {connection}.update_knowledge_base to record useful verified changes. "
            f"Supply the relevant evidence; skip an update if there is no new knowledge. {scope}")
    if event.get("stop_hook_active"):
        return {}
    return {"decision": "block", "reason": TURN_END_REMINDER + " "
        f"Before finishing, ask Tribal's KB agent through {connection}.update_knowledge_base "
        "to record useful new findings, decisions, changes, checks actually run, or handoff context. "
        "Supply the evidence and a unique request_id; reuse the same ID and payload for retries. "
        "Skip the update if there is nothing new, including facts already submitted after Git commands. "
        f"{scope} If MCP is unavailable, report that limitation. Then return your original answer. "
        "This is one reminder for the completed task, not a new task."}


# Read a hook event and emit its reminder without collecting or storing evidence.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["turn-start", "after-git", "turn-end"])
    arguments = parser.parse_args()
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("Expected a hook event object")
        config = json.loads((ROOT / ".codex" / "tribal-hooks.json").read_text())
        result = handle(arguments.mode, event, config)
    except (OSError, ValueError, TypeError, KeyError):
        result = {"systemMessage": "Tribal reminder skipped: invalid event or missing hook settings."}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
