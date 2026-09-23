#!/usr/bin/env python3
"""Offline additive-only gate for Data Connect schema and connector changes (RELEASE.md 4.1, PLAN 4.4).

It parses only the SDL and operations this repository uses and fails closed on anything else. Errors name
the construct kind and refusals the table, field or operation and the rule; neither carries a value.
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
                     ("LabelRegion", "cropAssetId"): "the domain's crop is optional",
                     ("EvidenceItem", "locator"): "a lookup that found no single match (no_match, ambiguous, an error) has "
                                                  "nothing to locate, and G26 allows no Google value but a place id"}
# Provenance and idempotency keys, TRN-005's included, that no change ever relaxes.
PROTECTED = frozenset(("ModelObservation", field) for field in ("runId", "regionId", "provider", "modelVersion", "stepKey",
                                                               "rawAssetId", "promptVersion", "inputSha256"))
# PLAN 4.4's one closed @unique exception: (table, old indexName, old fields) -> ((new indexName, new fields), reason).
NAMED_UNIQUE_RELAXATIONS = {("SourceAsset", "specimen_unique_1", ("bucket", "objectName", "generation")): (
    ("source_asset_specimen_object", ("organizationId", "collectionId", "specimenId", "bucket", "objectName", "generation")),
    "the blob store is content-addressed, so byte-identical assets of different specimens are one stored object")}
TYPE_DIRECTIVES, FIELD_DIRECTIVES = {"table", "view", "unique", "index"}, {"default", "ref", "unique", "index", "col"}
KEYWORDS = {"type", "enum", "input", "interface", "union", "scalar", "directive", "extend", "schema", "fragment",
            "subscription", "query", "mutation"}
AUTH, ACTOR = "@auth(level: NO_ACCESS)", "$actorUid: String!"
MEMBERSHIP = "organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check("
# GraphQL lexing: commas and comments are insignificant; a string, block strings too (\""" escaped), is one token.
TOKEN = re.compile(r'(?P<skip>[\s,]+|#[^\n\r]*)|(?P<block>"""(?:\\"""|(?!""")[\s\S])*+""")'
                   r'|(?P<string>"(?:\\.|[^"\\\n\r])*")|(?P<name>[_A-Za-z][_0-9A-Za-z]*)'
                   r'|(?P<number>-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)|(?P<punct>\.\.\.|[!$():=@\[\]{}])'
                   r'|(?P<error>[\s\S])')


def _tokens(text: str) -> list[tuple[str, str]]:
    tokens = [(match.lastgroup, match.group()) for match in TOKEN.finditer(text) if match.lastgroup != "skip"]
    if any(kind == "error" for kind, _ in tokens):
        raise ValueError("unterminated string or unsupported character")
    return tokens


def _find(tokens: list[str], needle: str) -> list[int]:
    """Where a token sequence starts; text inside a string or a comment never matches."""
    wanted = [token for _, token in _tokens(needle)]
    return [at for at in range(len(tokens) - len(wanted) + 1) if tokens[at:at + len(wanted)] == wanted]


def _skip(tokens: list[str], at: int) -> int:
    """The index just past the value at tokens[at]: a $variable, one token or one balanced group."""
    depth = 0
    for end in range(at + (tokens[at:at + 1] == ["$"]), len(tokens)):
        depth += (tokens[end] in ("(", "[", "{")) - (tokens[end] in (")", "]", "}"))
        if depth <= 0:
            return end + 1
    raise ValueError("unexpected end of source")


class _Stream:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens, self.at = tokens, 0

    def peek(self) -> str | None:
        return self.tokens[self.at][1] if self.at < len(self.tokens) else None

    def next(self, *expected: str, kind: str | None = None) -> tuple[str, str]:
        found, token = self.tokens[self.at] if self.at < len(self.tokens) else ("end", None)
        if found == "end" or (expected and token not in expected) or (kind and found != kind):
            raise ValueError("expected a name" if kind else f"expected {' or '.join(expected)}" if expected
                             else "unexpected end of source")
        self.at += 1
        return found, token

    def name(self) -> str:
        return self.next(kind="name")[1]

    def group(self) -> list[tuple[str, str]]:
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
        start, (kind, keyword) = stream.at, stream.next()
        if kind != "name" or keyword not in keywords:
            raise ValueError(f"unsupported {what} construct: {keyword if kind == 'name' and keyword in KEYWORDS else kind}")
        name = stream.name()
        while stream.peek() != "{":
            if stream.peek() == "(":
                stream.group()
            elif stream.next("@"):
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
                if stream.next(":") and argument in arguments:
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
    if not all(isinstance(item, str) and re.fullmatch(r'"[_A-Za-z][_0-9A-Za-z]*"', item) for item in values):
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
                field, _ = stream.name(), stream.next(":")
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


def _users(name: str, table: dict, index: str, fields: set[str], operations: dict) -> list[str]:
    """Operations using a unique: a key access naming its fields, an upsert, an onConflict naming it; unclear is a use."""
    rows = {name[:1].lower() + name[1:], *_names(table["directives"]["table"][0], "singular")}
    keyed = {row + suffix for row in rows for suffix in ("", "_update", "_delete")}
    users = set()
    for operation, value in operations.items():
        tokens = [token for _, token in _tokens(value["body"])]
        for at, token in enumerate(tokens):
            if token in keyed and tokens[at + 1:at + 2] == ["("]:
                group = tokens[at + 1:_skip(tokens, at + 1)]
                plain = all(group[start + 1:start + 3] == [":", "{"] for start, item in enumerate(group) if item == "key")
                if "key" in group and (not plain or fields <= {item.removesuffix("_expr") for item in group}):
                    users.add(operation)
            elif token == "onConflict":
                target = tokens[at + 2:_skip(tokens, at + 2)] if tokens[at + 1:at + 2] == [":"] else ["$"]
                named = {item.strip('"') for item in target}
                if named & {"$", index} or fields <= named:
                    users.add(operation)
            elif token in {row + suffix for row in rows for suffix in ("_upsert", "_upsertMany")}:
                users.add(operation)
    return sorted(users)


def _swaps(name: str, old: dict, new: dict, operations: dict) -> tuple[set[str], list[str]]:
    """PLAN 4.4's closed @unique exception, create before drop: one merge adds the new unique beside the old one, a later
    one drops the old one once the new one is live. The text a valid step exempts, and why the others are refused."""
    exempt, refusals = set(), []
    for (table, before, listed), ((after, wider), _) in NAMED_UNIQUE_RELAXATIONS.items():
        if table != name:
            continue
        was, kept, had, now = ([text for text in value["directives"].get("unique", ()) if _names(text, "indexName") == (index,)]
                               for value, index in ((old, before), (new, before), (old, after), (new, after)))
        old_listed, new_live, new_merged = (len(texts) == 1 and set(_names(texts[0], "fields")) == set(fields)
                                            for texts, fields in ((was, listed), (had, wider), (now, wider)))
        adds = old_listed and kept == was and not had and new_merged  # step one: the old unique stays declared
        drops = old_listed and not kept and new_live and now == had  # step two: the new unique is live and stays
        where, key = f"{name}: @unique {before}", set(_names(old["directives"]["table"][0], "key", ("id",)))
        if old_listed and not kept and not had and now:
            refusals.append(f"{where} dropped in the change that adds {after}; create before drop takes two merges")
        if not adds and not drops:
            continue
        reasons = [f"{where} is the primary key"] if set(listed) == key else []
        # PostgreSQL treats NULLs as distinct, so a nullable added column would switch the new unique off.
        reasons += [f"{name}: @unique {after} adds nullable or missing column {column}" for column in sorted({*wider} - {*listed})
                    if not all(value["fields"].get(column, {}).get("non_null") for value in (old, new))]
        reasons += [f"{where} to {after} covers protected key {column}" for column in sorted({*listed, *wider})
                    if (name, column) in PROTECTED]
        reasons += [f"{where} is used by existing operation {user}" for user in _users(name, old, before, set(listed), operations)
                    if drops]
        refusals += reasons
        exempt |= set() if reasons else {now[0] if adds else was[0]}
    return exempt, refusals


def _table(name: str, old: dict, new: dict, types: dict, operations: dict) -> list[str]:
    exempt, refusals = _swaps(name, old, new, operations)
    refusals += [f"{name}: @table key or name changed"] if new["directives"]["table"] != old["directives"]["table"] else []
    for kind in ("unique", "index"):
        before, after = Counter(old["directives"].get(kind, ())), Counter(new["directives"].get(kind, ()))
        if set(before - after) - exempt:
            refusals.append(f"{name}: type-level @{kind} removed or changed")
        if any(field in old["fields"] for text in set(after - before) - exempt for field in _names(text, "fields")):
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
            ref = now["directives"].get("ref")
            follows = ref is not None and any((name, column) in NAMED_RELAXATIONS and column in new["fields"]
                                              and not new["fields"][column]["non_null"] for column in _names(ref, "fields"))
            if (name, field) in PROTECTED or field in guarded:
                refusals.append(f"{where}: NOT NULL dropped on a key, unique or provenance field")
            elif (name, field) not in NAMED_RELAXATIONS and not follows:
                refusals.append(f"{where}: NOT NULL dropped outside the named relaxations")
    columns = {_sql(field, value["directives"].get("col")) for field, value in old["fields"].items()}
    for field, now in sorted((field, value) for field, value in new["fields"].items() if field not in old["fields"]):
        where, foreign = f"{name}.{field}", _names(now["directives"]["ref"], "fields") if "ref" in now["directives"] else ()
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
    for name in sorted(set(merged) - set(live)):
        header, body = ([token for _, token in _tokens(merged[name][part])] for part in ("header", "body"))
        if len(_find(header, "@auth")) != 1 or not _find(header, AUTH):
            refusals.append(f"{name}: new operation not at {AUTH}")
        # A default would let a caller omit the actor that the membership check binds.
        if len(_find(header, ACTOR)) == len(_find(header, ACTOR + " =")):
            refusals.append(f"{name}: new operation does not declare {ACTOR}")
        if not _find(body, MEMBERSHIP):
            refusals.append(f"{name}: new operation without the organizationMember @check")
        # A skipped or excluded field runs no @check.
        if any(_find(tokens, directive) for tokens in (header, body) for directive in ("@skip", "@include")):
            refusals.append(f"{name}: new operation uses @skip or @include")
    return refusals


def check_additive(live_schema: dict[str, str], merged_schema: dict[str, str],
                   live_connector: dict[str, str], merged_connector: dict[str, str]) -> list[str]:
    """Refusals for the merged sources against the live ones (RELEASE.md 4.1); an empty list means additive. An empty
    live schema is the placeholder, which the caller initializes instead; this raises for it, as for unparseable sources."""
    live, merged, operations = parse_schema(live_schema), parse_schema(merged_schema), parse_connector(live_connector)
    if not live:
        raise ValueError("the live schema is the empty placeholder; the release initializes instead")
    refusals = []
    for name, old in sorted(live.items()):
        new = merged.get(name)
        if old["kind"] == "table" and new and new["kind"] == "table":
            refusals += _table(name, old, new, merged, operations)
        elif new != old:  # a view must stay exactly as it is; a table cannot become a view
            refusals.append(f"{name}: {old['kind']} {'changed' if new and old['kind'] == 'view' else 'removed or renamed'}")
    existing = {_sql(name, value["directives"][value["kind"]][0]) for name, value in live.items()}
    refusals += [f"{name}: new type over an existing SQL table or view" for name in sorted(set(merged) - set(live))
                 if _sql(name, merged[name]["directives"][merged[name]["kind"]][0]) in existing]
    return refusals + _operations(operations, parse_connector(merged_connector))


def read_tree(directory: Path) -> dict[str, str]:
    """The committed *.gql sources of one directory by file name, the paths a release uploads."""
    if not Path(directory).is_dir():
        raise ValueError("source directory missing")
    try:
        return {path.name: path.read_text(encoding="utf-8") for path in sorted(Path(directory).glob("*.gql"))}
    except UnicodeDecodeError:
        raise ValueError("source file is not UTF-8") from None


def live_sources(schema: dict, connector: dict | None) -> tuple[dict[str, str], dict[str, str]]:
    """The source files of Data Connect REST GET responses by path; a missing connector (None) has none. The
    placeholder schema has no files ({} or {"files": []}): check_additive is not called for it; the caller initializes."""
    found = []
    for resource in (schema, {"source": {}} if connector is None else connector):
        source = resource.get("source") if isinstance(resource, dict) else None
        entries = source.get("files", []) if isinstance(source, dict) else None
        if not isinstance(entries, list) or not all(isinstance(entry, dict) and isinstance(entry.get("path"), str) and isinstance(
                entry.get("content"), str) and entry["path"].endswith(".gql") for entry in entries) or len(
                {entry["path"] for entry in entries}) != len(entries):
            raise ValueError("invalid or duplicate live source file")
        found.append(dict(sorted((entry["path"], entry["content"]) for entry in entries)))
    return found[0], found[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare live Data Connect sources with a merged tree, offline.")
    for side, part in (("live", "schema"), ("live", "connector"), ("merged", "schema"), ("merged", "connector")):
        parser.add_argument(f"--{side}-{part}", type=Path, required=side == "live", default=ROOT / "dataconnect" / part)
    args = parser.parse_args(argv)
    try:
        refusals = check_additive(*(read_tree(getattr(args, f"{side}_{part}")) for part in ("schema", "connector")
                                    for side in ("live", "merged")))
    except ValueError as exc:
        raise SystemExit(f"schema gate blocked: {exc}") from None
    print("\n".join(refusals) or "additive")
    return 1 if refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
