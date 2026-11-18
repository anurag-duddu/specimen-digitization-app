"""The fields' second opinion: a value field research settled is shown as settled only when an
independent strong model, filling the record on its own, agrees (autonomy program, lane F1;
docs/execution/golive/FIELD_RESEARCH.md, "The second opinion").

Measured basis (the program's fields benchmark, 2026-11-18, ~/specimen-golive/runs/
autonomy-fields-20261118/final/score_fields.md, K1's locality comparison): on the cleared records of
the 100 truth slides, Muse Spark Open 816B, given the same label crops, the readers' transcriptions
and the field definitions but never the pipeline's fields, agreed with 299 of the pipeline's 355
settled values on the 67 slides it answered, 5 of them wrong (39 of the 355 were wrong). Small
samples: 2 wrong in 280 has a 95 % upper bound near 3 %.

ITS OWN WORKFLOW STEP (STEP; application/second_opinion_step.py runs it). It runs after field
research has completed for the run (the research step or its recheck finalized the record: no
retryable research failure pending, nothing further to ask) and before the record is finalized
(`due`), with the lifecycle of every paid step: a reservation, an intent saved with a lease and an
attempt, a deadline, and a settlement. Field research never calls it and never reads its result.
Any failure of the step ends it "not obtained" and the workflow finalizes the record.

THE REQUEST. One model call on SECOND_OPINION_ROUTE: the system message is the instruction
(prompts/second_opinion.txt, pinned by INSTRUCTION_SHA256); the user message holds every label crop
of the slide in label order, then each label's two readers' transcriptions (reader A and reader B,
the profile's first two reader routes), exactly as the benchmark built it. A crop longer than
MAX_ASPECT times its width (or the reverse) is padded with a white border to that ratio, centred,
since the provider refuses it otherwise; the result records which labels were padded. The model
answers the tool record_fields (TOOL_NAME): the 20 fields, each {value, evidence}, which the answer
must satisfy field by field (`read_answer`). The request carries nothing of the pipeline's fields
(`request_parts` reads only the crops and the observations' texts).

ONE STORED RESULT (Run.second_opinion, `record`). The status (obtained, not obtained and why,
switched off), and for each judged field (every field but the catalogue number and the IRN that
holds a settled value when the step runs): the value it was compared with (as the app shows it),
the second opinion's value and the label text it rests on, and the verdict (agrees or differs). The
model's answer is stored inline. No finding, no mark, no evidence row is written and no field is
touched.

MARKS ARE DERIVED, NEVER STORED (`reasons`, called by step.finalize_fields on every finalize).
For a field settled with a value that no person holds authority over (`authority`) and no other
rule marks: `marked:<field>:<label>:second_opinion_differs` when the recorded verdict for its current
shown value is "differs"; `marked:<field>:<label>:second_opinion_not_checked` when there is no recorded
verdict for its current shown value (not obtained, switched off, not run yet, or the value changed
since it was judged); nothing when the recorded verdict for its current value is "agrees". Never
the catalogue number (its own evidence is the slide's QR code) nor the determiner's IRN.

THE COMPARISON (`same`), one strict rule per kind of field, on the value the app shows (normalized,
else parsed, else literal) against the second opinion's value:
- dates (Date Visited From and To, Date Identified): both must be ISO dates (YYYY, YYYY-MM or
  YYYY-MM-DD that the calendar accepts) and equal at the same precision;
- numbers (the four elevations): both must be plain decimal numbers (a thousands comma allowed)
  and equal once each is rounded to the hundredth;
- identifiers (the catalogue number, never judged here): the same digits, digit for digit;
- text (everything else): equal once accents are removed (NFKD, combining marks dropped), case is
  folded, and every character that is not a letter or a digit is dropped, except a "." or ","
  between two digits and a "-" or "+" directly before a digit, which are kept (so "1.5 km" is not
  "15 km" and "-80" is not "80"). Province/State and County also set aside one trailing unit word
  on either side (UNIT_WORDS), as the benchmark's comparison does.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import math
import re
import time
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from specimen_digitization.application.domain import FieldValue, ValueState

from .contracts import Reading

LOGGER = logging.getLogger(__name__)

# The workflow step, and the run's stage while it is due.
STEP = "field_second_opinion"
DIFFERS = "second_opinion_differs"
NOT_CHECKED = "second_opinion_not_checked"
OBTAINED, NOT_OBTAINED, SWITCHED_OFF = "obtained", "not_obtained", "switched_off"
AGREES_VERDICT, DIFFERS_VERDICT = "agrees", "differs"
TOOL_NAME = "record_fields"
# The 20 fields of the instruction, in its order.
FIELDS = ("fmnh_ins_number", "collection_code", "country", "province_state", "county", "city", "precise_location",
          "elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft", "habitat", "collection_method",
          "date_visited_from", "date_visited_to", "collectors", "verbatim_dts", "taxon", "identified_by_irn",
          "date_identified")
# Never judged: the catalogue number has its own evidence (the slide's QR code, catalogue_code.py);
# the instruction asks for no IRN.
EXCLUDED = frozenset({"fmnh_ins_number", "identified_by_irn"})
JUDGED = tuple(key for key in FIELDS if key not in EXCLUDED)
DATES = frozenset({"date_visited_from", "date_visited_to", "date_identified"})
NUMBERS = frozenset({"elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"})
IDENTIFIERS = frozenset({"fmnh_ins_number"})
# One trailing unit word set aside on either side (the benchmark's comparison: T0/ref/score.py
# value_ok for the province, K1's product_cell for the county).
UNIT_WORDS = {"province_state": ("prov", "province", "department"), "county": ("county", "co")}

# The request, as the benchmark pinned it (candidates.json, probe.json): 8,000 output tokens, the
# output tool forced. One request's worst case at list is about USD 0.052 (an input bound of about
# 14,000 tokens for a four-label slide and 8,000 output tokens; the benchmark's dearest answer cost
# USD 0.038, its mean 0.012). A malformed answer is asked again once (REQUESTS), as the readers' are,
# so the step reserves two requests' worst case, in micro-USD, and settles to what they cost. A
# request whose worst case does not fit what is left is not sent (not obtained: budget).
MAX_TOKENS = 8_000
REQUESTS = 2
CAP_MICROS = 120_000
# The tokens the step reserves on the run's token budget, as every mandatory paid step does
# (workflow.Workflow._step, reservation_tokens).
RESERVED_TOKENS = 16_000
# The stored result's status while its intent is open (the request may be in flight).
ASKING = "asking"
# Each image's tokens are bounded by one token per 28 by 28 pixels (the readers' rule; the benchmark's
# Muse Spark calls reported about a third of that), and the text's by its UTF-8 bytes.
PIXELS_PER_TOKEN = 28
TEMPLATE_TOKENS = 512
# Baseten refused 3 of the benchmark's 70 requests: "Media aspect ratio exceeds 40:1".
MAX_ASPECT = 40
# The longest the request may take (the benchmark's slowest answer took 27 s); the least time the
# step starts its request with.
TIMEOUT_SECONDS = 90.0
MIN_SECONDS = 15.0

_PROMPTS = Path(__file__).parent / "prompts"
INSTRUCTION_FILE = _PROMPTS / "second_opinion.txt"
# The benchmark's instruction, byte for byte (autonomy-fields-20261118/instruction.txt).
INSTRUCTION_SHA256 = "842a498cb2284a55631e71aee476261af92b7ebbf62148aa3849be20a78099d4"  # pragma: allowlist secret (instruction digest)


class NotObtained(Exception):
    """The second opinion was not obtained; the code says why (no request content in it)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def instruction() -> str:
    """The instruction text; refused when it is not the pinned text."""
    data = INSTRUCTION_FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != INSTRUCTION_SHA256:
        raise NotObtained("instruction_changed")
    return data.decode("utf-8")


