"""The specimen ontology: specimen.yaml, loaded, validated and rendered.

The conceptual model of this collection's labels is one file, readable by
people and by code (docs/product-requirements/
FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 5). Version 1.0 (plan WP 1.0)
holds the things, the profile's 20 fields with their Darwin Core terms, the
label notations with every reading each allows, the fields a kind of unit
could belong to, and the questions waiting for the owner's reading.

The loader refuses a key it does not know, a field that is not one of the
profile's 20 (application/domain.py MANDATORY), and an entry with no source.
`render` gives the text a model's instructions carry: its brief form is in
the first pass's prompt (WP 1.2; prompts.py), the whole text is for the
experts' (WP 1.3). `advice`
gives what the file says about one unit's text: the fields it could belong to
and the readings of its notations, or the open question it holds.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ..application.domain import MANDATORY

PATH = Path(__file__).with_name("specimen.yaml")


class OntologyError(ValueError):
    """The file breaks a rule of the loader."""


# What a word in angle brackets stands for in a written form (common.txt:4: a
# word in angle brackets stands for whatever the label writes there). A Roman
# month is written in capitals; the longer numerals come first so that "XII"
# is not read as "X".
PLACEHOLDERS = {
    "n": r"\d+",
    "d": r"\d{1,2}",
    "dd": r"\d{1,2}",
    "d1": r"\d{1,2}",
    "d2": r"\d{1,2}",
    "mm": r"\d{1,2}",
    "a": r"\d{1,2}",
    "b": r"\d{1,2}",
    "yy": r"\d{2}",
    "yyyy": r"\d{4}",
    "Roman month": r"(?:XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)",
    "letter": r"[^\W\d_]",
}
_PIECE = re.compile(r"<([^<>]*)>|( +)|([^<> ]+)")


@dataclass(frozen=True)
class Thing:
    id: str
    name: str
    examples: str
    darwin_core: str
    source: tuple[str, ...]


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    darwin_core: str
    holds: str
    source: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class Route:
    """A kind of unit no notation names, and the fields it could belong to."""

    id: str
    unit: str
    fields: tuple[str, ...]
    means: str
    source: tuple[str, ...]


@dataclass(frozen=True)
class Notation:
    id: str
    written: tuple[str, ...]
    readings: tuple[str, ...]
    fields: tuple[str, ...]
    source: tuple[str, ...]
    note: str = ""
    periods_optional: bool = False
    patterns: tuple[re.Pattern[str], ...] = field(default=(), compare=False, repr=False)


@dataclass(frozen=True)
class Question:
    """A question for the owner's reading: about units (`written`, matched in
    a unit's text; the unit then carries no field) or about one notation's
    entry (`notation`, never matched; the entry stands until the reading)."""

    id: str
    written: tuple[str, ...]
    question: str
    context: str
    answered_in: str
    source: tuple[str, ...]
    notation: str = ""
    periods_optional: bool = False
    patterns: tuple[re.Pattern[str], ...] = field(default=(), compare=False, repr=False)


@dataclass(frozen=True)
class Advice:
    """What the file says about one unit's text."""

    fields: tuple[str, ...] = ()
    means: tuple[str, ...] = ()
    notations: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ontology:
    version: str
    frame: Mapping[str, Any]
    things: tuple[Thing, ...]
    fields: tuple[Field, ...]
    routing: tuple[Route, ...]
    notation_rule: str
    notations: tuple[Notation, ...]
    questions: tuple[Question, ...]

    def advice(self, text: str, kind: str | None = None) -> Advice:
        """The fields and readings the file gives a unit's text.

        Every written form of every notation and question is looked for in
        the text; a match inside a longer match is dropped (no part of a
        slide code is a date). A unit that holds an open question carries no
        field and no reading until the owner's reading (spec section 5).
        `kind` names a routing entry, a judgement of the unit no notation
        makes (a place's name): its fields follow the notations'."""
        route = None
        if kind is not None:
            route = next((entry for entry in self.routing if entry.id == kind), None)
            if route is None:
                raise OntologyError(f"no routing entry {kind!r}")
        found = [
            (match.start(), match.end(), entry)
            for entry in (*self.questions, *self.notations)
            for pattern in entry.patterns
            for match in pattern.finditer(text)
            if match.end() > match.start()
        ]
        kept = sorted(
            (item for item in found if not any(
                other[0] <= item[0] and item[1] <= other[1]
                and other[1] - other[0] > item[1] - item[0]
                for other in found)),
            key=lambda item: (item[0], item[1]),
        )
        questions = _unique(entry.id for _, _, entry in kept if isinstance(entry, Question))
        if questions:
            return Advice(questions=questions)
        notations = [entry for _, _, entry in kept if isinstance(entry, Notation)]
        notations = list({entry.id: entry for entry in notations}.values())
        fields = [key for entry in notations for key in entry.fields]
        means = [reading for entry in notations for reading in entry.readings]
        if route is not None:
            fields += route.fields
            means.append(route.means)
        return Advice(
            fields=_unique(fields),
            means=_unique(means),
            notations=tuple(entry.id for entry in notations),
        )

    def render(self, brief: bool = False) -> str:
        """The ontology as a model's instructions carry it.

        `brief` is the first pass's text (docs/execution/units/PLAN.md, WP 1.2): the fields by
        key, display name and Darwin Core term, where a unit could belong, the notations and the
        open questions. It leaves out the things, each field's description and the rule for
        writing a literal, which serve the experts that write values; the first pass writes
        none, and its call has a cost bound."""
        frame = self.frame
        lines = [
            f"Specimen ontology, version {self.version}. Its frame is the "
            f"{frame['name']} ({frame['reference']}).",
        ]
        if not brief:
            lines += ["", "Things the labels describe (examples on labels; the Darwin Core class and terms):"]
            lines += [f"- {thing.name}: {thing.examples} (in Darwin Core, {thing.darwin_core})." for thing in self.things]
        if brief:
            lines += ["", "The profile's 20 fields (key, display name, Darwin Core term):"]
            lines += [f"- {entry.key} ({entry.label}), {entry.darwin_core}" for entry in self.fields]
        else:
            lines += ["", "The profile's 20 fields (key, display name, Darwin Core term: what it holds):"]
            for entry in self.fields:
                note = f" {_sentence(entry.note)}" if entry.note else ""
                lines.append(f"- {entry.key} ({entry.label}), {entry.darwin_core}: {entry.holds}{note}")
        lines += [
            "",
            "The fields a unit could belong to are advice only: every field's expert receives "
            "every unit. A notation below names its fields. Where no notation does:",
        ]
        lines += [
            f"- {_capital(route.unit)}: {', '.join(route.fields)}. {_capital(_sentence(route.means))}"
            for route in self.routing
        ]
        lines += [
            "",
            "Label notations and every reading each allows. A word in angle brackets stands "
            "for what the label writes there: <n> a number; <d>, <dd>, <d1>, <d2>, <mm>, <a> "
            "and <b> a day's or a month's one or two digits; <yy> a two-digit year; <yyyy> a "
            "four-digit year; <Roman month> a Roman numeral I to XII; <letter> one letter.",
        ]
        if not brief:
            lines.append(self.notation_rule)
        for notation in self.notations:
            written = ", ".join(f'"{form}"' for form in notation.written)
            readings = "; or ".join(notation.readings)
            where = f" [{', '.join(notation.fields)}]" if notation.fields else " [no field]"
            note = f" {_sentence(notation.note)}" if notation.note else ""
            lines.append(f"- {written}: {readings}{where}.{note}")
        lines += ["", "Open questions that wait for the owner's reading; until then a unit holding one carries no field."]
        for question in self.questions:
            if question.written:
                written = ", ".join(f'"{form}"' for form in question.written)
                lines.append(f"- {written}: {question.question}")
        about = [question for question in self.questions if question.notation]
        if about:
            lines.append("Open questions about a notation above, whose entry stands until the owner's reading:")
            notations = {notation.id: notation for notation in self.notations}
            for question in about:
                written = ", ".join(f'"{form}"' for form in notations[question.notation].written)
                lines.append(f"- {written}: {question.question}")
        return "\n".join(lines) + "\n"


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _sentence(text: str) -> str:
    return text if text.endswith((".", "?", "!")) else text + "."


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


