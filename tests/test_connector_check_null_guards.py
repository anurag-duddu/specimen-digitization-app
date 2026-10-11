"""An optional @check on a key lookup must begin with a null guard.

SQL Connect runs a @check expression even when a key lookup finds no row, so
`optional: true` does not let an absent row pass: the expression is evaluated on
null and denies. `AppendReviewDecisionV2` refused every first review decision
that way ("review decision provenance mismatch"). The guard `this == null ||`
lets the absent row through and keeps the check for a row that exists.

An optional @check on a relation field (`document`, `specimen` under a required
reference) is not a key lookup: the relation always has a row, so it needs none.
"""

from pathlib import Path
import re

CONNECTOR = Path(__file__).parents[1] / "dataconnect/connector"
GUARD = "this == null ||"
STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def groups(source):
    """Every parenthesized group as {close: open}, outside strings and comments."""
    stack, found, i = [], {}, 0
    while i < len(source):
        if source.startswith('"""', i):
            i = source.index('"""', i + 3) + 3
        elif source[i] == '"':
            i += 1
            while source[i] != '"':
                i += 2 if source[i] == "\\" else 1
            i += 1
        elif source[i] == "#":
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
        else:
            if source[i] == "(":
                stack.append(i)
            elif source[i] == ")":
                found[i] = stack.pop()
            i += 1
    assert not stack, "unbalanced parentheses"
    return found


def optional_checks_on_key_lookups(source):
    """(field, expression) of each `@check(optional: true, ...)` that sits on a `field(key: ...)`."""
    closing = groups(source)
    found = []
    for close, open_ in closing.items():
        if source[open_ - len("@check"):open_] != "@check":
            continue
        arguments = source[open_ + 1:close]
        if not re.search(r"\boptional:\s*true\b", STRING.sub('""', arguments)):
            continue
        before = source[:open_ - len("@check")].rstrip()
        if not before.endswith(")"):
            continue  # a relation field, not a lookup
        lookup_close = len(before) - 1
        lookup_open = closing[lookup_close]
        if not re.search(r"\bkey:", STRING.sub('""', source[lookup_open + 1:lookup_close])):
            continue
        field = re.search(r"([A-Za-z_]\w*)\s*$", source[:lookup_open])[1]
        expression = re.search(r'\bexpr:\s*("(?:[^"\\]|\\.)*")', arguments)[1][1:-1]
        found.append((field, expression))
    return found


def unguarded(source):
    return [field for field, expression in optional_checks_on_key_lookups(source) if not expression.lstrip().startswith(GUARD)]


def test_every_optional_check_on_a_key_lookup_starts_with_a_null_guard():
    seen = {}
    for path in sorted(CONNECTOR.glob("*.gql")):
        source = path.read_text()
        seen[path.name] = optional_checks_on_key_lookups(source)
        assert unguarded(source) == [], f"{path.name}: {unguarded(source)} need `{GUARD}` first"
    # The scan must find the lookup that failed, or a parsing slip would pass the test silently.
    assert [field for field, _ in seen["projection.gql"]] == ["reviewDecision"]


def test_the_scan_flags_an_unguarded_optional_check_and_nothing_else():
    check = '@check(optional: true, expr: "EXPR", message: "no (match)")'

    def query(lookup, expression="this.ok"):
        return "query Q { " + lookup.replace("CHECK", check.replace("EXPR", expression)) + " }"

    assert unguarded(query("row(key: {id: $id}) CHECK { ok }")) == ["row"]
    assert unguarded(query("alias: row(key: {id: $id}) CHECK { ok }")) == ["row"]
    assert unguarded(query("row(key: {id: $id}) CHECK { ok }", "this == null || (this.ok)")) == []
    # A lookup by `where` returns a list, and a relation field always has its row.
    assert unguarded(query("rows(where: {id: {eq: $id}}) CHECK { ok }")) == []
    assert unguarded(query("row(key: {id: $id}) { ok other CHECK { ok } }")) == []
    # Only an optional check is in question; a required one fails on null by design.
    assert unguarded('query Q { row(key: {id: $id}) @check(expr: "this.ok") { ok } }') == []
    # Strings and comments never open or close a group.
    assert unguarded('# row(key: {id: $id}) @check(optional: true, expr: "this.ok")\nquery Q { x }') == []
    assert unguarded(query('row(key: {id: $id, name: "a)b"}) CHECK { ok }')) == ["row"]
