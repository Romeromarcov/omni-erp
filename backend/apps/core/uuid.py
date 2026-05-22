"""
apps/core/uuid.py — UUID version 7 generator (R-CODE-5).

UUIDv7 is a time-ordered UUID format (RFC 9562).  It encodes a Unix
timestamp in milliseconds in the most-significant bits, which makes
UUIDs sortable by creation time and improves B-tree index locality.

Python 3.13 adds ``uuid.uuid7()`` natively; until we upgrade we provide
our own implementation.  The API surface intentionally mirrors the
built-in ``uuid.uuid4`` callable so that it can be used directly as a
Django field default::

    from apps.core.uuid import uuid7

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a new UUID version 7 (time-ordered, random).

    Layout (RFC 9562 §5.7):
    ┌────────────────────────────────┬──────────────────────────────────┐
    │ Bits 0-47  (48 b)              │ Unix timestamp in milliseconds   │
    │ Bits 48-51  (4 b)              │ Version = 0b0111 (7)             │
    │ Bits 52-63 (12 b)              │ rand_a  — random                 │
    │ Bits 64-65  (2 b)              │ Variant = 0b10                   │
    │ Bits 66-127 (62 b)             │ rand_b  — random                 │
    └────────────────────────────────┴──────────────────────────────────┘
    """
    unix_ts_ms: int = int(time.time() * 1000)
    rand_a: int = int.from_bytes(os.urandom(2), "big") & 0x0FFF   # 12 bits
    rand_b: int = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bits

    # Upper 64 bits: 48-bit timestamp | 4-bit version | 12-bit rand_a
    hi: int = (unix_ts_ms << 16) | (0x7 << 12) | rand_a
    # Lower 64 bits: 2-bit variant (0b10) | 62-bit rand_b
    lo: int = (0b10 << 62) | rand_b

    return uuid.UUID(int=(hi << 64) | lo)
