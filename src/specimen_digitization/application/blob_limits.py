"""Per-kind bounded byte reads; never return partial evidence as a complete blob."""

import hashlib

ORIGINAL_BYTES = 25 * 1024 * 1024
ARTIFACT_BYTES = 4 * 1024 * 1024
RAW_VIEW_BYTES = 1024 * 1024


class BlobTooLarge(ValueError):
    pass


def read_limited(read, maximum):
    if not 1 <= maximum <= 64 * 1024 * 1024:
        raise ValueError("Invalid blob byte limit")
    data = bytearray()
    while len(data) <= maximum:
        chunk = read(min(65536, maximum + 1 - len(data)))
        if not chunk:
            return bytes(data)
        if len(data) + len(chunk) > maximum:
            raise BlobTooLarge("Evidence exceeds the configured byte limit")
        data.extend(chunk)
    raise BlobTooLarge("Evidence exceeds the configured byte limit")


def verify_digest(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        from .storage import Conflict

        raise Conflict("Blob integrity failure")
    return data