def tool_schema() -> dict:
    """record_fields' parameters: the 20 fields, each {value: string or null, evidence: string}."""
    entry = {"type": "object", "additionalProperties": False, "required": ["value", "evidence"],
             "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "null"}]}, "evidence": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": list(FIELDS),
            "properties": {key: entry for key in FIELDS}}


TOOL_DESCRIPTION = ("The slide's record: the 20 fields in order, each with its value (or null) and the label text it "
                    "rests on.")


# ---- the request ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Label:
    """One label of the slide as the request shows it: its number, region, crop and readers' texts."""

    number: int
    region_id: str
    png: bytes
    width: int
    height: int
    readers: tuple[str | None, str | None]
    padded: bool = False


def pad(png: bytes, width: int, height: int) -> tuple[bytes, int, int, bool]:
    """The crop with a white border, centred, that brings it to MAX_ASPECT:1 when it is longer than
    that; else the crop as it is. Deterministic: the same crop gives the same bytes."""
    if max(width, height) <= MAX_ASPECT * min(width, height):
        return png, width, height, False
    from PIL import Image

    new_w = max(width, math.ceil(height / MAX_ASPECT))
    new_h = max(height, math.ceil(width / MAX_ASPECT))
    with Image.open(io.BytesIO(png)) as image:
        canvas = Image.new("RGB", (new_w, new_h), "white")
        canvas.paste(image.convert("RGB"), ((new_w - image.width) // 2, (new_h - image.height) // 2))
        out = io.BytesIO()
        canvas.save(out, format="PNG")
    return out.getvalue(), new_w, new_h, True


def labels_of(run, crops: Mapping[str, bytes]) -> tuple[Label, ...]:
    """The slide's labels in their order (Region.order), numbered from 1, each with its crop
    (`crops[region.id]`, PNG bytes, padded where it is too long) and the last text of each of the
    profile's first two reader routes (None where that reader returned nothing)."""
    routes = list(run.profile.routes)[:2]
    labels = []
    for number, region in enumerate(sorted(run.regions, key=lambda r: (r.order, r.id)), start=1):
        texts = []
        for route in routes:
            found = [o.literal_text for o in run.observations if o.region_id == region.id and o.route_id == route]
            text = found[-1] if found else None
            texts.append(text if text and text.strip() else None)
        while len(texts) < 2:
            texts.append(None)
        width, height = (region.height, region.width) if region.rotation_quarter_turns % 2 else (region.width, region.height)
        png, width, height, padded = pad(crops[region.id], width, height)
        labels.append(Label(number, region.id, png, width, height, (texts[0], texts[1]), padded))
    return tuple(labels)


def request_parts(labels: Sequence[Label]) -> list:
    """The user message's parts, as the benchmark built them (common.build_messages): a line, then per
    label its number and its image, then every reader's text per label, then the call to answer."""
    from pydantic_ai import BinaryContent

    parts: list = [f"One slide with {len(labels)} label{'s' if len(labels) != 1 else ''}. The label images follow."]
    for label in labels:
        parts.append(f"Label {label.number}:")
        parts.append(BinaryContent(data=label.png, media_type="image/png"))
    lines = ["Machine readings of the labels (reader A, reader B). They may be wrong; the images decide."]
    for label in labels:
        for name, text in zip(("A", "B"), label.readers):
            lines.append(f"Label {label.number}, reader {name}: " + ("(nothing returned)" if text is None else
                         "\n" + "\n".join("  " + line for line in text.split("\n"))))
    lines.append("Fill the record: call record_fields.")
    parts.append("\n".join(lines))
    return parts


def input_bound(labels: Sequence[Label], text: str) -> int:
    """At most the input tokens of the request: the instruction's, the texts' and the tool's UTF-8
    bytes, each image at one token per PIXELS_PER_TOKEN square, and the chat template."""
    texts = len(text.encode()) + len(json.dumps(tool_schema()).encode()) + sum(
        len((reader or "").encode()) + 64 for label in labels for reader in label.readers) + 200
    images = sum(math.ceil(label.width / PIXELS_PER_TOKEN) * math.ceil(label.height / PIXELS_PER_TOKEN)
        for label in labels)
    return texts + images + TEMPLATE_TOKENS


# ---- the answer -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Opinion:
    """One field of the answer: its value (None when absent or unsure), the label text it rests on,
    and whether a null value said UNSURE."""

    value: str | None
    evidence: str
    unsure: bool = False


def read_answer(arguments) -> dict[str, Opinion]:
    """The record a record_fields call holds; NotObtained("malformed") when it is not one.

    `arguments` is the call's arguments (a JSON text or an object). It must satisfy the tool schema
    field by field: an object with exactly the 20 fields, each an object with exactly the keys
    `value` (a string or null) and `evidence` (a string). Anything else is malformed: a missing
    field, an extra one, a null entry, a bare value, a number, an extra key inside an entry."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            raise NotObtained("malformed") from None
    if not isinstance(arguments, dict) or set(arguments) != set(FIELDS):
        raise NotObtained("malformed")
    record = {}
    for key in FIELDS:
        entry = arguments[key]
        if not isinstance(entry, dict) or set(entry) != {"value", "evidence"}:
            raise NotObtained("malformed")
        value, evidence = entry["value"], entry["evidence"]
        if not (value is None or isinstance(value, str)) or not isinstance(evidence, str):
            raise NotObtained("malformed")
        evidence = evidence.strip()
        value = value.strip() if isinstance(value, str) and value.strip() else None
        record[key] = Opinion(value, evidence, unsure=value is None and evidence.upper().startswith("UNSURE"))
    return record


# ---- the comparison -------------------------------------------------------------------------------

def shown(value: FieldValue) -> str | None:
    """The value the app shows: normalized, else parsed, else literal, the first with text."""
    return next((text for text in (value.normalized, value.parsed, value.literal) if text and text.strip()), None)


def _iso(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", text.strip())
    if match is None:
        return None
    parts = tuple(int(group) for group in match.groups() if group is not None)
    try:
        date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return None
    return parts


def _number(text: str) -> Decimal | None:
    text = text.strip()
    if not re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
        return None
    try:
        return Decimal(text.replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def folded(text: str) -> str:
    """Accents removed, case folded, only letters and digits kept, and a "." or "," between two
    digits or a "-" or "+" directly before a digit."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).casefold()
    kept = []
    for i, ch in enumerate(plain):
        after = plain[i + 1] if i + 1 < len(plain) else ""
        before = plain[i - 1] if i else ""
        if ch.isalnum():
            kept.append(ch)
        elif ch in ".," and before.isdigit() and after.isdigit():
            kept.append(ch)
        elif ch in "-+" and after.isdigit():
            kept.append(ch)
    return "".join(kept)


def _unit_free(key: str, text: str) -> str:
    """folded(text) without one trailing unit word of the field (UNIT_WORDS), when another word
    precedes it."""
    match = re.search(r"[^\w]*(\w+)[^\w]*$", text)
    if match and folded(match.group(1)) in UNIT_WORDS.get(key, ()) and re.search(r"\w", text[:match.start(1)]):
        text = text[:match.start(1)]
    return folded(text.rstrip(" ,.;:"))


def kind(key: str) -> str:
    return "date" if key in DATES else "number" if key in NUMBERS else "identifier" if key in IDENTIFIERS else "text"


def same(key: str, first: str | None, second: str | None) -> bool:
    """Whether two values of the field `key` agree under its kind's one rule (module docstring)."""
    if not (first and first.strip() and second and second.strip()):
        return False
    how = kind(key)
    if how == "date":
        a, b = _iso(first), _iso(second)
        return a is not None and a == b
    if how == "number":
        a, b = _number(first), _number(second)
        return a is not None and a == b
    if how == "identifier":
        return first.strip().isdigit() and first.strip() == second.strip()
    if key in UNIT_WORDS:
        a, b = _unit_free(key, first), _unit_free(key, second)
    else:
        a, b = folded(first), folded(second)
    return bool(a) and a == b


# ---- whose field it is -----------------------------------------------------------------------------

LOCKS = "human_review_field_locks"
# The decision endpoint's audit actions for a decision on one field, and the field each names
# (after["field_key"], or the taxon for a taxonomy decision).
DECISION_ACTIONS = {"review_field": None, "review_research_candidate": None, "review_authority_resolution": None,
                    "review_taxonomy_resolution": "taxon"}
# The key a decision's audit event carries once the endpoint records the field on the run itself
# (Run.person_decided_fields): an event without it was saved before this change, and is adopted
# once, where the run is loaded (adopt_legacy).
DECIDED_MARK = "person_decided_field"


def authority(run, readings: Sequence[Reading] = ()) -> set[str]:
    """The fields a person holds authority over, by a record on the run, through one function: a
    decision a move or a new run carried (step.human_keys), a research selection a person locked, the
    location reassessment's protected fields (the person's verified decisions), the fields a person
    decided at the decision endpoint (Run.person_decided_fields, legacy decisions adopted at load),
    and a value whose label's transcript a person decided (Reading.person_decided)."""
    from .location_reassessment import KEY as REASSESSMENT
    from .step import human_keys

    dependencies = getattr(run, "dependencies", None) or {}
    held = set(human_keys(run)) | {key for key in dependencies.get(LOCKS) or {} if isinstance(key, str)}
    held |= {key for key in getattr(run, "person_decided_fields", None) or () if isinstance(key, str)}
    marker = dependencies.get(REASSESSMENT)
    if isinstance(marker, Mapping) and isinstance(marker.get("protected"), list):
        held |= {key for key in marker["protected"] if isinstance(key, str)}
    persons = {reading.region_id for reading in readings if reading.person_decided}
    if persons:
        evidence = {item.id: item for item in run.evidence}
        for key, value in run.fields.items():
            regions = {evidence[i].region_id for i in value.evidence_ids if i in evidence} | {value.source_region_id}
            if persons & regions:
                held.add(key)
    return held


def decided(run, key: str) -> None:
    """The decision endpoint: a person decided the field `key`; recorded on the run, durably."""
    if key not in run.person_decided_fields:
        run.person_decided_fields = [*run.person_decided_fields, key]


def _legacy_decision(event, run_id: str) -> str | None:
    if event.action not in DECISION_ACTIONS or (event.before or {}).get("run_id") != run_id:
        return None
    after = event.after or {}
    if DECIDED_MARK in after:
        return None
    key = DECISION_ACTIONS[event.action] or after.get("field_key")
    return key if isinstance(key, str) and key else None


def adopt_legacy(specimen) -> None:
    """A run's field decisions saved before the endpoint recorded them on the run: the specimen's
    review audit names each (DECISION_ACTIONS, this run's id in `before`, no DECIDED_MARK), and they
    join Run.person_decided_fields where the stored record is loaded (active_graph.unpack). A record
    with nothing to adopt is left exactly as stored. A decision the endpoint recorded carries
    DECIDED_MARK and is never adopted, so a history restore to a revision before it keeps the
    restored revision's own list."""
    run = getattr(specimen, "run", None)
    if run is None:
        return
    found = []
    for event in getattr(specimen, "audit", None) or ():
        key = _legacy_decision(event, run.id)
        if key is not None and key not in run.person_decided_fields and key not in found:
            found.append(key)
    if found:
        run.person_decided_fields = [*run.person_decided_fields, *found]


# ---- the derived marks -----------------------------------------------------------------------------

def _settled(value: FieldValue | None) -> bool:
    return value is not None and value.state == ValueState.SUPPORTED and shown(value) is not None


def _other_marks(run) -> set[str]:
    """The fields another rule's `marked:` finding names: that mark already says the value is not
    confirmed, and the second opinion adds none."""
    found = set()
    for finding in getattr(run, "findings", None) or ():
        if finding.reason_code.startswith("marked:"):
            found.add(finding.field_key or finding.reason_code.split(":")[1])
    return found


def judged_fields(run) -> dict:
    """The stored result's judged fields: {field: {compared, value, evidence, verdict}}."""
    stored = getattr(run, "second_opinion", None)
    found = stored.get("fields") if isinstance(stored, Mapping) else None
    return dict(found) if isinstance(found, Mapping) else {}


def derived(run, readings: Sequence[Reading] = ()) -> list[tuple[str, str]]:
    """(field, why) for every mark the stored result and the current values give (module docstring):
    DIFFERS where the recorded verdict for the field's current shown value is "differs", NOT_CHECKED
    where there is none, nothing where it is "agrees". Only a run on the units path (step.units_path),
    the one field research researches."""
    from .step import units_path

    if not units_path(run):
        return []
    entries = judged_fields(run)
    held, others = authority(run, readings), _other_marks(run)
    marks = []
    for key in JUDGED:
        value = run.fields.get(key)
        if key in held or key in others or not _settled(value):
            continue
        entry = entries.get(key)
        verdict = entry.get("verdict") if isinstance(entry, Mapping) and entry.get("compared") == shown(value) else None
        if verdict == AGREES_VERDICT:
            continue
        marks.append((key, DIFFERS if verdict == DIFFERS_VERDICT else NOT_CHECKED))
    return marks


def _labels(run, key: str, readings: Sequence[Reading]) -> list[str]:
    from .ontology_checks import _labels as value_labels

    return value_labels(run, key, readings, {item.id: item for item in run.evidence})


def reasons(run) -> list[str]:
    """The second opinion's reason codes on the run as it is now: `marked:<field>:<label>:<why>` for
    each mark `derived` gives, once per label the value rests on. step.finalize_fields adds them on
    every finalize; nothing stores them."""
    from .step import marked_code, run_readings

    if not getattr(run, "fields", None):
        return []
    readings = run_readings(run)
    return [marked_code(key, label, why) for key, why in derived(run, readings) for label in _labels(run, key, readings)]


def own(code: str) -> bool:
    """Whether a reason code is one of the second opinion's marks."""
    return code.startswith("marked:") and code.endswith((":" + DIFFERS, ":" + NOT_CHECKED))


# Every outcome of a call that was sent is final for the values it asked about (`asked`, kept with the
# stored result): a timeout, a provider error after sending, a second malformed answer, and these two,
# where it may have been sent: it is never asked again for them on Retry, Resume or a recheck; only for a
# value never asked or changed since, or on a new run (due).
UNANSWERED = frozenset({"outcome_unknown", "abandoned"})


def asked_values(run) -> dict:
    """The values the step answers for, as shown, keyed by field: what an intent is opened on."""
    from .step import run_readings

    return {key: shown(run.fields[key]) for key, _ in derived(run, run_readings(run))}


def due(run) -> bool:
    """Whether the step is due: a value it answers for has no recorded verdict for its current
    shown value (its mark would be NOT_CHECKED), and no unanswered call was made on these same values."""
    from .step import run_readings

    need = [key for key, why in derived(run, run_readings(run)) if why == NOT_CHECKED]
    if not need:
        return False
    stored = getattr(run, "second_opinion", None)
    asked = stored.get("asked") if isinstance(stored, Mapping) and stored.get("status") == NOT_OBTAINED else None
    if not isinstance(asked, Mapping):
        return True
    # Field by field over the fields it answers for now: asked again only for a value never asked or
    # changed since; a field that left the set (a person took it) never causes it.
    return any(key not in asked or asked[key] != shown(run.fields[key]) for key in need)


def finish(run) -> None:
    """The record finalized once the step has ended, however it ended: the reasons field research's
    finalize gave it, with the second opinion's codes derived again from the stored result and the
    current values (reasons); cleared when no reason is left, else for review. No field, finding or
    other reason changes."""
    from specimen_digitization.application.domain import Disposition

    kept = [code for code in run.reasons if not own(code)]
    run.reasons = list(dict.fromkeys((*kept, *reasons(run))))
    run.blocker = None
    run.disposition = Disposition.REVIEW if run.reasons else Disposition.CLEARED
    run.stage = "finalized"


# ---- the call ---------------------------------------------------------------------------------------

async def ask(model, labels: Sequence[Label], text: str, meter, *, deadline: float, sent: list | None = None) -> object:
    """One request (the instruction and the labels), built first, then reserved on `meter` at its
    worst case and settled at the provider's reported usage, or at its worst case (zero after an HTTP
    429) when it fails after the reservation; the request and the client's closing are both cut at
    `deadline` (time.monotonic). Returns the record_fields call's arguments. NotObtained when the
    request is not made or not answered by one record_fields call. `sent` gets one item per request
    reserved."""
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolCallPart, UserPromptPart
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.tools import ToolDefinition

    from .budget import BudgetExhausted
    from .experts import _close_client

    messages = [ModelRequest(parts=[SystemPromptPart(content=text), UserPromptPart(content=request_parts(labels))])]
    parameters = ModelRequestParameters(output_mode="tool", allow_text_output=False, output_tools=[
        ToolDefinition(name=TOOL_NAME, parameters_json_schema=tool_schema(), description=TOOL_DESCRIPTION)])
    bound = input_bound(labels, text)
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise NotObtained("no_time")
    try:
        ticket = await meter.reserve(bound, MAX_TOKENS)
    except BudgetExhausted:
        raise NotObtained("budget") from None
    if sent is not None:
        sent.append(ticket)
    settled = False
    try:
        try:
            # As the experts bound theirs (experts.py, asyncio.timeout), with the gateway client's own
            # timeout beneath it (production_model: ClientTimeouts).
            async with asyncio.timeout(timeout):
                response = await model.request(messages, {"max_tokens": MAX_TOKENS}, parameters)
        finally:
            try:
                await asyncio.wait_for(_close_client(model), max(0.0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                # An answer already received stands (the coordinator's ruling on round 4, 7).
                LOGGER.warning("second opinion: the client did not close before the deadline")
    except asyncio.TimeoutError:
        raise NotObtained("timeout") from None
    except Exception as error:  # noqa: BLE001 - a provider error is the answer: not obtained
        status = getattr(error, "status_code", None)
        if status == 429:
            meter.settle(ticket, 0, 0)
            settled = True
        raise NotObtained(f"provider_error{'_' + str(status) if status else ''}") from None
    else:
        usage = response.usage
        if usage.has_values():
            meter.settle(ticket, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, reported=True)
            settled = True
    finally:
        if not settled:
            # Sent and not answered with usage, or not known whether it was sent: its worst case.
            meter.settle(ticket, bound, MAX_TOKENS)
    calls = [part for part in response.parts if isinstance(part, ToolCallPart) and part.tool_name == TOOL_NAME]
    if len(calls) != 1:
        raise NotObtained("no_tool_call")
    return calls[0].args


@dataclass
class Result:
    """What one run of the step obtained: its status and why, the judged fields and the answer when
    obtained, and what its request cost (`spent` None: unknown, the reservation stays held)."""

    status: str
    reason: str | None = None
    fields: dict | None = None
    answer: object = None
    labels: dict | None = None
    padded: list = field(default_factory=list)
    spent: int | None = 0
    tokens: dict | None = None
    requests: int = 0


# The stored answer is the 20 values and their supporting text, each cut at TEXT_LIMIT characters: a
# few kilobytes at most (20 fields x 2 texts x 300 characters), whatever the model returned.
TEXT_LIMIT = 300


def clip(text: str | None) -> str | None:
    return text if text is None or len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT]


def bounded_answer(record: Mapping[str, Opinion]) -> dict:
    """The answer as stored: {field: {value, evidence}}, each text clipped (clip)."""
    return {key: {"value": clip(record[key].value), "evidence": clip(record[key].evidence)} for key in FIELDS}


def bounded(call: Callable, deadline: float):
    """`call()` in a worker thread, waited for until `deadline` (time.monotonic) at most: NotObtained
    ("no_time") when it has not returned by then (the thread is left to end on its own; nothing waits
    for it)."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as Late

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="second-opinion")
    try:
        return pool.submit(call).result(timeout=max(0.0, deadline - time.monotonic()))
    except Late:
        raise NotObtained("no_time") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def obtain(run, *, model_factory: Callable, crops: Callable, price, seconds: float, meter_factory: Callable) -> Result:
    """Ask and compare (module docstring), inside `seconds`: reading the crops (`crops()`, {region id:
    PNG bytes}, in a worker thread waited for until the deadline), the request and the client's closing
    (ask) all end by it. A malformed answer (no record_fields call, or one the schema refuses) is asked
    again once with a new model (`model_factory()`) while time and the meter's cap allow; a second is
    "malformed". Never raises an Exception: anything that goes wrong is a Result not obtained, with
    its code. The run is not changed."""
    deadline = time.monotonic() + seconds
    spent, tokens, sent, padded = 0, None, [], []
    meter = None
    try:
        if price is None:
            raise NotObtained("unconfigured")
        if seconds < MIN_SECONDS:
            raise NotObtained("no_time")
        text = instruction()
        labels = labels_of(run, bounded(crops, deadline))
        padded = [label.number for label in labels if label.padded]
        if not labels:
            raise NotObtained("no_labels")
        meter = meter_factory(CAP_MICROS, price)
        for request in range(REQUESTS):
            if deadline - time.monotonic() < MIN_SECONDS:
                raise NotObtained("no_time")
            try:
                model = model_factory()
            except Exception:  # noqa: BLE001 - no request was made
                raise NotObtained("unconfigured") from None
            try:
                arguments = asyncio.run(ask(model, labels, text, meter, deadline=deadline, sent=sent))
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except ValueError:
                        raise NotObtained("malformed") from None
                record = read_answer(arguments)
                break
            except NotObtained as reason:
                if reason.code not in ("malformed", "no_tool_call") or request + 1 == REQUESTS:
                    raise
        fields = {}
        for key in JUDGED:
            value = run.fields.get(key)
            if _settled(value):
                opinion = record[key]
                fields[key] = {"compared": shown(value), "value": clip(opinion.value), "evidence": clip(opinion.evidence),
                    "verdict": AGREES_VERDICT if same(key, shown(value), opinion.value) else DIFFERS_VERDICT}
        result = Result(OBTAINED, fields=fields, answer=bounded_answer(record), padded=padded,
            labels={str(label.number): label.region_id for label in labels})
    except NotObtained as reason:
        result = Result(NOT_OBTAINED, reason.code, padded=padded)
    except Exception:  # noqa: BLE001 - the step never fails the run
        LOGGER.warning("second opinion not obtained", exc_info=True)
        result = Result(NOT_OBTAINED, "error", padded=padded)
    if meter is not None:
        spent = meter.spent_micros if meter.outstanding_micros == 0 else None
        tokens = getattr(meter, "reported", None)
    result.spent, result.tokens, result.requests = spent, tokens, len(sent)
    return result


def record(run, result: Result, *, attempt: int, at: str) -> None:
    """The run's one stored result (Run.second_opinion). Obtained: the status, the judged fields and
    the answer replace what was there. Not obtained or switched off: the status, why and the attempt;
    verdicts an earlier answer gave on values that are still current keep deriving their marks."""
    from specimen_digitization.model_gateway import SECOND_OPINION_ROUTE

    previous = run.second_opinion if isinstance(run.second_opinion, Mapping) else {}
    stored = {"status": result.status, "attempt": attempt, "route": SECOND_OPINION_ROUTE, "at": at}
    if result.status == OBTAINED:
        stored.update(instruction_sha256=INSTRUCTION_SHA256, fields=result.fields or {}, answer=result.answer,
            labels=result.labels or {}, padded_labels=list(result.padded))
    else:
        if result.reason:
            stored["reason"] = result.reason
        stored.update({key: previous[key] for key in ("instruction_sha256", "fields", "answer", "labels",
            "padded_labels") if key in previous})
        # Coverage of sent calls (`asked`): the values an intent opens on wait in `asking`, and join
        # `asked` field by field once a request was sent (or may have been); an outcome that sent nothing
        # never removes or replaces what earlier sent calls asked.
        before = dict(previous.get("asked") or {})
        if result.status == ASKING:
            stored["asking"] = asked_values(run)
        elif previous.get("status") == ASKING and (result.reason in UNANSWERED or result.requests):
            before.update(previous.get("asking") or {})
        if before:
            stored["asked"] = before
    run.second_opinion = stored


def open_intent(run) -> bool:
    """Whether the step's intent is open on the run: saved before its request, its result not yet."""
    stored = getattr(run, "second_opinion", None)
    return isinstance(stored, Mapping) and stored.get("status") == ASKING


def paid_call(run, *, attempt: int, reserved: int, result: Result) -> None:
    """The step's one paid-call entry, in lane_costs' shape (field_research.step.record_cost's): what the
    provider reported, or the reservation when that is not known; the run's token total gets the
    reported tokens."""
    from specimen_digitization.application.domain import now
    from specimen_digitization.model_gateway import SECOND_OPINION_ROUTE

    prices = run.profile.execution.price_list
    known = result.spent is not None
    usage = {"model_calls": result.requests}
    if result.tokens:
        usage.update(reported_requests=result.tokens["requests"], input_tokens=result.tokens["input_tokens"],
            cached_input_tokens=result.tokens["cached_input_tokens"], output_tokens=result.tokens["output_tokens"])
        run.usage.tokens += result.tokens["input_tokens"] + result.tokens["output_tokens"]
    run.paid_calls.append({
        "step": STEP,
        "attempt": attempt,
        "kind": "model",
        "route_id": SECOND_OPINION_ROUTE,
        "reserved_micros": reserved,
        "usage": usage if known else None,
        "outcome": "completed" if result.status == OBTAINED else "failed" if known else "unknown",
        "cost_micros": result.spent if known else reserved,
        "cost_basis": "computed" if known else "reserved",
        **({"failure_code": result.reason} if result.reason else {}),
        "price_list": {"version": prices["version"], "as_of": prices["as_of"]},
        "at": now(),
    })
    if any(call["cost_basis"] == "reserved" for call in run.paid_calls):
        run.usage.actual_cost_micros = None
    elif known:
        run.usage.actual_cost_micros = (run.usage.actual_cost_micros or 0) + result.spent


def abandon(run, code: str = "abandoned") -> bool:
    """The step's open intent ends "not obtained" with `code`, its request's spend unknown: its paid
    call is recorded at the whole reservation, held (the run's reserved cost, the monthly caps' and the
    program's ledgers keep it, as for any call whose outcome is unknown); its lease and reserved time
    go. Whether there was one to abandon."""
    from specimen_digitization.application.domain import now

    if not open_intent(run):
        return False
    attempt = run.second_opinion.get("attempt") or run.attempts.get(STEP, 1)
    if not any(call["step"] == STEP and call["attempt"] == attempt for call in run.paid_calls):
        paid_call(run, attempt=attempt, reserved=0 if run.profile.synthetic else CAP_MICROS,
            result=Result(NOT_OBTAINED, code, spent=None))
    record(run, Result(NOT_OBTAINED, code), attempt=attempt, at=now())
    run.lease_until = None
    timeout = run.profile.execution.effect_timeout_for_step(STEP)
    run.usage.reserved_active_seconds = max(0, run.usage.reserved_active_seconds - timeout)
    return True


def at_finalize(run) -> list[str]:
    """step.finalize_fields' hook: anything that finalizes the run while the step's intent is open (a
    person's decision, its approval, research again) abandons that intent first (abandon), so it never
    stands as an unknown outcome; then the derived marks (reasons)."""
    abandon(run)
    return reasons(run)


def route_price(run):
    """The second opinion's price row in the run's profile, or None."""
    from specimen_digitization.model_gateway import SECOND_OPINION_ROUTE

    from .step import profile_of

    try:
        prices = profile_of(run).processing.price_list
    except Exception:  # noqa: BLE001 - a profile that does not read prices nothing
        return None
    return prices.models.get(SECOND_OPINION_ROUTE) if prices is not None else None


def production_model():
    """The second opinion's model through the Hugging Face gateway, wrapped as an expert's is
    (PrivateProviderModel, ClientTimeouts)."""
    import os

    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise RuntimeError("provider_data_policy_and_spending_approval_required")
    from specimen_digitization.model_gateway import SECOND_OPINION_ROUTE, HuggingFaceModelGateway
    from specimen_digitization.provider_privacy import PrivateProviderModel

    from .experts import ClientTimeouts

    gateway = HuggingFaceModelGateway(timeout_seconds=TIMEOUT_SECONDS)
    return PrivateProviderModel(ClientTimeouts(gateway.model_for(SECOND_OPINION_ROUTE)))


def _cost_meter(cap_micros: int, price):
    from .step import cost_meter

    return cost_meter(cap_micros, price)


@dataclass
class SecondOpinionStep:
    """The workflow's second-opinion runner (Workflow.second_opinion, mounted by
    research_harness.workflow_bridge): `model_factory()` returns the model the one request goes to,
    `meter_factory(cap_micros, price)` the meter it reserves on. A workflow without one has the step
    switched off: it runs, writes the status and asks nothing."""

    model_factory: Callable = production_model
    meter_factory: Callable = _cost_meter


def production_step() -> SecondOpinionStep:
    return SecondOpinionStep()
