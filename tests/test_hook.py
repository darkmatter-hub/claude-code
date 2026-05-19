"""Basic smoke tests for the hook entrypoint and CLI."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch):
    """Redirect storage to a temp dir per test."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("DARKMATTER_CLAUDE_CODE_DIR", tmp)
    yield Path(tmp)


def _fire(event_kind: str, payload: dict, monkeypatch) -> int:
    from darkmatter_claude_code import hook
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return hook.run(event_kind)


def test_user_prompt_emits_passport(monkeypatch):
    rc = _fire("user", {"session_id": "test-1", "prompt": "hello"}, monkeypatch)
    assert rc == 0
    from darkmatter_claude_code import store
    chain = store.read_chain("test-1")
    assert len(chain) == 1
    assert chain[0]["event"]["type"] == "claude_code.user_prompt"
    assert chain[0]["payload"]["input"] == "hello"


def test_pre_and_post_tool_use_chain(monkeypatch):
    _fire("pre",  {"session_id": "test-2", "tool_name": "Bash", "tool_input": {"cmd": "ls"}}, monkeypatch)
    _fire("post", {"session_id": "test-2", "tool_name": "Bash", "tool_response": "file1\nfile2"}, monkeypatch)
    from darkmatter_claude_code import store
    chain = store.read_chain("test-2")
    assert len(chain) == 2
    assert chain[0]["event"]["type"] == "claude_code.tool_call"
    assert chain[1]["event"]["type"] == "claude_code.tool_result"
    assert chain[1]["parent_id"] == chain[0]["id"]
    assert chain[1]["integrity"]["parent_hash"] == chain[0]["integrity"]["integrity_hash"]


def test_stop_event_uses_checkpoint_type(monkeypatch):
    _fire("stop", {"session_id": "test-3", "stop_reason": "end_turn"}, monkeypatch)
    from darkmatter_claude_code import store
    chain = store.read_chain("test-3")
    assert chain[0]["event"]["type"] == "checkpoint"


def test_unknown_event_kind_does_not_crash(monkeypatch):
    from darkmatter_claude_code import hook
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert hook.run("unknown-kind") == 0


def test_malformed_json_does_not_crash(monkeypatch):
    from darkmatter_claude_code import hook
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert hook.run("user") == 0


def test_chain_verifies(monkeypatch):
    _fire("user", {"session_id": "test-v", "prompt": "p1"}, monkeypatch)
    _fire("pre",  {"session_id": "test-v", "tool_name": "Read"}, monkeypatch)
    _fire("post", {"session_id": "test-v", "tool_name": "Read", "tool_response": "ok"}, monkeypatch)
    _fire("stop", {"session_id": "test-v"}, monkeypatch)
    from darkmatter_claude_code import store
    from context_passport import verify_chain
    chain = store.read_chain("test-v")
    assert len(chain) == 4
    assert verify_chain(chain)
