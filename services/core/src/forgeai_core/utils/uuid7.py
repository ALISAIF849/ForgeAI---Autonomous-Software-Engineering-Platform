"""RFC 9562 UUID version 7 — time-ordered UUIDs, used as the default primary key
generator everywhere (see docs/architecture/07-database-schema.md §1). Plain
uuid.uuid4() fragments B-tree indexes under high insert volume; a 48-bit
big-endian millisecond timestamp prefix keeps new rows clustered at the end of
the index instead of scattered randomly through it.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ms = int(time.time() * 1000).to_bytes(6, "big")
    rand = os.urandom(10)
    b = bytearray(ms + rand)
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # variant 10
    return uuid.UUID(bytes=bytes(b))
