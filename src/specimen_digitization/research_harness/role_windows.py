"""How many independent specialists share one lease window.

A worker opens a lease, runs the next K pending specialists of the roster at once,
publishes what they committed, releases the lease, and opens the next window until
no field is pending. The roles are independent (they share no field, no source and
no request: the owner's "unrelated steps can run in parallel"), so K roles cost the
time of the slowest one instead of the sum.
"""

# K, the committed window size: how many specialists run at once under one lease.
#
# 2 runs the six roles as three windows in engine.RESEARCH_ROLE_ORDER:
# temporal and parties, measurement and collection, taxonomy and geography.
# Each next production window rebuilds host-verified settled context, so geography
# can use accepted collecting date/person context after those roles finish.
# Within a window the roles have
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
# USD 0.213), so a USD 1 run fits the committed two at once while sufficient headroom remains. A lease must outlast the window
# (persistence.MAX_LEASE_TTL_SECONDS). 1 restores one role per lease window.
ROLE_CONCURRENCY = 2

# What engine.ResearchEngine accepts as max_concurrency (its constructor allows 1 or 2). That file
# is a pinned artifact, so the number is repeated here to refuse an unsupported K before a window's
# lease is claimed, not after (a test pins the two together).
ENGINE_MAX_CONCURRENCY = 2


def window_size(remaining_micro_usd: int, reservation_micro_usd: int) -> int:
    """The window's width for a run with ``remaining_micro_usd`` left: at most K, and no more
    roles than the allowance can reserve a request for.

    Every running role holds one request's reservation, taken before the request is sent. With
    less than K reservations left, the K-th concurrent request would be refused (BudgetExceeded)
    and its role would lose its fields; a narrower window runs those roles one after another
    instead. At least one role always runs: a run that cannot reserve even one request is refused
    by the reservation itself, as it is with K = 1. The width is taken when the window opens;
    spending inside the window can still leave a later request short, exactly as at K = 1.

    A K the engine cannot run is refused here, before the caller claims a lease."""
    if type(ROLE_CONCURRENCY) is not int or not 1 <= ROLE_CONCURRENCY <= ENGINE_MAX_CONCURRENCY:
        raise ValueError("research_role_concurrency_unsupported")
    return max(1, min(ROLE_CONCURRENCY, remaining_micro_usd // reservation_micro_usd))
