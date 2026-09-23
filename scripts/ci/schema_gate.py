#!/usr/bin/env python3
"""Offline additive-only gate for Data Connect schema and connector changes (RELEASE.md 4.1).

It parses only the SDL and operations this repository uses and fails closed on
anything else, naming the construct kind and never file content. Each refusal
names the table, field or operation and the rule, never a value: workflow logs
are public.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
# The data contract's reasons. A relation field may drop NOT NULL with the named column its @ref covers.
NAMED_RELAXATIONS = {("SourceAsset", "width"): "raw model responses are assets without pixels",
                     ("SourceAsset", "height"): "raw model responses are assets without pixels",
                     ("LabelRegion", "cropAssetId"): "the domain's crop is optional"}
PROTECTED = frozenset(("ModelObservation", field) for field in ("runId", "regionId", "provider", "modelVersion", "stepKey"))
TYPE_DIRECTIVES, FIELD_DIRECTIVES = {"table", "view", "unique", "index"}, {"default", "ref", "unique", "index", "col"}
KEYWORDS = {"type", "enum", "input", "interface", "union", "scalar", "directive", "extend", "schema", "fragment",
            "subscription", "query", "mutation"}
AUTH, ACTOR = "@auth(level: NO_ACCESS)", "$actorUid: String!"
MEMBERSHIP = "organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check("
# GraphQL lexing: commas are insignificant like whitespace, a comment runs to the line end, and a string
# (a block string too, with \""" escaped) is one token, so its braces, quotes and '#' never count.
TOKEN = re.compile(r'(?P<skip>[\s,]+|#[^\n\r]*)|(?P<block>"""(?:\\"""|(?!""")[\s\S])*+""")'
                   r'|(?P<string>"(?:\\.|[^"\\\n\r])*")|(?P<name>[_A-Za-z][_0-9A-Za-z]*)'
                   r'|(?P<number>-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)|(?P<punct>\.\.\.|[!$():=@\[\]{}])'
                   r'|(?P<error>[\s\S])')
QUOTED_NAME = re.compile(r'"[_A-Za-z][_0-9A-Za-z]*"')


def _tokens(text: str) -> list[tuple[str, str]]:
    tokens = [(match.lastgroup, match.group()) for match in TOKEN.finditer(text) if match.lastgroup != "skip"]
    if any(kind == "error" for kind, _ in tokens):
        raise ValueError("unterminated string or unsupported character")
    return tokens


def _find(tokens: list[str], needle: str) -> list[int]:
    """Where a token sequence starts; text inside a string or a comment never matches."""
    wanted = [token for _, token in _tokens(needle)]
    return [at for at in range(len(tokens) - len(wanted) + 1) if tokens[at:at + len(wanted)] == wanted]


class _Stream:
    """A cursor over tokens; an unexpected token or the end of the tokens fails closed."""

    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens, self.at = tokens, 0

    def peek(self) -> str | None:
        return self.tokens[self.at][1] if self.at < len(self.tokens) else None

    def next(self, *expected: str) -> tuple[str, str]:
        kind, token = self.tokens[self.at] if self.at < len(self.tokens) else ("end", None)
        if kind == "end" or (expected and token not in expected):
            raise ValueError(f"expected {' or '.join(expected)}" if expected else "unexpected end of source")
        self.at += 1
        return kind, token

    def name(self) -> str:
        kind, token = self.next()
        if kind != "name":
            raise ValueError("expected a name")
        return token

    def group(self) -> list[tuple[str, str]]:
        """Consume one balanced (...) or {...} and return the tokens inside it."""
        opener = self.next("(", "{")[1]
        closer, begin, depth = {"(": ")", "{": "}"}[opener], self.at, 1
        while depth:
            token = self.next()[1]
            depth += (token == opener) - (token == closer)
        return self.tokens[begin:self.at - 1]


def _definitions(text: str, keywords: tuple[str, ...], what: str):
    """Each top-level `keyword Name (...)? @directive(...)* {...}` as keyword, name, header and body tokens."""
    stream = _Stream(_tokens(text))
    while stream.peek() is not None:
        start = stream.at
        kind, keyword = stream.next()
        if kind != "name" or keyword not in keywords:
            raise ValueError(f"unsupported {what} construct: {keyword if kind == 'name' and keyword in KEYWORDS else kind}")
        name = stream.name()
        while stream.peek() != "{":
            if stream.peek() == "(":
                stream.group()
            else:
                stream.next("@")
                stream.name()
        header = stream.tokens[start:stream.at]
        yield keyword, name, header, stream.group()


def _value(stream: _Stream, nested: bool = False) -> str | tuple:
    """A scalar's token, or a list of scalars as a tuple; anything else fails closed."""
    kind, token = stream.next()
    if token == "[" and not nested:
        items = []
        while stream.peek() != "]":
            items.append(_value(stream, True))
        stream.next("]")
        return tuple(items)
    if kind in ("string", "block", "number", "name"):
        return token
    raise ValueError(f"unsupported directive argument ({kind})")


