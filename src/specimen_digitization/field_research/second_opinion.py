"""The fields' second opinion: a value field research settled is shown as settled only when an
independent strong model, filling the record on its own, agrees (autonomy program, lane F1;
docs/execution/golive/FIELD_RESEARCH.md, "The second opinion").

Measured basis (the program's fields benchmark, 2026-11-18, ~/specimen-golive/runs/
autonomy-fields-20261118/final/score_fields.md, K1's locality comparison): on the cleared records of
the 100 truth slides, Muse Spark Open 816B, given the same label crops, the readers' transcriptions
and the field definitions but never the pipeline's fields, agreed with 299 of the pipeline's 355
settled values on the 67 slides it answered, 5 of them wrong (39 of the 355 were wrong). This code's
own replay of the same answers marks 60 values as differing, 35 of them wrong. Small samples: 2 wrong
in 280 has a 95 % upper bound near 3 %.

THE STEP (FieldResearchStep.run calls `check` once per attempt, after research has settled the fields,
their checks have run and a location reassessment's values are committed, before the clearance
rules). One model call on SECOND_OPINION_ROUTE: the system message is the instruction
(prompts/second_opinion.txt, pinned by INSTRUCTION_SHA256); the user message holds every label crop
of the slide in label order, then each label's two readers' transcriptions (reader A and reader B,
the profile's first two reader routes), exactly as the benchmark built it. A crop longer than
MAX_ASPECT times its width (or the reverse) is padded with a white border to that ratio, centred,
since the provider refuses it otherwise; the stored answer records which labels were padded. The
model answers the tool record_fields (TOOL): the 20 fields, each {value, evidence}. The request
carries nothing of the pipeline's fields (`request_parts` reads only the crops and the observations'
texts).

COVERAGE IS RECORDED (`responsible`, `covered`). The step is responsible for every value settled with
text (supported, normalized, parsed or literal non-blank) that no other rule marks and that no
person holds authority over (`person_holds`: a decision carried to the units path, a locked research
selection, a location reassessment's protected field, a value whose label a person transcribed, and
run.person_decided_fields, the fields a person decided at the decision endpoint). Never the
catalogue number (its own evidence is the slide's QR code: catalogue_code.py) nor the determiner's
IRN. After the step every such value carries exactly one verdict, kept in
run.dependencies[STATE]["coverage"] with the value it was given on: `agrees` (an info finding
`second_opinion_agrees:<field>` citing an evidence row of the second opinion's value), `differs` (a
warning `marked:<field>:<label>:second_opinion_differs`, one of the run's reasons) or `not_checked`
(a warning `marked:<field>:<label>:second_opinion_not_checked`). A value is judged when it has no
verdict, its verdict was given on another value, or its verdict is not_checked; a recorded agree or
differs on the same value stands. The step first drops this rule's findings and verdicts on every
field it is not responsible for (a person's, an open one, one another rule marks), so a stale mark
cannot outlive a person's decision or transcript correction. A field left open or blank is not
judged: the second opinion's value for it is stored as an evidence row only.

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

NOT OBTAINED: when the step is off (no model factory) or has no route or price, when research still
has a retryable failure to ask again (`research_pending`: the money stays with research), when the
time left is below what the step needs, the budget is spent, the provider errs (HTTP 402 included),
the request times out, the answer is not one record_fields call that satisfies the tool schema field
by field, a second request would be sent in the same attempt, or any exception: every value it would
have judged gets `not_checked`, and one info finding `second_opinion_not_obtained:<code>` says why.
An unchecked value is not confirmed, shown on its field; nothing holds the record beyond what a mark
does. Fields, findings and evidence are put back before the marks are added; the run never fails.

TIME: the whole step, from reading the crops to storing the evidence, runs inside `seconds`, which
the caller takes from what the enclosing step and the worker's deadline leave, less the clearance
rules' margin. It does not start below MIN_SECONDS; it checks the clock before the request; the
request is the only call whose time is not bounded by its size, and it is cut at the budget's end
less STORE_SECONDS, which the evidence storage (one blob write) needs. So the step ends before the
deadline the caller gave it, and the worker's deadline (WorkerDeadlineExceeded) lies beyond that.

A person deciding a field adds it to run.person_decided_fields and drops this rule's findings on it
(`forget`, called by the decision endpoint); refinalize and the decision endpoint compute nothing.
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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from specimen_digitization.application.domain import Evidence, FieldValue, RunFinding, ValueState

from .contracts import Reading

LOGGER = logging.getLogger(__name__)

RULE = "second_opinion"
RULE_VERSION = "field-research-second-opinion-v2"
DIFFERS = "second_opinion_differs"
NOT_CHECKED = "second_opinion_not_checked"
AGREES = "second_opinion_agrees"
# The run-level note of an attempt whose second opinion was not obtained (an info finding, never a
# reason): `second_opinion_not_obtained:<code>`.
NOT_OBTAINED = "second_opinion_not_obtained"
EVIDENCE_KIND = "second_opinion"
EVIDENCE_SOURCE = "second_opinion"
# run.dependencies[STATE]: the attempt that last asked, its route and status, and the verdicts.
STATE = "second_opinion"
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
# output tool forced. The step's own cap, in micro-USD: one request's worst case at list (an input
# bound of about 14,000 tokens for a four-label slide and 8,000 output tokens is about USD 0.052; the
# benchmark's dearest answer cost USD 0.038, its mean 0.012).
MAX_TOKENS = 8_000
CAP_MICROS = 60_000
# Each image's tokens are bounded by one token per 28 by 28 pixels (the readers' rule; the benchmark's
# Muse Spark calls reported about a third of that), and the text's by its UTF-8 bytes.
PIXELS_PER_TOKEN = 28
TEMPLATE_TOKENS = 512
# Baseten refused 3 of the benchmark's 70 requests: "Media aspect ratio exceeds 40:1".
MAX_ASPECT = 40
# The longest the call may take (the benchmark's slowest answer took 27 s), within what the step's
# deadline leaves; the least time the step starts with; what storing the evidence is left.
TIMEOUT_SECONDS = 90.0
MIN_SECONDS = 15.0
STORE_SECONDS = 5.0

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
        raise NotObtained("second_opinion_instruction_changed")
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
    """The record a record_fields call holds; NotObtained when it is not one.

    `arguments` is the call's arguments (a JSON text or an object). It must be an object whose keys
    are among the 20 fields and include every judged field. Each entry must satisfy the tool schema:
    an object with exactly the keys `value` (a string or null) and `evidence` (a string). One
    departure is read, as the benchmark read it: an entry that is null is a field the labels do not
    carry. The catalogue number and the IRN may be missing. Anything else is malformed."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            raise NotObtained("second_opinion_malformed") from None
    if not isinstance(arguments, dict) or set(arguments) - set(FIELDS):
        raise NotObtained("second_opinion_malformed")
    if any(key not in arguments for key in JUDGED):
        raise NotObtained("second_opinion_partial")
    record = {}
    for key in FIELDS:
        entry = arguments.get(key)
        if entry is None:
            record[key] = Opinion(None, "")
            continue
        if not isinstance(entry, dict) or set(entry) != {"value", "evidence"}:
            raise NotObtained("second_opinion_malformed")
        value, evidence = entry["value"], entry["evidence"]
        if not (value is None or isinstance(value, str)) or not isinstance(evidence, str):
            raise NotObtained("second_opinion_malformed")
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


