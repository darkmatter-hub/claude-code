"""
Ed25519 signing key management for the Claude Code hook bundle.

One key per user (not per session). Stored at:
    ~/.darkmatter/claude-code/key.pem            (private, PKCS8 PEM)
    ~/.darkmatter/claude-code/public_key.b64     (public, raw base64)

Generated on first use. Permissions tightened to user-only on Unix.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from . import store


def _key_path() -> Path:
    return store.root() / "key.pem"


def _pub_path() -> Path:
    return store.root() / "public_key.b64"


def have_key() -> bool:
    return _key_path().exists()


def load_private():
    """Load the private signing key. Returns None if cryptography unavailable."""
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return None
    p = _key_path()
    if not p.exists():
        return None
    try:
        return serialization.load_pem_private_key(p.read_bytes(), password=None)
    except Exception:
        return None


def load_public_b64() -> Optional[str]:
    p = _pub_path()
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return None


def generate_and_save() -> tuple[str, Path]:
    """
    Generate a fresh Ed25519 keypair, persist it, return (pub_b64, private_path).
    Requires cryptography.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _key_path().write_bytes(pem)
    try:
        os.chmod(_key_path(), 0o600)
    except Exception:
        pass

    from context_passport.signing import public_key_to_base64
    pub_b64 = public_key_to_base64(priv.public_key())
    _pub_path().write_text(pub_b64, encoding="utf-8")

    return pub_b64, _key_path()
