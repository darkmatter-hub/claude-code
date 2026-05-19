"""
Local persistence and chain-state tracking for Claude Code sessions.

Each Claude Code session produces a chain of Context Passports. The hook
script fires once per event (user prompt, tool use, tool result, turn end)
and needs to know the previous passport in order to chain correctly.

Layout:
    ~/.darkmatter/claude-code/
    ├── key.pem                       # Ed25519 private signing key (if signing enabled)
    ├── public_key.b64                # Base64 public key for verifiers
    └── sessions/
        └── <session_id>/
            ├── chain.jsonl           # Append-only stream of every passport
            └── latest.json           # Most recent passport (parent for next)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

_DEFAULT_ROOT = Path(os.path.expanduser(
    os.environ.get("DARKMATTER_CLAUDE_CODE_DIR", "~/.darkmatter/claude-code")
))


def root() -> Path:
    p = _DEFAULT_ROOT
    p.mkdir(parents=True, exist_ok=True)
    (p / "sessions").mkdir(parents=True, exist_ok=True)
    return p


def session_dir(session_id: str) -> Path:
    d = root() / "sessions" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_latest(session_id: str) -> Optional[dict]:
    """Return the most recent passport in this session, or None."""
    f = session_dir(session_id) / "latest.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def append(session_id: str, passport: dict) -> None:
    """Append the passport to the chain log and update latest.json atomically.

    chain.jsonl is append-only and durable per write. latest.json is updated
    via os.replace on a temp file so that a process kill between the two
    writes cannot leave latest.json out of sync with chain.jsonl (which
    would corrupt the chain by making the next hook chain from the wrong
    parent).
    """
    d = session_dir(session_id)
    with open(d / "chain.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(passport) + "\n")
    tmp = d / "latest.json.tmp"
    tmp.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    os.replace(tmp, d / "latest.json")


def read_chain(session_id: str) -> list[dict]:
    f = session_dir(session_id) / "chain.jsonl"
    if not f.exists():
        return []
    return [
        json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
