# DarkMatter for Claude Code

Auto-capture every Claude Code action as a verifiable, signed, hash-chained Context Passport record. Hooks into Claude Code's lifecycle so you get a tamper-evident audit trail of every prompt, every tool call, and every assistant turn without changing your application code.

**Built by [DarkMatter](https://darkmatterhub.ai). Implements [Context Passport v1.0](https://contextpassport.com), an open CC0 standard.**

## Install

```bash
pip install "darkmatter-claude-code[signing]"
cd path/to/your/project
darkmatter-claude-code install
```

This:
1. Adds 4 hook entries to `.claude/settings.json` (creating the file if needed).
2. Generates an Ed25519 signing key at `~/.darkmatter/claude-code/key.pem`.
3. Prints the public key so you can give it to anyone who needs to verify your records.

Restart Claude Code. From this point forward every event in every session is auto-captured.

## What gets captured

| Claude Code event | Hook fired | Context Passport `event.type` | What's in the payload |
|---|---|---|---|
| User submits a prompt | `UserPromptSubmit` | `commit` | The prompt text |
| Claude is about to use a tool | `PreToolUse` | `commit` | Tool name + arguments |
| Tool returns a result | `PostToolUse` | `commit` | Tool name + result |
| Assistant finishes responding | `Stop` | `checkpoint` | Stop reason or final response summary |

Every record is:
- Signed with your Ed25519 key (proves it came from you)
- Hash-chained to the previous record (any modification breaks the chain)
- Stored at `~/.darkmatter/claude-code/sessions/<session_id>/chain.jsonl`

## Verify your chain

```bash
darkmatter-claude-code verify <session_id>
```

Or independently with the open-source Python reference implementation:

```bash
pip install context-passport
python -c "
import json
from context_passport import verify_chain
with open('$HOME/.darkmatter/claude-code/sessions/default/chain.jsonl') as f:
    chain = [json.loads(line) for line in f]
print('chain intact:', verify_chain(chain))
"
```

Or with the conformance suite:

```bash
pip install context-passport-conformance
context-passport-conformance --vectors-dir ~/.darkmatter/claude-code/sessions/default
```

## Optional: forward to DarkMatter

By default everything stays local. To also push each passport to your DarkMatter account (so you can see sessions from any machine, and the records get anchored to the public Witness Log):

```bash
export DARKMATTER_API_KEY="dm_sk_..."
```

Then keep using Claude Code normally. Forwarding is best-effort and never blocks the hook; if the network is down, your local records are still complete and the next successful POST will catch up.

## Configuration

All optional. Set via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DARKMATTER_API_KEY` | unset | If set, forward each passport to darkmatterhub.ai |
| `DARKMATTER_API_URL` | `https://darkmatterhub.ai` | Receiving server endpoint |
| `DARKMATTER_CLAUDE_CODE_DIR` | `~/.darkmatter/claude-code` | Local storage root |
| `DARKMATTER_CLAUDE_CODE_AGENT_ID` | `claude-code:local` | Override agent_id in records |
| `DARKMATTER_CLAUDE_CODE_AGENT_NAME` | `Claude Code` | Override agent_name |
| `DARKMATTER_CLAUDE_CODE_MODEL` | `claude` | Override model field |
| `DARKMATTER_CLAUDE_CODE_KEY_ID` | `darkmatter-claude-code` | key_id stored in the signature block |

## Status and key management

```bash
darkmatter-claude-code status              # Show install + key + recent sessions
darkmatter-claude-code key show            # Print your public key
darkmatter-claude-code key generate --force # Regenerate the signing key (irreversible)
```

## How this relates to the DarkMatter MCP server

[`darkmatter-hub/mcp`](https://github.com/darkmatter-hub/mcp) is a universal MCP server that exposes Context Passport tools (`darkmatter_commit`, `darkmatter_verify`, etc.) to any MCP-compatible AI tool. It captures whatever the agent explicitly invokes.

This package (`darkmatter-claude-code`) is the auto-capture adapter specifically for Claude Code. It captures every event, not just what the agent decides to commit. Use both if you want full auto-capture in Claude Code plus the MCP tools available for explicit invocation. Use just this for auto-capture-only.

## License

Apache-2.0. See `LICENSE`.

The Context Passport schema this package implements is released separately under CC0 1.0 at [github.com/contextpassport/spec](https://github.com/contextpassport/spec).

## Related repositories

- [github.com/contextpassport/spec](https://github.com/contextpassport/spec) — the open standard
- [github.com/contextpassport/python](https://github.com/contextpassport/python) — Python reference SDK (this package depends on it)
- [github.com/darkmatter-hub/mcp](https://github.com/darkmatter-hub/mcp) — universal MCP server
- [github.com/darkmatter-hub/darkmatter](https://github.com/darkmatter-hub/darkmatter) — DarkMatter receiving server
