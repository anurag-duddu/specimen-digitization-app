"""The fields' second opinion: a value field research settled is shown as settled only when an
independent strong model, filling the record on its own, agrees (autonomy program, lane F1;
docs/execution/golive/FIELD_RESEARCH.md, "The second opinion").

Measured basis (the program's fields benchmark, 2026-11-18, ~/specimen-golive/runs/
autonomy-fields-20261118/final/score_fields.md, K1's locality comparison): on the cleared records of
the 100 truth slides, Muse Spark Open 816B, given the same label crops, the readers' transcriptions
and the field definitions but never the pipeline's fields, agreed with 299 of the pipeline's 355
settled values on the 67 slides it answered, 5 of them wrong (39 of the 355 were wrong); four in five
of the values it disagreed on were wrong. Small samples: 2 wrong in 280 has a 95 % upper bound near
3 %.

THE STEP (FieldResearchStep.run calls `check` once per attempt, after research has settled the fields,
their checks have run and a location reassessment's values are committed, before the clearance
rules). One model call on SECOND_OPINION_ROUTE: the system message is the instruction
(prompts/second_opinion.txt, pinned by INSTRUCTION_SHA256); the user message holds every label crop
of the slide in label order, then each label's two readers' transcriptions (reader A and reader B,
the profile's first two reader routes), exactly as the benchmark built it. The model answers the tool
record_fields (TOOL): the 20 fields, each {value, evidence}. The request carries nothing of the
pipeline's fields (`request_parts` reads only the regions' crops and the observations' texts).

WHICH FIELDS IT JUDGES (`scope`): the values this attempt wrote (a field whose value differs from
the one it had when the step began: researched, derived, inferred, or replaced by a location
reassessment), and the fields an earlier attempt left NOT_CHECKED; of those, a value settled with
text (supported, normalized, parsed or literal non-blank) that carries no `marked:` finding already
and that no person holds authority over (`person_holds`). Never the catalogue number (it has its own
evidence, the slide's QR code: catalogue_code.py) nor the determiner's IRN (the instruction asks for
none). A field left open or blank is not judged: the second opinion's value for it is stored as
evidence only.

THE COMPARISON (`same`), one strict rule per kind of field, on the value the app shows (normalized,
else parsed, else literal) against the second opinion's value:
- dates (Date Visited From and To, Date Identified): both must be ISO dates (YYYY, YYYY-MM or
  YYYY-MM-DD that the calendar accepts) and equal at the same precision;
- numbers (the four elevations): both must be plain decimal numbers (a thousands comma allowed)
  and equal once each is rounded to the hundredth;
- identifiers (the catalogue number, never judged here): the same digits, digit for digit;
- text (everything else): equal once accents are removed (NFKD, combining marks dropped), case is
  folded, and every character that is not a letter or a digit is dropped (white space and
  punctuation folded). Province/State and County also set aside one trailing unit word on either
  side (UNIT_WORDS), as the benchmark's comparison does.
Agree: nothing changes. Differ, or the second opinion gives no value (the label does not carry the
field, or it is unsure): the field gets a warning finding of rule RULE,
`marked:<field>:<label>:second_opinion_differs` (step.marked_reasons makes it one of the run's
reasons), citing an evidence row of kind EVIDENCE_KIND that holds the second opinion's value and the
label text it rests on.

WHAT IT NEVER DOES: change a field's value, state, layers or reason text; remove any finding but its
own; un-mark or clear anything; judge a field a person holds; fail the run. When the second opinion is
not obtained (no route price, an exception, a provider error such as HTTP 402, a timeout, a spent
budget, an answer that is not one record_fields call holding every judged field, or a second call in
the same attempt), every field it would have judged gets `marked:<field>:<label>:second_opinion_not_checked`
in place of a verdict: an unchecked value is not confirmed, shown on its field. Nothing holds the
record beyond what a mark does. `guarded` puts the fields, findings, evidence and the step's record
back on any exception inside the comparison and marks the scope not checked.

A person deciding a field drops this rule's findings on it (`forget`, called by the decision
endpoint); refinalize and the decision endpoint compute nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
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
RULE_VERSION = "field-research-second-opinion-v1"
DIFFERS = "second_opinion_differs"
NOT_CHECKED = "second_opinion_not_checked"
# The run-level note of an attempt whose second opinion was not obtained (an info finding, never a
# reason): `second_opinion_not_obtained:<code>`.
NOT_OBTAINED = "second_opinion_not_obtained"
EVIDENCE_KIND = "second_opinion"
EVIDENCE_SOURCE = "second_opinion"
# run.dependencies[STATE]: the attempt that asked, the route, and how it went.
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
# The longest the call may take (the benchmark's slowest answer took 27 s), within what the step's
# deadline leaves.
TIMEOUT_SECONDS = 90.0
MIN_SECONDS = 10.0

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


def labels_of(run, crop: Callable) -> tuple[Label, ...]:
    """The slide's labels in their order (Region.order), numbered from 1, each with its crop
    (`crop(region)` -> PNG bytes) and the last text of each of the profile's first two reader routes
    (None where that reader returned nothing)."""
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
        labels.append(Label(number, region.id, crop(region), width, height, (texts[0], texts[1])))
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

    `arguments` is the call's arguments (a JSON text or an object). Each of the judged fields must be
    present; a field's entry is {value, evidence} (value a string, a number, which becomes its text, or
    null; evidence a string, or absent) or null (nothing on the label). The catalogue number and the IRN
    may be missing. A key outside the 20 fields, or any other shape, is malformed."""
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
        if not isinstance(entry, dict) or set(entry) - {"value", "evidence"}:
            raise NotObtained("second_opinion_malformed")
        value, evidence = entry.get("value"), entry.get("evidence")
        if isinstance(value, bool) or not (value is None or isinstance(value, (str, int, float))):
            raise NotObtained("second_opinion_malformed")
        if isinstance(value, float) and not math.isfinite(value):
            raise NotObtained("second_opinion_malformed")
        if isinstance(value, (int, float)):
            value = str(int(value)) if float(value) == int(value) else repr(value)
        if evidence is not None and not isinstance(evidence, str):
            raise NotObtained("second_opinion_malformed")
        evidence = (evidence or "").strip()
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
    """Accents removed, case folded, only letters and digits kept."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return "".join(ch for ch in plain.casefold() if ch.isalnum())


def _unit_free(key: str, text: str) -> str:
    """folded(text) without one trailing unit word of the field (UNIT_WORDS), when another word
    precedes it."""
    words = [word for word in (folded(part) for part in re.split(r"[^\w]+", text)) if word]
    if len(words) > 1 and words[-1] in UNIT_WORDS.get(key, ()):
        words = words[:-1]
    return "".join(words)


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
        a, b = re.sub(r"\D", "", first), re.sub(r"\D", "", second)
        return bool(a) and a == b and first.strip().isdigit() and second.strip().isdigit()
    if key in UNIT_WORDS:
        a, b = _unit_free(key, first), _unit_free(key, second)
    else:
        a, b = folded(first), folded(second)
    return bool(a) and a == b


# ---- whose field it is ----------------------------------------------------------------------------

LOCKS = "human_review_field_locks"


def person_holds(run, readings: Sequence[Reading] = (), human: Collection[str] = ()) -> set[str]:
    """The fields a person holds authority over by a record on the run: `human` (step.human_keys, the
    decisions a move to the units path carried), a research selection a person locked, the location
    reassessment's `protected` list (the person's verified decisions), and a value whose label a person
    transcribed (Reading.person_decided). Lane Q1's function (PR #454), unchanged."""
    from .location_reassessment import KEY as REASSESSMENT

    dependencies = getattr(run, "dependencies", None) or {}
    held = set(human) | {key for key in dependencies.get(LOCKS) or {} if isinstance(key, str)}
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


