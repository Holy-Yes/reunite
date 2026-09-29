#!/usr/bin/env python
"""Generate a VAPID key pair for Web Push. Run once, paste the two lines into .env.

    python scripts/gen_vapid.py

The public key is also what the front end passes to `pushManager.subscribe({ applicationServerKey })`.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def main() -> None:
    v = Vapid()
    v.generate_keys()
    priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    Vapid.from_string(b64u(priv))  # round-trip check: pywebpush will load the key from this string
    print(f"VAPID_PUBLIC_KEY={b64u(pub)}")
    print(f"VAPID_PRIVATE_KEY={b64u(priv)}")
    print("VAPID_SUBJECT=mailto:you@your-college.edu")


if __name__ == "__main__":
    main()
