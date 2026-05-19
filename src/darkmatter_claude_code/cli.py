"""
CLI entrypoint: install, hook, status, key, verify.

  darkmatter-claude-code install            Wire up hooks in .claude/settings.json
  darkmatter-claude-code hook <user|pre|post|stop>   Hook handler (called by Claude Code)
  darkmatter-claude-code status             Show current install + key + recent activity
  darkmatter-claude-code key generate       Create a fresh Ed25519 signing key
  darkmatter-claude-code key show           Print the public key
  darkmatter-claude-code verify [session]   Verify the chain for a session
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import hook, keys, store


def cmd_install(args: argparse.Namespace) -> int:
    target_dir = Path(args.target or ".") / ".claude"
    target_dir.mkdir(parents=True, exist_ok=True)
    settings_path = target_dir / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            print(f"WARNING: existing settings.json is not valid JSON; refusing to overwrite. Manual install required.", file=sys.stderr)
            return 1

    hooks_cfg = existing.setdefault("hooks", {})

    def _entry(event: str) -> dict:
        return {
            "hooks": [{
                "type": "command",
                "command": f"darkmatter-claude-code hook {event}",
            }],
        }

    for ev_name, ev_arg in [
        ("UserPromptSubmit", "user"),
        ("PreToolUse",       "pre"),
        ("PostToolUse",      "post"),
        ("Stop",             "stop"),
    ]:
        existing_list = hooks_cfg.get(ev_name, [])
        if any(
            "darkmatter-claude-code" in str(h)
            for h in existing_list
        ):
            print(f"hook for {ev_name} already installed, skipping")
            continue
        existing_list.append(_entry(ev_arg))
        hooks_cfg[ev_name] = existing_list

    settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Hooks installed at {settings_path}")

    if not keys.have_key():
        try:
            pub_b64, key_path = keys.generate_and_save()
            print(f"Generated Ed25519 signing key at {key_path}")
            print(f"Public key (base64): {pub_b64}")
        except ImportError:
            print("NOTE: signing not available (cryptography not installed). Install with: pip install 'darkmatter-claude-code[signing]'")
    else:
        print(f"Signing key already exists at {store.root() / 'key.pem'}")

    print()
    print("Done. Restart Claude Code so it picks up the new hooks.")
    print(f"Records will be stored at: {store.root() / 'sessions'}")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    return hook.run(args.event)


def cmd_status(args: argparse.Namespace) -> int:
    print(f"DarkMatter for Claude Code")
    print(f"  Storage:          {store.root()}")
    print(f"  Signing key:      {'present' if keys.have_key() else 'NOT GENERATED (run: darkmatter-claude-code key generate)'}")
    if keys.have_key():
        pub = keys.load_public_b64()
        if pub:
            print(f"  Public key:       {pub}")
    api = "set" if "DARKMATTER_API_KEY" in __import__("os").environ else "not set"
    print(f"  DARKMATTER_API_KEY: {api} (when set, passports also forward to darkmatterhub.ai)")
    sessions_dir = store.root() / "sessions"
    if sessions_dir.exists():
        sessions = sorted([p.name for p in sessions_dir.iterdir() if p.is_dir()])
        print(f"  Sessions found:   {len(sessions)}")
        for s in sessions[-5:]:
            chain = store.read_chain(s)
            print(f"    {s}: {len(chain)} passports")
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    if args.action == "generate":
        if keys.have_key() and not args.force:
            print(f"Key already exists at {store.root() / 'key.pem'}. Use --force to regenerate.")
            return 1
        try:
            pub_b64, key_path = keys.generate_and_save()
            print(f"Generated Ed25519 signing key at {key_path}")
            print(f"Public key (base64): {pub_b64}")
            return 0
        except ImportError:
            print("ERROR: cryptography not installed. Install with: pip install 'darkmatter-claude-code[signing]'", file=sys.stderr)
            return 2
    if args.action == "show":
        pub = keys.load_public_b64()
        if pub is None:
            print("No public key available. Run: darkmatter-claude-code key generate", file=sys.stderr)
            return 1
        print(pub)
        return 0
    return 1


def cmd_verify(args: argparse.Namespace) -> int:
    from context_passport import verify_chain
    sid = args.session or "default"
    chain = store.read_chain(sid)
    if not chain:
        print(f"No records for session: {sid}")
        return 1
    ok = verify_chain(chain)
    print(f"Session: {sid}")
    print(f"Records: {len(chain)}")
    print(f"Chain intact: {ok}")
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="darkmatter-claude-code")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="Install hooks into .claude/settings.json")
    p_install.add_argument("--target", help="Project directory (default: cwd)")
    p_install.set_defaults(func=cmd_install)

    p_hook = sub.add_parser("hook", help="Internal: invoked by Claude Code hooks")
    p_hook.add_argument("event", choices=["user", "pre", "post", "stop"])
    p_hook.set_defaults(func=cmd_hook)

    p_status = sub.add_parser("status", help="Show install status and recent activity")
    p_status.set_defaults(func=cmd_status)

    p_key = sub.add_parser("key", help="Manage the signing key")
    p_key.add_argument("action", choices=["generate", "show"])
    p_key.add_argument("--force", action="store_true", help="Overwrite an existing key")
    p_key.set_defaults(func=cmd_key)

    p_verify = sub.add_parser("verify", help="Verify the chain for a session")
    p_verify.add_argument("session", nargs="?", help="Session id (default: 'default')")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