def _not_checked(run) -> set[str]:
    return {finding.field_key for finding in run.findings
        if finding.rule_id == RULE and finding.reason_code.endswith(":" + NOT_CHECKED) and finding.field_key}


def scope(run, before: Mapping[str, FieldValue], *, readings: Sequence[Reading], human: Collection[str] = ()) -> list[str]:
    """The fields this attempt's second opinion judges (module docstring): the values this attempt
    wrote and the fields an earlier attempt left not checked, settled with text, carrying no mark of
    another rule, held by no person, and neither the catalogue number nor the IRN."""
    held = person_holds(run, readings, human)
    retry = _not_checked(run)
    # A mark of another rule (a label's settlement, the check stage): the field is a person's already.
    others = {finding.field_key for finding in run.findings
        if finding.rule_id != RULE and finding.reason_code.startswith("marked:")}
    others |= {code.split(":")[1] for code in _other_marks(run)}
    found = []
    for key in JUDGED:
        value = run.fields.get(key)
        if key in held or key in others or not _settled(value):
            continue
        if value == before.get(key) and key not in retry:
            continue
        found.append(key)
    return found


def _other_marks(run) -> list[str]:
    """The run's `marked:` codes of rules other than this one (step.marked_reasons)."""
    from .step import marked_reasons

    own = {finding.reason_code for finding in run.findings if finding.rule_id == RULE}
    return [code for code in marked_reasons(run) if code.count(":") >= 2 and code not in own]