# ---- whose field it is, and coverage --------------------------------------------------------------

LOCKS = "human_review_field_locks"


def person_holds(run, readings: Sequence[Reading] = (), human: Collection[str] = ()) -> set[str]:
    """The fields a person holds authority over by a record on the run: `human` (step.human_keys, the
    decisions a move to the units path carried), a research selection a person locked, the location
    reassessment's `protected` list (the person's verified decisions), the fields a person decided at
    the decision endpoint (run.person_decided_fields), and a value whose label a person transcribed
    (Reading.person_decided). Lane Q1's function (PR #454), with the decided fields added."""
    from .location_reassessment import KEY as REASSESSMENT

    dependencies = getattr(run, "dependencies", None) or {}
    held = set(human) | {key for key in dependencies.get(LOCKS) or {} if isinstance(key, str)}
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


def _settled(value: FieldValue | None) -> bool:
    return value is not None and value.state == ValueState.SUPPORTED and shown(value) is not None


def _other_marks(run) -> set[str]:
    """The fields a `marked:` reason of another rule names (step.marked_reasons)."""
    from .step import marked_reasons

    own = {finding.reason_code for finding in run.findings if finding.rule_id == RULE}
    found = {code.split(":")[1] for code in marked_reasons(run) if code.count(":") >= 2 and code not in own}
    return found | {finding.field_key for finding in run.findings
        if finding.rule_id != RULE and finding.reason_code.startswith("marked:") and finding.field_key}