class _Loader(yaml.SafeLoader):
    """A safe loader that refuses a key written twice in one mapping."""


def _mapping(loader: _Loader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise OntologyError(f"key {key!r} written twice (line {key_node.start_mark.line + 1})")
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _entry(value: Any, where: str, required: set[str], optional: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise OntologyError(f"{where} must be a mapping")
    unknown = sorted(set(value) - required - optional, key=str)
    if unknown:
        raise OntologyError(f"{where}: unknown key {unknown[0]!r}")
    missing = sorted(required - set(value))
    if "source" in missing:
        raise OntologyError(f"{where} has no source")
    if missing:
        raise OntologyError(f"{where}: missing key {missing[0]!r}")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OntologyError(f"{where} must be a non-empty string")
    return value.strip()


def _texts(value: Any, where: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not empty):
        raise OntologyError(f"{where} must be a {'' if empty else 'non-empty '}list")
    return tuple(_text(item, f"{where}[{index}]") for index, item in enumerate(value))


def _source(value: dict, where: str) -> tuple[str, ...]:
    """The entry's sources: a non-empty list, no item empty."""
    sources = value.get("source")
    if (not isinstance(sources, list) or not sources
            or any(not isinstance(item, str) or not item.strip() for item in sources)):
        raise OntologyError(f"{where} has no source")
    return tuple(item.strip() for item in sources)


def _fields(value: Any, where: str) -> tuple[str, ...]:
    keys = _texts(value, where, empty=True)
    for key in keys:
        if key not in MANDATORY:
            raise OntologyError(f"{where}: {key!r} is not one of the profile's 20 fields")
    if len(set(keys)) != len(keys):
        raise OntologyError(f"{where} names a field twice")
    return keys


def _flag(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise OntologyError(f"{where} must be true or false")
    return value


def _patterns(forms: tuple[str, ...], periods_optional: bool, where: str) -> tuple[re.Pattern[str], ...]:
    """Each written form as a pattern (the file's header states the rules)."""
    patterns = []
    for form in forms:
        pieces = list(_PIECE.finditer(form))
        if "".join(piece.group(0) for piece in pieces) != form:
            raise OntologyError(f"{where}: {form!r} has an angle bracket that opens no placeholder")
        parts = []
        for index, piece in enumerate(pieces):
            name, space, literal = piece.groups()
            if name is not None:
                if name not in PLACEHOLDERS:
                    raise OntologyError(f"{where}: {form!r} uses the unknown placeholder <{name}>")
                parts.append(PLACEHOLDERS[name])
            elif space is not None:
                parts.append(r"\s*")
            elif periods_optional and index == len(pieces) - 1 and literal.endswith("."):
                parts.append(f"(?i:{re.escape(literal[:-1])})" if literal[:-1] else "")
                parts.append(r"(?:\.|(?!\w))")
            else:
                parts.append(f"(?i:{re.escape(literal)})")
        first, last = form[0], form[-1]
        begins_in_a_word = pieces[0].group(1) is not None or first.isalnum()
        ends_in_a_word = pieces[-1].group(1) is not None or last.isalnum()
        before = r"(?<!\w)" if begins_in_a_word else ""
        after = r"(?!\w)" if ends_in_a_word else ""
        patterns.append(re.compile(before + "".join(parts) + after))
    return tuple(patterns)


def _unique_ids(entries, where: str) -> None:
    ids = [entry.id for entry in entries]
    if len(set(ids)) != len(ids):
        raise OntologyError(f"{where}: an id is written twice")


TOP = {"version", "frame", "things", "fields", "routing", "notation_rule", "notations", "questions"}


def parse(data: Any) -> Ontology:
    """The ontology from the file's parsed contents; refused when it breaks a rule."""
    top = _entry(data, "the file", TOP)
    frame = _entry(top["frame"], "frame", {"name", "reference", "source"})
    _text(frame["name"], "frame.name")
    _text(frame["reference"], "frame.reference")
    _source(frame, "frame")

    things = []
    for index, value in enumerate(_list(top["things"], "things")):
        where = f"things[{index}]"
        entry = _entry(value, where, {"id", "name", "examples", "darwin_core", "source"})
        things.append(Thing(
            id=_text(entry["id"], f"{where}.id"),
            name=_text(entry["name"], f"{where}.name"),
            examples=_text(entry["examples"], f"{where}.examples"),
            darwin_core=_text(entry["darwin_core"], f"{where}.darwin_core"),
            source=_source(entry, where),
        ))
    _unique_ids(things, "things")

    fields = []
    for index, value in enumerate(_list(top["fields"], "fields")):
        where = f"fields[{index}]"
        entry = _entry(value, where, {"key", "label", "darwin_core", "holds", "source"}, frozenset({"note"}))
        key = _text(entry["key"], f"{where}.key")
        if key not in MANDATORY:
            raise OntologyError(f"{where}: {key!r} is not one of the profile's 20 fields")
        fields.append(Field(
            key=key,
            label=_text(entry["label"], f"{where}.label"),
            darwin_core=_text(entry["darwin_core"], f"{where}.darwin_core"),
            holds=_text(entry["holds"], f"{where}.holds"),
            source=_source(entry, where),
            note=_text(entry["note"], f"{where}.note") if "note" in entry else "",
        ))
    keys = [entry.key for entry in fields]
    if sorted(keys) != sorted(MANDATORY):
        missing = [key for key in MANDATORY if key not in keys]
        raise OntologyError(f"fields must list each of the profile's 20 fields once; missing {missing}")

    routing = []
    for index, value in enumerate(_list(top["routing"], "routing")):
        where = f"routing[{index}]"
        entry = _entry(value, where, {"id", "unit", "fields", "means", "source"})
        routing.append(Route(
            id=_text(entry["id"], f"{where}.id"),
            unit=_text(entry["unit"], f"{where}.unit"),
            fields=_fields(entry["fields"], f"{where}.fields"),
            means=_text(entry["means"], f"{where}.means"),
            source=_source(entry, where),
        ))
    _unique_ids(routing, "routing")

    rule = _entry(top["notation_rule"], "notation_rule", {"text", "source"})
    _source(rule, "notation_rule")

    notations = []
    for index, value in enumerate(_list(top["notations"], "notations")):
        where = f"notations[{index}]"
        entry = _entry(value, where, {"id", "written", "readings", "fields", "source"},
                       frozenset({"note", "periods_optional"}))
        written = _texts(entry["written"], f"{where}.written")
        optional = _flag(entry.get("periods_optional", False), f"{where}.periods_optional")
        notations.append(Notation(
            id=_text(entry["id"], f"{where}.id"),
            written=written,
            readings=_texts(entry["readings"], f"{where}.readings"),
            fields=_fields(entry["fields"], f"{where}.fields"),
            source=_source(entry, where),
            note=_text(entry["note"], f"{where}.note") if "note" in entry else "",
            periods_optional=optional,
            patterns=_patterns(written, optional, where),
        ))
    _unique_ids(notations, "notations")

    questions = []
    for index, value in enumerate(_list(top["questions"], "questions")):
        where = f"questions[{index}]"
        entry = _entry(value, where, {"id", "question", "context", "answered_in", "source"},
                       frozenset({"written", "notation", "periods_optional"}))
        if ("written" in entry) == ("notation" in entry):
            raise OntologyError(f"{where} needs written forms or a notation, not both")
        written = _texts(entry["written"], f"{where}.written") if "written" in entry else ()
        notation = _text(entry["notation"], f"{where}.notation") if "notation" in entry else ""
        if notation and notation not in {item.id for item in notations}:
            raise OntologyError(f"{where}: no notation {notation!r}")
        optional = _flag(entry.get("periods_optional", False), f"{where}.periods_optional")
        questions.append(Question(
            id=_text(entry["id"], f"{where}.id"),
            written=written,
            notation=notation,
            question=_text(entry["question"], f"{where}.question"),
            context=_text(entry["context"], f"{where}.context"),
            answered_in=_text(entry["answered_in"], f"{where}.answered_in"),
            source=_source(entry, where),
            periods_optional=optional,
            patterns=_patterns(written, optional, where),
        ))
    _unique_ids(questions, "questions")

    return Ontology(
        version=_text(top["version"], "version"),
        frame=dict(frame),
        things=tuple(things),
        fields=tuple(fields),
        routing=tuple(routing),
        notation_rule=_text(rule["text"], "notation_rule.text"),
        notations=tuple(notations),
        questions=tuple(questions),
    )


def _list(value: Any, where: str) -> list:
    if not isinstance(value, list) or not value:
        raise OntologyError(f"{where} must be a non-empty list")
    return value


def read(text: str) -> Ontology:
    """The ontology from the file's text."""
    try:
        data = yaml.load(text, Loader=_Loader)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as error:
        raise OntologyError(f"the file is not valid YAML: {error}") from error
    return parse(data)


@cache
def ontology() -> Ontology:
    """The ontology of the file this package ships."""
    return read(PATH.read_text(encoding="utf-8"))


def render(brief: bool = False) -> str:
    """The shipped ontology as a model's instructions carry it (`brief`: the first pass's)."""
    return ontology().render(brief)