def forget(run, key: str) -> None:
    """A person decided or selected the field `key`: this rule's findings on it go. Nothing is
    recomputed; nothing else on the run changes (the evidence rows stay, as every row does)."""
    run.findings[:] = [finding for finding in run.findings if not (finding.rule_id == RULE and finding.field_key == key)]


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
    """Compare and mark (module docstring), and store the second opinion's value as evidence for every
    judged field that differs and every field the pipeline left open or blank where the second opinion
    gives a value. Returns {field: "agrees" | "differs" | "evidence"}."""
    outcome = {}
    judged_set = set(judged)
    for key in JUDGED:
        opinion = record[key]
        value = run.fields.get(key) or FieldValue()
        if key in judged_set:
            if same(key, shown(value), opinion.value):
                outcome[key] = "agrees"
                continue
            outcome[key] = "differs"
        elif not _settled(value) and opinion.value is not None and value.state != ValueState.SUPPORTED:
            outcome[key] = "evidence"
        else:
            continue
        row = Evidence(kind=EVIDENCE_KIND, asset_id=asset_id, region_id=_region_of(opinion.evidence, labels),
            source=EVIDENCE_SOURCE, locator=f"second_opinion:{key}", excerpt=excerpt(key, opinion),
            raw_ref=raw_ref, digest=raw_digest if raw_ref else None)
        run.evidence.append(row)
        if outcome[key] == "differs":
            _mark(run, key, DIFFERS, readings, [row.id])
    return outcome


def not_checked(run, judged: Sequence[str], code: str, *, readings: Sequence[Reading]) -> None:
    """Mark every judged field not checked, and note once on the run why."""
    for key in judged:
        _mark(run, key, NOT_CHECKED, readings)
    run.findings.append(RunFinding(rule_id=RULE, rule_version=RULE_VERSION, severity="info",
        reason_code=f"{NOT_OBTAINED}:{code}"))


# ---- the call -------------------------------------------------------------------------------------

async def ask(model, labels: Sequence[Label], text: str, meter, *, timeout: float) -> tuple[object, int]:
    """One request (the instruction and the labels), reserved on `meter` at its worst case and settled
    at the provider's reported usage; the record_fields call's arguments. NotObtained when the request
    is not made or not answered by one record_fields call."""
    from pydantic_ai.messages import ModelRequest, SystemPromptPart, ToolCallPart, UserPromptPart
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.tools import ToolDefinition

    from .budget import BudgetExhausted

    bound = input_bound(labels, text)
    try:
        ticket = await meter.reserve(bound, MAX_TOKENS)
    except BudgetExhausted:
        raise NotObtained("second_opinion_budget") from None
    messages = [ModelRequest(parts=[SystemPromptPart(content=text), UserPromptPart(content=request_parts(labels))])]
    parameters = ModelRequestParameters(output_mode="tool", allow_text_output=False, output_tools=[
        ToolDefinition(name=TOOL_NAME, parameters_json_schema=tool_schema(), description=TOOL_DESCRIPTION)])
    from .experts import _close_client

    try:
        try:
            response = await asyncio.wait_for(model.request(messages, {"max_tokens": MAX_TOKENS}, parameters), timeout)
        finally:
            await _close_client(model)
    except asyncio.TimeoutError:
        meter.settle(ticket, bound, MAX_TOKENS)
        raise NotObtained("second_opinion_timeout") from None
    except Exception as error:  # noqa: BLE001 - a provider error is the answer: not obtained
        status = getattr(error, "status_code", None)
        if status == 429:
            meter.settle(ticket, 0, 0)
        else:
            meter.settle(ticket, bound, MAX_TOKENS)
        raise NotObtained(f"second_opinion_provider_error{'_' + str(status) if status else ''}") from None
    usage = response.usage
    if usage.has_values():
        meter.settle(ticket, usage.input_tokens, usage.output_tokens, usage.cache_read_tokens, reported=True)
    else:
        meter.settle(ticket, bound, MAX_TOKENS)
    calls = [part for part in response.parts if isinstance(part, ToolCallPart) and part.tool_name == TOOL_NAME]
    if len(calls) != 1:
        raise NotObtained("second_opinion_no_tool_call")
    return calls[0].args, bound


