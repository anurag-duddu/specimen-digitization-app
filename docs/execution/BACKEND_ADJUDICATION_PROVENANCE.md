# Bounded adjudication and observation provenance

Additive to `6b4b654`; earlier Flutter/TRN fixtures remain unchanged.

The legacy adjudication path now uses the same bounded raw-reading alignment as the evidence layer. A budget-blocked or incomplete independent pair has nullable disagreement ratio, explicit alignment status/reasons, unresolved transcript, and retained alternatives. Even identical text beyond the supported alignment size is unmeasured, not automatic agreement. Measured ratios use explicit `bounded-levenshtein-fraction-v1` semantics (edit distance divided by maximum raw length); old SequenceMatcher semantics are not silently reused. Existing stored historical hashes remain based on their exact original payload.

Production observations now retain actual agent-call wall duration and its basis, the provider/SDK-reported finish state and model name, validated-output completion state, explicitly requested model settings (null when none were supplied), original asset ID and an immutable copy of the exact model-input crop. Missing historical telemetry stays null; no timing, provider defaults or finish reason is fabricated. The crop bytes and source association are checked by the integrity gate.

Five focused tests passed (`/tmp/specimen-bounded-adjudication-telemetry.log`): actual PydanticAI FunctionModel output provenance plus bounded/long multilingual reading behavior. Forty-three application/reading/declaration regressions passed before the final telemetry assertions (`/tmp/specimen-bounded-adjudication-initial.log`). A test initially expected the name supplied inside FunctionModel's response; the SDK actually replaces that name. The corrected assertion verifies the parsed observation against the retained raw response, preserving what was really reported.

No live provider requests, production changes, or frozen fixture rewrites. Published profile/risk/SAM wiring and bounded authority HTTP follow-ups remain active work.