def responsible(run, *, readings: Sequence[Reading], human: Collection[str] = ()) -> list[str]:
    """The values the step answers for (module docstring): settled with text, marked by no other rule,
    held by no person, and neither the catalogue number nor the IRN."""
    held = person_holds(run, readings, human)
    others = _other_marks(run)
    return [key for key in JUDGED if key not in held and key not in others and _settled(run.fields.get(key))]


def coverage(run) -> dict:
    state = run.dependencies.get(STATE)
    found = state.get("coverage") if isinstance(state, Mapping) else None
    return dict(found) if isinstance(found, Mapping) else {}


def covered(run, key: str) -> bool:
    """A recorded agrees or differs on the value the field holds now."""
    entry = coverage(run).get(key)
    return (isinstance(entry, Mapping) and entry.get("verdict") in ("agrees", "differs")
        and entry.get("value") == shown(run.fields[key]))


def _state(run, **update) -> None:
    state = run.dependencies.get(STATE)
    state = dict(state) if isinstance(state, Mapping) else {}
    state.update(update)
    run.dependencies[STATE] = state


def forget(run, key: str) -> None:
    """A person decided or selected the field `key`: this rule's findings and verdict on it go. Nothing
    is recomputed; nothing else on the run changes (the evidence rows stay, as every row does)."""
    run.findings[:] = [finding for finding in run.findings if not (finding.rule_id == RULE and finding.field_key == key)]
    found = coverage(run)
    if key in found:
        del found[key]
        _state(run, coverage=found)


def decided(run, key: str) -> None:
    """The decision endpoint: the person decided the field `key`, durably (run.person_decided_fields),
    and this rule's findings on it go (forget)."""
    if key not in run.person_decided_fields:
        run.person_decided_fields = [*run.person_decided_fields, key]
    forget(run, key)


def _labels(run, key: str, readings: Sequence[Reading]) -> list[str]:
    from .ontology_checks import _labels as value_labels

    return value_labels(run, key, readings, {item.id: item for item in run.evidence})


def _mark(run, key: str, why: str, readings: Sequence[Reading], evidence_ids: Sequence[str] = ()) -> None:
    from .step import marked_code

    for label in _labels(run, key, readings):
        run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="warning", field_key=key,
            reason_code=marked_code(key, label, why), evidence_ids=list(evidence_ids)))


def _region_of(evidence: str, labels: Sequence[Label]) -> str | None:
    match = re.match(r"\s*L(\d+)\s*:", evidence or "")
    if match is None:
        return None
    number = int(match.group(1))
    return next((label.region_id for label in labels if label.number == number), None)


def excerpt(key: str, opinion: Opinion) -> str:
    """The evidence row's text: the field, the second opinion's value, and the label text it rests on."""
    if opinion.value is not None:
        head = f"{key}: {opinion.value}"
    elif opinion.unsure:
        head = f"{key}: unsure"
    else:
        head = f"{key}: not on the label"
    rest = opinion.evidence[:300]
    return f"Second opinion, {head}" + (f" (label text: {rest})" if rest else "")


