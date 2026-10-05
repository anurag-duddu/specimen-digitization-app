# Lane P runtime: reference objects and recovery

The production factory supplies `GeoreferencingAdapter` only when the committed
source registry contains its history or spatial source. `GcsPinnedDatasetReader`
accepts an exact canonical `Dataset` entry, reads metadata for that entry's
`application/sha256/<sha256>` object using the existing worker blob store, and
pins the media read to the returned generation. The existing bounded streaming
reader rejects oversize data, redirects and digest changes; the dataset reader
then rechecks both exact size and SHA-256. The adapter verifies again before
parsing. Neither the runtime nor this reader downloads `source_url` or substitutes
another dataset when an object is absent.

`owner_setup.sh` adds one custom role, `specimenGeoreferenceDatasets`, containing
only `storage.objects.create` and `storage.objects.get`. Its bucket binding is
only for `specimen-data-release` and the ten exact immutable manifest object
names. It grants no list, overwrite, delete, public access or new worker right.
Dataset publication remains in the main-only data workflow after review and
merge. The runtime workflow must follow a successful data release on that same
SHA. Local files and offline tests do not establish object availability or live
worker access.

A run with zero headroom or a financial halt can open a `publication_only`
runtime. It exposes the genuine lease, journal and canonical publication service
with `role_window=0`, and an engine whose `run()` always refuses. It constructs
neither a model factory nor a source transport/broker. It preserves all budget
state, held liabilities, policy/pin checks, access checks, paused-job holds and
the existing scientific publication guards. The native worker must publish or
recover committed output before reporting a remaining need for paid work.

For an explicit human derivation command, the native worker may pass its verified
`derivation_context` to `open()`. With headroom and a registered georeferencing
source, the returned `derivation_services` exposes the durable captured broker,
an immutable mapping of registered specialist requests, the adapter and that
trusted context. No model engine is constructed. The worker must use the trusted
capture entrypoint, never call the unjournaled inner adapter as an effect. New
derivation captures retain the existing positive reservation, shared cumulative
budget accounting and canonical send fence. An exhausted/halted run still gets
publication-only recovery and cannot start a new derivation effect. G9/G30 holds
and the requirement for a verified human command remain in force.

After the worker verifies the genuine human enqueue audit, provisioning also
accepts that command on `finalized` or `waiting_for_review` records. It rechecks
the queued/current revision, run ID, nonblank reason, original snapshot digest
and immutable settled-input proofs, then imports every genuine human lock and
input lock into the new job. The saved specimen keeps its lifecycle, values and
review status. Missing or stale commands cannot use this exception. Normal
`plan` provisioning retains its existing rules.

Composition depends on the Geo adapter/manifest and the source-capture forwarding
of `georeferencing_adapter`. The root integrator owns the native-worker sequence,
human-command validation and final combined-source checks. This note records
source behavior; production deployment and live acceptance are not confirmed.