def _directives(stream: _Stream) -> list[tuple[str, tuple]]:
    """Directives as (name, arguments sorted by name); argument order carries no meaning."""
    found = []
    while stream.peek() == "@":
        stream.next()
        name, arguments = stream.name(), {}
        if stream.peek() == "(":
            stream.next()
            while not arguments or stream.peek() != ")":
                argument = stream.name()
                stream.next(":")
                if argument in arguments:
                    raise ValueError(f"duplicate argument in @{name}")
                arguments[argument] = _value(stream)
            stream.next(")")
        found.append((name, tuple(sorted(arguments.items()))))
    return found


def _group(found: list, allowed: set[str], where: str) -> dict[str, tuple[str, ...]]:
    """Canonical text per directive name: single spaces between parts, values verbatim."""
    grouped: dict[str, list[str]] = {}
    for name, arguments in found:
        if name not in allowed:
            raise ValueError(f"unsupported directive @{name} on {where}")
        inner = ", ".join(f"{key}: " + (f"[{', '.join(value)}]" if isinstance(value, tuple) else value)
                          for key, value in arguments)
        grouped.setdefault(name, []).append(f"@{name}({inner})" if arguments else f"@{name}")
    return {name: tuple(sorted(texts)) for name, texts in grouped.items()}


def _names(directive: str, argument: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The field names one argument of a canonical directive lists, such as @ref fields or @table key."""
    ((_, arguments),) = _directives(_Stream(_tokens(directive)))
    value = dict(arguments).get(argument)
    if value is None:
        return default
    values = value if isinstance(value, tuple) else (value,)
    if not all(isinstance(item, str) and QUOTED_NAME.fullmatch(item) for item in values):
        raise ValueError(f"unsupported {argument} argument")
    return tuple(item[1:-1] for item in values)


def _sql(name: str, directive: str | None) -> str:
    """The SQL name of a type or field: its directive's name argument, else Data Connect's snake case."""
    explicit = _names(directive, "name") if directive else ()
    return explicit[0] if explicit else re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _type(stream: _Stream) -> tuple[str, str]:
    """A type reference as its base name and its list and NOT NULL shape: [String!]! is ("String", "[!]!")."""
    if stream.peek() != "[":
        base, shape = stream.name(), ""
    else:
        stream.next()
        base, inner = _type(stream)
        shape = f"[{inner}{stream.next(']')[1]}"
    return base, shape + (stream.next()[1] if stream.peek() == "!" else "")


def parse_schema(files: dict[str, str]) -> dict[str, dict]:
    """Every type as {kind, directives, fields}, each directive as canonical text under its name."""
    types: dict[str, dict] = {}
    for text in files.values():
        for _, name, header, body in _definitions(text, ("type",), "schema"):
            head, stream, fields = _Stream(header[2:]), _Stream(body), {}
            directives = _group(_directives(head), TYPE_DIRECTIVES, name)
            kinds = [key for key in ("table", "view") if key in directives]
            if name in types:
                raise ValueError(f"duplicate type {name}")
            if head.peek() is not None or len(kinds) != 1 or len(directives[kinds[0]]) != 1:
                raise ValueError(f"{name}: not exactly one @table or @view")
            while stream.peek() is not None:
                field = stream.name()
                stream.next(":")
                base, shape = _type(stream)
                grouped = _group(_directives(stream), FIELD_DIRECTIVES, f"{name}.{field}")
                if field in fields or any(len(texts) > 1 for texts in grouped.values()):
                    raise ValueError(f"{name}.{field}: duplicate field or directive")
                fields[field] = {"type": base, "list": shape.removesuffix("!"), "non_null": shape.endswith("!"),
                                 "directives": {key: texts[0] for key, texts in grouped.items()}}
            types[name] = {"kind": kinds[0], "directives": directives, "fields": fields}
    return types


def parse_connector(files: dict[str, str]) -> dict[str, dict]:
    """Every operation as {kind, header, body}: its tokens joined by single spaces, without comments or commas."""
    operations: dict[str, dict] = {}
    for text in files.values():
        for keyword, name, header, body in _definitions(text, ("query", "mutation"), "connector"):
            if name in operations:
                raise ValueError(f"duplicate operation {name}")
            operations[name] = {"kind": keyword, "header": " ".join(token for _, token in header),
                                "body": " ".join(token for _, token in body)}
    return operations


def _relaxed(table: str, field: str, fields: dict) -> bool:
    """A named relaxation, or a relation whose @ref covers a named relaxation that is nullable too."""
    ref = fields[field]["directives"].get("ref")
    return (table, field) in NAMED_RELAXATIONS or ref is not None and any(
        (table, column) in NAMED_RELAXATIONS and column in fields and not fields[column]["non_null"]
        for column in _names(ref, "fields"))


def _table(name: str, old: dict, new: dict, types: dict) -> list[str]:
    refusals = [f"{name}: @table key or name changed"] if new["directives"]["table"] != old["directives"]["table"] else []
    for kind in ("unique", "index"):
        before, after = Counter(old["directives"].get(kind, ())), Counter(new["directives"].get(kind, ()))
        if before - after:
            refusals.append(f"{name}: type-level @{kind} removed or changed")
        if any(field in old["fields"] for text in after - before for field in _names(text, "fields")):
            refusals.append(f"{name}: new type-level @{kind} over an existing field")
    # NOT NULL never drops on a key (id by default) or a field- or type-level @unique field.
    guarded: set[str] = set()
    for table in (old, new):
        guarded |= set(_names(table["directives"]["table"][0], "key", ("id",)))
        guarded |= {field for field, value in table["fields"].items() if "unique" in value["directives"]}
        guarded |= {field for text in table["directives"].get("unique", ()) for field in _names(text, "fields")}
    for field, was in sorted(old["fields"].items()):
        now, where = new["fields"].get(field), f"{name}.{field}"
        if now is None:
            refusals.append(f"{where}: field removed or renamed")
            continue
        if (now["type"], now["list"]) != (was["type"], was["list"]):
            refusals.append(f"{where}: type or list shape changed")
        for key in sorted(set(was["directives"]) | set(now["directives"])):
            if was["directives"].get(key) != now["directives"].get(key):
                change = "added" if key not in was["directives"] else "removed" if key not in now["directives"] else "changed"
                refusals.append(f"{where}: @{key} {change}")
        if now["non_null"] and not was["non_null"]:
            refusals.append(f"{where}: NOT NULL added")
        elif was["non_null"] and not now["non_null"]:
            if (name, field) in PROTECTED or field in guarded:
                refusals.append(f"{where}: NOT NULL dropped on a key, unique or provenance field")
            elif not _relaxed(name, field, new["fields"]):
                refusals.append(f"{where}: NOT NULL dropped outside the named relaxations")
    columns = {_sql(field, value["directives"].get("col")) for field, value in old["fields"].items()}
    for field, now in sorted(new["fields"].items()):
        if field in old["fields"]:
            continue
        where, ref = f"{name}.{field}", now["directives"].get("ref")
        foreign = _names(ref, "fields") if ref else ()
        if now["non_null"]:
            refusals.append(f"{where}: new field on an existing table must be nullable")
        if _sql(field, now["directives"].get("col")) in columns:
            refusals.append(f"{where}: new field over an existing column")
        if foreign and all(column in old["fields"] for column in foreign):
            refusals.append(f"{where}: new foreign key over existing fields only")
        # Implicit foreign-key columns follow a naming convention and may already exist.
        elif not foreign and now["type"] in types:
            refusals.append(f"{where}: new relation without @ref fields over a new field")
    return refusals


def _operations(live: dict, merged: dict) -> list[str]:
    refusals = [f"{name}: operation {'changed' if name in merged else 'removed or renamed'}"
                for name, operation in sorted(live.items()) if merged.get(name) != operation]
    actor = len(_tokens(ACTOR))
    for name, operation in sorted(merged.items()):
        if name in live:
            continue
        header, body = ([token for _, token in _tokens(operation[part])] for part in ("header", "body"))
        if len(_find(header, "@auth")) != 1 or not _find(header, AUTH):
            refusals.append(f"{name}: new operation not at {AUTH}")
        # A default would let a caller omit the actor that the membership check binds.
        if not any(header[at + actor:at + actor + 1] != ["="] for at in _find(header, ACTOR)):
            refusals.append(f"{name}: new operation does not declare {ACTOR}")
        if not _find(body, MEMBERSHIP):
            refusals.append(f"{name}: new operation without the organizationMember @check")
        # A skipped or excluded field runs no @check.
        if any(_find(tokens, directive) for tokens in (header, body) for directive in ("@skip", "@include")):
            refusals.append(f"{name}: new operation uses @skip or @include")
    return refusals


def check_additive(live_schema: dict[str, str], merged_schema: dict[str, str],
                   live_connector: dict[str, str], merged_connector: dict[str, str]) -> list[str]:
    """Refusals for the merged sources against the live ones, per RELEASE.md 4.1; empty means additive.

    An empty live schema source is the placeholder: there is nothing to compare,
    and the caller initializes instead of calling this. Called anyway, it raises
    rather than admit every merged type as new; so does any unparseable source.
    """
    live, merged = parse_schema(live_schema), parse_schema(merged_schema)
    if not live:
        raise ValueError("the live schema is the empty placeholder; the release initializes instead")
    refusals = []
    for name, old in sorted(live.items()):
        new = merged.get(name)
        if old["kind"] == "view":
            if new != old:
                refusals.append(f"{name}: view {'changed' if new else 'removed or renamed'}")
        elif new is None or new["kind"] != "table":
            refusals.append(f"{name}: table removed or renamed")
        else:
            refusals += _table(name, old, new, merged)
    existing = {_sql(name, value["directives"][value["kind"]][0]) for name, value in live.items()}
    refusals += [f"{name}: new type over an existing SQL table or view" for name in sorted(set(merged) - set(live))
                 if _sql(name, merged[name]["directives"][merged[name]["kind"]][0]) in existing]
    return refusals + _operations(parse_connector(live_connector), parse_connector(merged_connector))


def read_tree(directory: Path) -> dict[str, str]:
    """The committed *.gql sources of one directory by file name, the paths a release uploads."""
    if not Path(directory).is_dir():
        raise ValueError("source directory missing")
    try:
        return {path.name: path.read_text(encoding="utf-8") for path in sorted(Path(directory).glob("*.gql"))}
    except UnicodeDecodeError:
        raise ValueError("source file is not UTF-8") from None


def live_sources(schema: dict, connector: dict | None) -> tuple[dict[str, str], dict[str, str]]:
    """The source files of Data Connect REST GET responses by path; a missing connector (None) has none.

    The placeholder schema has no files ({} or {"files": []}), so its sources are
    empty: check_additive is not called for it, and the caller initializes instead.
    """
    found = []
    for resource in (schema, {"source": {}} if connector is None else connector):
        source = resource.get("source") if isinstance(resource, dict) else None
        entries = source.get("files", []) if isinstance(source, dict) else None
        if not isinstance(entries, list) or not all(
                isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"].endswith(".gql")
                and isinstance(entry.get("content"), str) for entry in entries):
            raise ValueError("invalid live source")
        files = {entry["path"]: entry["content"] for entry in entries}
        if len(files) != len(entries):
            raise ValueError("duplicate live source file")
        found.append(dict(sorted(files.items())))
    return found[0], found[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare live Data Connect sources with a merged tree, offline.")
    parser.add_argument("--live-schema", type=Path, required=True)
    parser.add_argument("--live-connector", type=Path, required=True)
    parser.add_argument("--merged-schema", type=Path, default=ROOT / "dataconnect/schema")
    parser.add_argument("--merged-connector", type=Path, default=ROOT / "dataconnect/connector")
    args = parser.parse_args(argv)
    try:
        refusals = check_additive(read_tree(args.live_schema), read_tree(args.merged_schema),
                                  read_tree(args.live_connector), read_tree(args.merged_connector))
    except ValueError as exc:
        raise SystemExit(f"schema gate blocked: {exc}") from None
    print("\n".join(refusals) or "additive")
    return 1 if refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
