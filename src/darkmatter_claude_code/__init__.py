"""
DarkMatter for Claude Code.

Auto-captures every Claude Code event (user prompt, tool use, tool result,
assistant turn) as a Context Passport record. Records are signed, chained,
and stored locally. Optionally forwarded to a DarkMatter receiving server.

Install:
    pip install darkmatter-claude-code
    darkmatter-claude-code install

Then use Claude Code normally. Records appear at:
    ~/.darkmatter/claude-code/sessions/<session_id>/chain.jsonl

Verify offline at any time:
    pip install context-passport
    python -c "
        import json
        from context_passport import verify_chain
        with open('~/.darkmatter/claude-code/sessions/<id>/chain.jsonl') as f:
            chain = [json.loads(line) for line in f]
        print(verify_chain(chain))
    "

Built by DarkMatter (https://darkmatterhub.ai). Implements
Context Passport v1.0 (https://contextpassport.com).
"""

__version__ = "0.1.0"
