"""
apps/core/uuid.py — UUID version 7 generator (R-CODE-5, RFC 9562 §5.7 & §6.2).

UUIDv7 is a time-ordered UUID format (RFC 9562). It encodes a Unix
timestamp in milliseconds in the most-significant bits and uses a monotonic
12-bit counter in ``rand_a`` (RFC 9562 §6.2 Method 1) so that UUIDs generated
within the same millisecond (or across minor clock regressions) remain strictly
increasing. This guarantees deterministic ``ORDER BY pk`` tie-breaking even on
platforms with coarse clock resolution (e.g. ~15 ms on Windows).

    from apps.core.uuid import uuid7

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ts_ms: int = 0
_counter: int = 0


def _seed_counter() -> int:
    """Return an 11-bit random initial counter (0..0x07FF), leaving >=2048 steps before rollover."""
    return int.from_bytes(os.urandom(2), "big") & 0x07FF


def uuid7() -> uuid.UUID:
    """Return a new strictly monotonic UUID version 7 (RFC 9562 §5.7 & §6.2).

    Layout (RFC 9562 §5.7):
    ┌────────────────────────────────┬──────────────────────────────────┐
    │ Bits 0-47  (48 b)              │ Unix timestamp in milliseconds   │
    │ Bits 48-51  (4 b)              │ Version = 0b0111 (7)             │
    │ Bits 52-63 (12 b)              │ rand_a  — monotonic counter      │
    │ Bits 64-65  (2 b)              │ Variant = 0b10                   │
    │ Bits 66-127 (62 b)             │ rand_b  — cryptographic random   │
    └────────────────────────────────┴──────────────────────────────────┘
    """
    global _last_ts_ms, _counter

    rand_b: int = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF  # 62 bits
    now_ms: int = int(time.time() * 1000)

    with _lock:
        if now_ms > _last_ts_ms:
            _last_ts_ms = now_ms
            _counter = _seed_counter()
        else:
            _counter += 1
            if _counter > 0x0FFF:
                # Counter exhausted within the same ms: advance monotonic timestamp by 1 ms.
                _last_ts_ms += 1
                _counter = _seed_counter()
        ts_ms = _last_ts_ms
        rand_a = _counter

    # Upper 64 bits: 48-bit timestamp | 4-bit version | 12-bit monotonic rand_a
    hi: int = ((ts_ms & 0xFFFFFFFFFFFF) << 16) | (0x7 << 12) | rand_a
    # Lower 64 bits: 2-bit variant (0b10) | 62-bit rand_b
    lo: int = (0b10 << 62) | rand_b

    return uuid.UUID(int=(hi << 64) | lo)