def apply(run, record: Mapping[str, Opinion], judged: Sequence[str], *, labels: Sequence[Label],
        readings: Sequence[Reading], asset_id: str | None, raw_ref: str | None, raw_digest: str | None) -> dict:
    """Compare and record (module docstring): every judged field gets an evidence row of the second
    opinion's value and its verdict (an agrees note or a differs mark); every field the pipeline left
    open or blank where the second opinion gives a value gets the row alone. Returns {field: verdict}
    for the judged fields."""
    outcome = {}
    judged_set = set(judged)
    for key in JUDGED:
        opinion = record[key]
        value = run.fields.get(key) or FieldValue()
        if key in judged_set:
            outcome[key] = "agrees" if same(key, shown(value), opinion.value) else "differs"
        elif not (opinion.value is not None and value.state != ValueState.SUPPORTED):
            continue
        row = Evidence(kind=EVIDENCE_KIND, asset_id=asset_id, region_id=_region_of(opinion.evidence, labels),
            source=EVIDENCE_SOURCE, locator=f"second_opinion:{key}", excerpt=excerpt(key, opinion),
            raw_ref=raw_ref, digest=raw_digest if raw_ref else None)
        run.evidence.append(row)
        if outcome.get(key) == "differs":
            _mark(run, key, DIFFERS, readings, [row.id])
        elif outcome.get(key) == "agrees":
            run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info", field_key=key,
                reason_code=f"{AGREES}:{key}", evidence_ids=[row.id]))
    return outcome


def not_checked(run, judged: Sequence[str], code: str, *, readings: Sequence[Reading]) -> None:
    """Mark every judged field not checked, and note once on the run why."""
    for key in judged:
        _mark(run, key, NOT_CHECKED, readings)
    run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info",
        reason_code=f"{NOT_OBTAINED}:{code}"))


# ---- the call -------------------------------------------------------------------------------------

async def ask(model, labels: Sequence[Label], text: str, meter, *, deadline: float) -> object:
    """One request (the instruction and the labels), built first, then reserved on `meter` at its
    worst case and settled at the provider's reported usage, or at its worst case (zero after an HTTP
    429) when it fails after the reservation; cut at `deadline` (time.monotonic) less STORE_SECONDS.
    Returns the record_fields call's arguments. NotObtained when the request is not made or not
    answered by one record_fields call."""
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolCallPart, UserPromptPart
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.tools import ToolDefinition

    from .budget import BudgetExhausted
    from .experts import _close_client

    messages = [ModelRequest(parts=[SystemPromptPart(content=text), UserPromptPart(content=request_parts(labels))])]
    parameters = ModelRequestParameters(output_mode="tool", allow_text_output=False, output_tools=[
        ToolDefinition(name=TOOL_NAME, parameters_json_schema=tool_schema(), description=TOOL_DESCRIPTION)])
    bound = input_bound(labels, text)
    timeout = deadline - STORE_SECONDS - time.monotonic()
    if timeout <= 0:
        raise NotObtained("second_opinion_no_time")
    try:
        ticket = await meter.reserve(bound, MAX_TOKENS)
    except BudgetExhausted:
        raise NotObtained("second_opinion_budget") from None
    settled = False
    try:
        try:
            response = await asyncio.wait_for(model.request(messages, {"max_tokens": MAX_TOKENS}, parameters), timeout)
        finally:
            await _close_client(model)
    except asyncio.TimeoutError:
        raise NotObtained("second_opinion_timeout") from None
    except Exception as error:  # noqa: BLE001 - a provider error is the answer: not obtained
        status = getattr(error, "status_code", None)
        if status == 429:
            meter.settle(ticket, 0, 0)
            settled = True
        raise NotObtained(f"second_opinion_provider_error{'_' + str(status) if status else ''}") from None
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
        raise NotObtained("second_opinion_no_tool_call")
    return calls[0].args


@dataclass
class Paid:
    """The step's one paid call, for step.record_cost: what it reserved and spent (None: unknown)."""

    reserved: int
    spent: int | None = None
    tokens: dict | None = None
    outcome: str = "failed"
    model_calls: int = 1


