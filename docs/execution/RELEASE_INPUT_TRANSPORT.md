# Bounded release input transport

The single `RELEASE_INPUTS_B64` secret can carry either the existing base64 JSON
bundle or base64 of one gzip stream containing the exact same JSON bytes.
`RELEASE_INPUTS_SHA256` continues to pin the original uncompressed bundle bytes.
Packet, plan, independent-review, authorization and complete cumulative-ledger
hashes and semantic admission remain unchanged. Compression grants no authority.

`release_admission.encode_release_inputs(raw)` returns the existing raw base64
form when it fits within 48000 ASCII bytes. Otherwise it uses a deterministic gzip
envelope with no filename, zero timestamp and a fixed OS marker, and refuses an
output above 48000 bytes. It never reformats ledger, evidence or bundle JSON.
No extra secret, flag variable, dependency, storage service or cost allowance is
introduced. The existing frozen issuers are not silently adapted or repinned;
coordinators must explicitly qualify a producer using the exact merged consumer.

The decoder recognizes gzip only by the binary gzip magic, which cannot begin
valid JSON. Compressed input is limited to 48000 base64 characters before
inflation. One standard-library `zlib.decompressobj(wbits=31).decompress` call
uses a maximum output of 1048577 bytes, allowing one overflow-detection byte.
The accepted raw limit remains 1048576 bytes. The decoder requires end-of-stream
and empty unconsumed/unused input; it rejects CRC/size failures, truncation,
trailing bytes and concatenated members. It does not autodetect zlib/raw-deflate,
call `gzip.decompress`, loop over streams or flush a decompressor. A flush length
is an initial buffer size, not a hard output limit.

For backward compatibility, existing raw-JSON decoding retains its original 1 MiB
raw ceiling, with a corresponding 1398104-character base64 precheck. This is not
permission to store a larger secret: the producer and native installer retain
the 48000-byte ceiling. The optional compressed form has no such legacy allowance.

After restoring bytes, materialization checks the existing original bundle hash
and exact bundle/evidence field names. Every payload string is checked and
encoded as UTF-8 before creating a destination. Invalid compressed input, hashes,
JSON or evidence types therefore leave no partial destination. Accepted output
uses fixed filenames and private directories/files; it never extracts paths from
an archive. Existing packet/plan/evidence and release-admission validators still
run on the restored bytes before any privileged release operation.

The original raw bound, variable semantics, cumulative ledgers, every prior
reservation/unknown hold and all native request/time/crypto/scope limits remain
unchanged. Actual source and input review are still required. A successful local
codec probe is neither operational admission nor product-release acceptance.

References: [GitHub secret limits](https://docs.github.com/en/actions/reference/security/secrets)
and [Python 3.12 bounded decompression APIs](https://docs.python.org/3.12/library/zlib.html).
