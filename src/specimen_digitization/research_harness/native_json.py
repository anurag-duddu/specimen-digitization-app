"""Exact typed JSON at the four V2 native HTTP read boundaries.

SQL Connect's Any transport can turn 15.0 into 15. Research digests commit
to that distinction, so these queries return their scoped row as SQL text.
Only transport decoding happens here; every existing access, identity, digest,
budget and causal validator still consumes the resulting typed object.
"""
from __future__ import annotations

import json
import math

from .compatibility import PublicationUnavailable

NATIVE_JSON_READS = {
    "GetCanonicalResearchBindingV2": "binding",
    "GetCanonicalResearchMaterializationInputsV2": "binding",
    "GetResearchPublicationIntentV2": "intent",
    "GetResearchPublicationReceiptV2": "retained",
}


def decode_native_json(operation, data):
    """No direct-Any fallback at an actual HTTP boundary, even for old data."""
    field = NATIVE_JSON_READS.get(operation)
    if field is None:
        return data

    def refuse():
        raise PublicationUnavailable("native_v2_exact_json_unavailable")

    if type(data) is not dict or field not in data:
        refuse()
    row = data[field]
    # A real absent SQL row retains its normal absence semantics.
    if row is None:
        return data
    if type(row) is not dict or set(row) != {"exact_json"}:
        refuse()
    raw = row["exact_json"]
    if type(raw) is not str or not raw:
        refuse()
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:
        refuse()

    # Existing readers bound each state/preimage and the receipt/row counts.
    # Their 32 MiB per-string bound is not a whole-response bound: this scoped
    # response legitimately includes multiple retained preimages and copies.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                refuse()
            result[key] = value
        return result

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            refuse()
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=number,
            parse_constant=lambda _: refuse())
    except (ValueError, TypeError, RecursionError, OverflowError):
        refuse()
    if type(value) is not dict:
        refuse()
    return {**data, field: value}