@dataclass
class Paid:
    """The step's one paid call, for step.record_cost: what it reserved and spent (None: unknown)."""

    reserved: int
    spent: int | None = None
    tokens: dict | None = None
    outcome: str = "failed"
    model_calls: int = 1


def check(run, before: Mapping[str, FieldValue], *, route: str | None, model_factory: Callable | None,
        crop: Callable, blobs, asset_id: str | None, readings: Sequence[Reading], human: Collection[str],
        cap_micros: int, meter_factory: Callable, price, timeout: float) -> Paid | None:
    """The step: judge the fields in `scope` once for this attempt. Returns the paid call (Paid) when
    a request was reserved, else None. Never raises: on any exception the run's fields, findings and
    evidence are put back as they were and the judged fields are marked not checked."""
    from .step import STEP

    attempt = run.attempts.get(STEP, 1)
    kept_fields = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    kept_findings, kept_evidence = list(run.findings), list(run.evidence)
    previous = run.dependencies.get(STATE)
    judged: list[str] = []
    paid: Paid | None = None
    try:
        judged = scope(run, before, readings=readings, human=human)
        if not judged:
            return None
        # This attempt's verdicts replace this rule's earlier findings on the fields it judges.
        run.findings[:] = [f for f in run.findings if not (f.rule_id == RULE and f.field_key in judged)]
        if isinstance(previous, Mapping) and previous.get("attempt") == attempt:
            raise NotObtained("second_opinion_already_asked")
        run.dependencies[STATE] = {"attempt": attempt, "route": route, "status": "asking"}
        if model_factory is None or price is None or route is None:
            raise NotObtained("second_opinion_unconfigured")
        if timeout < MIN_SECONDS:
            raise NotObtained("second_opinion_no_time")
        text = instruction()
        labels = labels_of(run, crop)
        if not labels:
            raise NotObtained("second_opinion_no_labels")
        try:
            model = model_factory()
        except Exception:  # noqa: BLE001 - no request was made
            raise NotObtained("second_opinion_unconfigured") from None
        cap = min(CAP_MICROS, max(0, cap_micros))
        meter = meter_factory(cap, price)
        paid = Paid(reserved=cap)
        try:
            arguments, _ = asyncio.run(ask(model, labels, text, meter, timeout=timeout))
        finally:
            paid.spent = meter.spent_micros if meter.outstanding_micros == 0 else None
            paid.tokens = getattr(meter, "reported", None)
            paid.model_calls = 1 if meter.spent_micros or meter.outstanding_micros else 0
        record = read_answer(arguments)
        stored = json.dumps({"route": route, "attempt": attempt, "instruction_sha256": INSTRUCTION_SHA256,
            "arguments": arguments, "labels": {str(label.number): label.region_id for label in labels}},
            sort_keys=True, ensure_ascii=False, default=str).encode()
        raw_ref = blobs.put(stored) if blobs is not None else None
        outcome = apply(run, record, judged, labels=labels, readings=readings, asset_id=asset_id,
            raw_ref=raw_ref, raw_digest=hashlib.sha256(stored).hexdigest())
        run.dependencies[STATE] = {"attempt": attempt, "route": route, "status": "obtained", "fields": outcome}
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
    run.findings[:] = [f for f in kept_findings if not (f.rule_id == RULE and f.field_key in judged)]
    try:
        not_checked(run, judged, code, readings=readings)
    except Exception:  # noqa: BLE001 - the marks never fail research either
        LOGGER.warning("second opinion: not-checked marks failed", exc_info=True)
        run.findings[:] = kept_findings
    if not (isinstance(previous, Mapping) and previous.get("attempt") == attempt):
        run.dependencies[STATE] = {"attempt": attempt, "route": route, "status": f"not_obtained:{code}"}
    return paid
