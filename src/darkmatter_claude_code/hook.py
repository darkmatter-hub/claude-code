"""
The hook script Claude Code invokes on each lifecycle event.

Reads the event JSON from stdin, builds a Context Passport, signs it if a
key is configured, chains it to the previous passport in the session,
appends to the local chain, and exits 0.

Crashes are silently swallowed (exit 0, log to stderr) so a broken hook
never breaks the user's Claude Code session.

Usage from .claude/settings.json:
  {
    "hooks": {
      "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "darkmatter-claude-code hook user" }] }],
      "PreToolUse":       [{ "hooks": [{ "type": "command", "command": "darkmatter-claude-code hook pre"  }] }],
      "PostToolUse":      [{ "hooks": [{ "type": "command", "command": "darkmatter-claude-code hook post" }] }],
      "Stop":             [{ "hooks": [{ "type": "command", "command": "darkmatter-claude-code hook stop" }] }]
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

from context_passport import make_passport

from . import store, keys


# Map each Claude Code lifecycle hook to a top-level event.type that an
# auditor can filter on without traversing the nested payload. We use
# namespaced custom types (per SPEC.md §3.3) for the three Claude-Code-
# specific events and the core 'checkpoint' type for turn boundaries.
_EVENT_TO_TYPE = {
    "user":  ("claude_code.user_prompt", "user prompt"),
    "pre":   ("claude_code.tool_call",   "pre tool use"),
    "post":  ("claude_code.tool_result", "post tool use"),
    "stop":  ("checkpoint",              "assistant turn end"),
}


def _maybe_sign(passport: dict) -> dict:
    """Sign the passport if a key is available and cryptography is installed."""
    if not keys.have_key():
        return passport
    try:
        from context_passport.signing import sign_passport
    except ImportError:
        return passport
    priv = keys.load_private()
    if priv is None:
        return passport
    key_id = os.environ.get("DARKMATTER_CLAUDE_CODE_KEY_ID", "darkmatter-claude-code")
    return sign_passport(passport, priv, key_id=key_id)


def _session_id(event_data: dict) -> str:
    """
    Pull the Claude Code session_id from the event payload. Fall back to
    a date-based id if not provided.
    """
    sid = event_data.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    import datetime
    return "session-" + datetime.date.today().isoformat()


def _agent_identity() -> dict:
    return {
        "agent_id":   os.environ.get("DARKMATTER_CLAUDE_CODE_AGENT_ID", "claude-code:local"),
        "agent_name": os.environ.get("DARKMATTER_CLAUDE_CODE_AGENT_NAME", "Claude Code"),
        "provider":   "anthropic",
        "model":      os.environ.get("DARKMATTER_CLAUDE_CODE_MODEL", "claude"),
        "role":       None,
    }


def _build_payload(event_kind: str, event_data: dict) -> dict:
    """
    Shape the Claude Code event into a Context Passport payload.

    We capture both the input/output fields visibly and stash the full
    raw event in memory under 'claude_code' so nothing is lost.
    """
    raw = {k: v for k, v in event_data.items() if k != "session_id"}
    if event_kind == "user":
        return {
            "input":  event_data.get("prompt") or event_data.get("user_input") or raw,
            "output": None,
            "memory": {"claude_code": {"event": "UserPromptSubmit", **raw}},
            "variables": None,
        }
    if event_kind == "pre":
        return {
            "input": {
                "tool":  event_data.get("tool_name") or event_data.get("tool"),
                "args":  event_data.get("tool_input") or event_data.get("input") or {},
            },
            "output": None,
            "memory": {"claude_code": {"event": "PreToolUse", **raw}},
            "variables": None,
        }
    if event_kind == "post":
        return {
            "input": {
                "tool": event_data.get("tool_name") or event_data.get("tool"),
                "args": event_data.get("tool_input") or event_data.get("input") or {},
            },
            "output": event_data.get("tool_response") or event_data.get("result"),
            "memory": {"claude_code": {"event": "PostToolUse", **raw}},
            "variables": None,
        }
    # stop
    return {
        "input":  None,
        "output": event_data.get("stop_reason") or event_data.get("response") or "turn ended",
        "memory": {"claude_code": {"event": "Stop", **raw}},
        "variables": None,
    }


def run(event_kind: str) -> int:
    """Hook entrypoint. Returns the exit code (always 0 on hook failure)."""
    if event_kind not in _EVENT_TO_TYPE:
        sys.stderr.write(f"[darkmatter-claude-code] unknown event kind: {event_kind}\n")
        return 0

    raw_input = sys.stdin.read().strip() or "{}"
    try:
        event_data: dict[str, Any] = json.loads(raw_input)
    except Exception as e:
        sys.stderr.write(f"[darkmatter-claude-code] failed to parse event JSON: {e}\n")
        return 0

    sid = _session_id(event_data)
    event_type, _ = _EVENT_TO_TYPE[event_kind]
    parent = store.get_latest(sid)
    identity = _agent_identity()

    try:
        payload = _build_payload(event_kind, event_data)
        passport = make_passport(
            agent_id=identity["agent_id"],
            agent_name=identity["agent_name"],
            payload=payload,
            parent=parent,
            role=identity["role"],
            provider=identity["provider"],
            model=identity["model"],
            event_type=event_type,
        )
        passport = _maybe_sign(passport)
        store.append(sid, passport)

        # Optional: forward to DarkMatter receiving server if configured
        api_key = os.environ.get("DARKMATTER_API_KEY")
        if api_key:
            _forward(passport, api_key)

        return 0
    except Exception as e:
        sys.stderr.write(f"[darkmatter-claude-code] hook crashed (continuing): {e}\n")
        return 0


def _forward(passport: dict, api_key: str) -> None:
    """Best-effort POST to DarkMatter. Never raise."""
    try:
        import urllib.request
        endpoint = os.environ.get("DARKMATTER_API_URL", "https://darkmatterhub.ai") + "/api/commit"
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({"passport": passport}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # never block the agent's hook on a network failure