def check(run, *, route: str | None, model_factory: Callable | None, crops: Callable, blobs,
        asset_id: str | None, readings: Sequence[Reading], human: Collection[str], cap_micros: int,
        meter_factory: Callable, price, seconds: float, research_pending: bool = False) -> Paid | None:
    """The step (module docstring), once for this attempt, inside `seconds`. `crops()` returns
    {region id: PNG bytes}. Returns the paid call (Paid) when a request was reserved, else None.
    Never raises: on any exception the run's fields, findings and evidence are put back as they were
    and the values to judge are marked not checked."""
    from .step import STEP

    deadline = time.monotonic() + seconds
    attempt = run.attempts.get(STEP, 1)
    previous = run.dependencies.get(STATE)
    asked = isinstance(previous, Mapping) and previous.get("attempt") == attempt and previous.get("asked")
    mine = responsible(run, readings=readings, human=human)
    # This rule's findings and verdicts on any field it does not answer for now go first, and the
    # previous attempt's run-level note.
    run.findings[:] = [f for f in run.findings if not (f.rule_id == RULE and (f.field_key is None
        or f.field_key not in mine))]
    found = {key: entry for key, entry in coverage(run).items() if key in mine}
    _state(run, coverage=found)
    judged = [key for key in mine if not covered(run, key)]
    if not judged:
        return None
    run.findings[:] = [f for f in run.findings if not (f.rule_id == RULE and f.field_key in judged)]
    kept_fields = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    kept_findings, kept_evidence = list(run.findings), list(run.evidence)
    paid: Paid | None = None
    padded: list[int] = []
    try:
        if asked:
            raise NotObtained("second_opinion_already_asked")
        if model_factory is None or price is None or route is None:
            raise NotObtained("second_opinion_unconfigured")
        if research_pending:
            raise NotObtained("second_opinion_research_pending")
        if seconds < MIN_SECONDS:
            raise NotObtained("second_opinion_no_time")
        _state(run, attempt=attempt, route=route, asked=True, status="asking")
        text = instruction()
        labels = labels_of(run, crops())
        padded = [label.number for label in labels if label.padded]
        if not labels:
            raise NotObtained("second_opinion_no_labels")
        if deadline - time.monotonic() < MIN_SECONDS:
            raise NotObtained("second_opinion_no_time")
        try:
            model = model_factory()
        except Exception:  # noqa: BLE001 - no request was made
            raise NotObtained("second_opinion_unconfigured") from None
        cap = min(CAP_MICROS, max(0, cap_micros))
        meter = meter_factory(cap, price)
        paid = Paid(reserved=cap)
        try:
            arguments = asyncio.run(ask(model, labels, text, meter, deadline=deadline))
        finally:
            paid.spent = meter.spent_micros if meter.outstanding_micros == 0 else None
            paid.tokens = getattr(meter, "reported", None)
            paid.model_calls = 1 if meter.spent_micros or getattr(meter, "reported", {}).get("requests") else 0
        record = read_answer(arguments)
        stored = json.dumps({"route": route, "attempt": attempt, "instruction_sha256": INSTRUCTION_SHA256,
            "arguments": arguments, "labels": {str(label.number): label.region_id for label in labels},
            "padded_labels": padded}, sort_keys=True, ensure_ascii=False, default=str).encode()
        raw_ref = blobs.put(stored) if blobs is not None else None
        outcome = apply(run, record, judged, labels=labels, readings=readings, asset_id=asset_id,
            raw_ref=raw_ref, raw_digest=hashlib.sha256(stored).hexdigest())
        found.update({key: {"verdict": verdict, "value": shown(run.fields[key]), "attempt": attempt}
            for key, verdict in outcome.items()})
        _state(run, coverage=found, status="obtained", padded_labels=padded)
        paid.outcome = "completed"
        return paid
    except NotObtained as reason:
        code = reason.code
    except Exception:  # noqa: BLE001 - the second opinion never fails research
        LOGGER.warning("second opinion not obtained: fields marked not checked", exc_info=True)
        code = "second_opinion_error"
    # Not obtained: put back what this step changed, then mark the judged fields not checked.
    run.fields.clear()
    run.fields.update(kept_fields)
    run.evidence[:] = kept_evidence
    run.findings[:] = kept_findings
    try:
        not_checked(run, judged, code, readings=readings)
    except Exception:  # noqa: BLE001 - the marks never fail research either
        LOGGER.warning("second opinion: not-checked marks failed", exc_info=True)
        run.findings[:] = kept_findings
    found.update({key: {"verdict": "not_checked", "value": shown(run.fields[key]), "attempt": attempt}
        for key in judged})
    _state(run, coverage=found, **({} if asked else {"status": f"not_obtained:{code}"}))
    return paid
