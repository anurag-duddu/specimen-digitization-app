"""How many independent specialists share one lease window.

A worker opens a lease, runs the next K pending specialists of the roster at once,
publishes what they committed, releases the lease, and opens the next window until
no field is pending. The roles are independent (they share no field, no source and
no request: the owner's "unrelated steps can run in parallel"), so K roles cost the
time of the slowest one instead of the sum.
"""

# K, the committed window size: how many specialists run at once under one lease.
#
# 2 runs the six roles as three windows in roster order: taxonomy and geography,
# temporal and measurement, parties and collection. Within a window the roles have
# disjoint fields (contracts.ROLE_FIELDS is a partition) and disjoint sources
# (taxonomy's three APIs, geography's GEOLocate; no other role has a ready source),
# so the per-source request spacing, the field-level source-capture gate and the
# publication order are untouched. All K requests reserve against the run's one
# allowance before they are sent; the reservation is checked inside the state
# document's compare-and-swap, so concurrent roles cannot overshoot it.
#
# Do not raise it past what the engine accepts (engine.ResearchEngine allows 1 or 2;
# that file is a pinned artifact) and keep K * the per-request reservation inside
# the run's allowance: a request reserves its worst case (committed_pins, about
# USD 0.11), so a USD 0.5 run fits four at once. A lease must outlast the window
# (persistence.MAX_LEASE_TTL_SECONDS). 1 restores one role per lease window.
ROLE_CONCURRENCY = 2
