#!/usr/bin/env python3
"""Check Dart string literals against the UX writing guidelines.

Source of truth: apps/specimen_digitization/design/02-ux-writing-guidelines.md
section 6 ("Rules for agents") items 1 and 6, and section 7 ("Length budgets").
Also enforces apps/specimen_digitization/design/01-usability-heuristics-audit.md
"Pass criteria", heuristic 4, item 4.

What it checks, for every string literal in every `.dart` file under the scanned
root (comments, `import`/`export`/`part` URIs and interpolated expressions are
not scanned):

  dash         Rule 1. An em-dash or an en-dash. Use a period, a comma, a colon
               or a hyphen. Fails the build.
  banned-word  Rule 6. One of the banned filler words, or a bare UI label that
               says nothing ("OK", "Yes", "No", "Confirm", "Submit"). Fails the
               build.
  long-text    Section 7. A `Text('...')` literal over 20 words. Reported as a
               warning only. Nothing in section 7 budgets a body string by word
               count, so this list is advice for a human, not a gate.

Exit status is non-zero only for `dash` and `banned-word` findings that are not
in the baseline. Warnings never change the exit status.

Usage:

    python3 scripts/ci/check_ui_strings.py \
        --baseline scripts/ci/ui_strings_baseline.txt

The baseline
------------

The client already ships strings that break rules 1 and 6, and this check is
meant to stop new ones rather than block every commit until the old ones are
rewritten. The baseline file lists the violations that exist today, one per
line, as `path:line:rule` relative to the repository root. A violation listed
there is reported as "baselined" and does not fail the build. Anything else
does.

The baseline is a ratchet: it may shrink, never grow.

To shrink it, rewrite the string in `lib/` so it passes the rule, then delete
that line from the baseline. Running the check afterwards reports the entry as
stale, which is the reminder to delete it; pass `--strict-baseline` to turn a
stale entry into a failure, which is how a CI job proves the ratchet only ever
moved down.

Line numbers move when unrelated code above a string changes. Regenerate the
file with

    python3 scripts/ci/check_ui_strings.py \
        --baseline scripts/ci/ui_strings_baseline.txt --write-baseline

and check that `git diff` on the baseline shows only line-number churn, never a
new `path:line:rule` triple. A new triple in that diff is a new violation being
laundered through the baseline, and is the one thing this file must not be used
for.

Python 3.12, standard library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Written as escapes on purpose: this file is itself covered by rule 1, and a
# literal dash here would be a false positive for anyone grepping the tree.
EM_DASH = "\u2014"
EN_DASH = "\u2013"
DASHES = (EM_DASH, EN_DASH)

# Section 6, item 6. Matched as whole words, case-insensitively.
BANNED_WORDS = (
    "invalid",
    "illegal",
    "failed to",
    "an error occurred",
    "something went wrong",
    "oops",
    "please wait",
    "simply",
    "just",
    "easily",
    "unfortunately",
    "sorry",
    "we",
    "our",
    "delightful",
    "seamless",
)

# Section 6, item 6, second sentence. Banned only as the whole string.
BANNED_BARE_LABELS = ("ok", "yes", "no", "confirm", "submit")

# Section 7. A warning threshold for inline body copy, not a budget row.
MAX_TEXT_WORDS = 20

# Interpolated expressions are code, not copy. They are replaced by this
# placeholder so that identifiers inside `${...}` never trip a word rule, while
# still counting as one word towards the length warning.
PLACEHOLDER = "￼"

WORD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")

DIRECTIVES = ("import ", "export ", "part ", "part'", 'part"')


class Literal:
    """One Dart string literal, with its interpolations blanked out."""

    def __init__(self, path: Path, line: int, text: str, owner: str | None):
        self.path = path
        self.line = line
        self.text = text
        self.owner = owner


def _is_word_char(char: str) -> bool:
    return char.lower() in WORD_CHARS


def _owner_of(source: str, start: int) -> str | None:
    """Return the widget or function name a literal is the first argument of."""
    index = start - 1
    while index >= 0 and source[index] in " \t\r\n":
        index -= 1
    if index < 0 or source[index] != "(":
        return None
    index -= 1
    while index >= 0 and source[index] in " \t\r\n":
        index -= 1
    name_end = index + 1
    while index >= 0 and (_is_word_char(source[index]) or source[index] == "$"):
        index -= 1
    name = source[index + 1 : name_end]
    return name or None


def scan_literals(path: Path, source: str) -> list[Literal]:
    """Extract every string literal from Dart source.

    Handles line and nesting block comments, raw strings, single and triple
    quotes, escapes, and nested `${...}` interpolation (including a string
    inside an interpolation, which is scanned as its own literal).
    """
    literals: list[Literal] = []
    index = 0
    line = 1
    length = len(source)
    # Each open interpolation pushes the state of the string it interrupts.
    stack: list[tuple[str, bool, bool, int, int, list[str], int]] = []
    quote = ""
    raw = False
    triple = False
    start_line = 0
    start_index = 0
    parts: list[str] = []
    brace_depth = 0

    def close_literal() -> None:
        text = "".join(parts)
        owner = _owner_of(source, start_index)
        prefix = source[:start_index].rsplit("\n", 1)[-1].lstrip()
        if not any(prefix.startswith(directive) for directive in DIRECTIVES):
            literals.append(Literal(path, start_line, text, owner))

    while index < length:
        char = source[index]
        if not quote:
            if char == "\n":
                line += 1
                index += 1
                continue
            if source.startswith("//", index):
                end = source.find("\n", index)
                index = length if end < 0 else end
                continue
            if source.startswith("/*", index):
                depth = 1
                index += 2
                while index < length and depth:
                    if source.startswith("/*", index):
                        depth += 1
                        index += 2
                    elif source.startswith("*/", index):
                        depth -= 1
                        index += 2
                    else:
                        if source[index] == "\n":
                            line += 1
                        index += 1
                continue
            if stack and char == "}" and brace_depth == 0:
                # End of a `${...}` interpolation: resume the outer string.
                (
                    quote,
                    raw,
                    triple,
                    start_line,
                    start_index,
                    parts,
                    brace_depth,
                ) = stack.pop()
                parts.append(PLACEHOLDER)
                index += 1
                continue
            if stack and char == "{":
                brace_depth += 1
                index += 1
                continue
            if stack and char == "}":
                brace_depth -= 1
                index += 1
                continue
            is_raw = False
            if char in "rR" and index + 1 < length and source[index + 1] in "'\"":
                is_raw = True
                index += 1
                char = source[index]
            if char in "'\"":
                quote = char
                raw = is_raw
                triple = source.startswith(char * 3, index)
                start_line = line
                start_index = index - (1 if is_raw else 0)
                index += 3 if triple else 1
                parts = []
                continue
            index += 1
            continue

        # Inside a string literal.
        if char == "\n":
            line += 1
            if not triple:
                # Unterminated single-quoted string; recover at the line end.
                close_literal()
                quote = ""
                index += 1
                continue
            parts.append(char)
            index += 1
            continue
        if not raw and char == "\\":
            parts.append(source[index + 1 : index + 2])
            index += 2
            continue
        if triple and source.startswith(quote * 3, index):
            close_literal()
            quote = ""
            index += 3
            continue
        if not triple and char == quote:
            close_literal()
            quote = ""
            index += 1
            continue
        if not raw and char == "$":
            following = source[index + 1 : index + 2]
            if following == "{":
                stack.append(
                    (quote, raw, triple, start_line, start_index, parts, brace_depth)
                )
                quote = ""
                brace_depth = 0
                index += 2
                continue
            if following and _is_word_char(following):
                index += 1
                while index < length and (
                    _is_word_char(source[index]) or source[index] == "."
                ):
                    index += 1
                parts.append(PLACEHOLDER)
                continue
        parts.append(char)
        index += 1

    if quote:
        close_literal()
    return literals


def _words(text: str) -> list[str]:
    return [word for word in text.split() if any(c.isalnum() for c in word)]


def _contains_word(haystack: str, needle: str) -> bool:
    """Whole-word, case-insensitive containment for one or more words."""
    lower = haystack.lower()
    start = 0
    while True:
        found = lower.find(needle, start)
        if found < 0:
            return False
        before = lower[found - 1] if found else ""
        after_index = found + len(needle)
        after = lower[after_index] if after_index < len(lower) else ""
        if not _is_word_char(before) and not _is_word_char(after):
            return True
        start = found + 1


class Finding:
    def __init__(self, literal: Literal, rule: str, detail: str):
        self.literal = literal
        self.rule = rule
        self.detail = detail

    @property
    def key(self) -> str:
        return f"{self.literal.path.as_posix()}:{self.literal.line}:{self.rule}"

    def describe(self) -> str:
        excerpt = " ".join(self.literal.text.split())
        if len(excerpt) > 72:
            excerpt = excerpt[:69] + "..."
        return f"  {self.key}\n      {self.detail}\n      {excerpt}"


def is_identifier_like(text: str) -> bool:
    """True for a machine identifier that is never shown to a reader.

    Server enums, Firebase error codes and preference keys are matched against,
    not displayed; section 6 rule 17 requires them to pass through `labelOf`
    before they reach a screen. A single lowercase token joined by `-`, `_` or
    `.` is one of those, so it is out of scope for the copy rules. Real one-word
    labels ("Yes", "Cancel") carry a capital and no separator, so they stay in.
    """
    token = text.strip()
    if not token or any(char.isspace() for char in token):
        return False
    if token != token.lower() or not any(sep in token for sep in "-_."):
        return False
    return all(_is_word_char(char) or char in "-." for char in token)


def check(literal: Literal) -> list[Finding]:
    findings: list[Finding] = []
    if is_identifier_like(literal.text):
        return findings
    for dash in DASHES:
        if dash in literal.text:
            name = "em-dash" if dash == EM_DASH else "en-dash"
            findings.append(
                Finding(
                    literal,
                    "dash",
                    f"rule 1, contains an {name}; "
                    "use a period, a comma, a colon or a hyphen",
                )
            )
    stripped = literal.text.strip()
    if stripped.lower() in BANNED_BARE_LABELS:
        findings.append(
            Finding(
                literal,
                "banned-word",
                f'rule 6, "{stripped}" says nothing on its own; name the action',
            )
        )
    else:
        for word in BANNED_WORDS:
            if _contains_word(literal.text, word):
                findings.append(
                    Finding(literal, "banned-word", f'rule 6, banned word "{word}"')
                )
    return findings


def warn(literal: Literal) -> Finding | None:
    if not literal.owner or not literal.owner.endswith("Text"):
        return None
    count = len(_words(literal.text))
    if count <= MAX_TEXT_WORDS:
        return None
    return Finding(
        literal,
        "long-text",
        f"section 7, {literal.owner} literal is {count} words, "
        f"over {MAX_TEXT_WORDS}",
    )


def read_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def write_baseline(path: Path, keys: list[str]) -> None:
    header = [
        "# Baselined UI string violations for scripts/ci/check_ui_strings.py.",
        "#",
        "# Format: path:line:rule, relative to the repository root.",
        "# This list is a ratchet. It may shrink, never grow. Read the module",
        "# docstring of scripts/ci/check_ui_strings.py before editing it.",
        "#",
        "# Regenerate line numbers with --write-baseline and confirm that the",
        "# diff shows only line-number churn, never a new path:line:rule triple.",
        "",
    ]
    path.write_text("\n".join(header + sorted(keys)) + "\n", encoding="utf-8")


def default_roots(repo_root: Path) -> tuple[Path, ...]:
    """The directories scanned when no ``--root`` is given.

    The client, and the ``specimen_ui`` design system package. The package
    carries user-facing strings of its own now: a disabled control's reason, a
    dismiss label, a sheet's title. 10 section 8 puts it inside this gate.
    """
    app = repo_root / "apps" / "specimen_digitization"
    return (app / "lib", app / "packages" / "specimen_ui" / "lib")


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Check Dart UI strings against the UX writing guidelines."
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        dest="roots",
        default=None,
        help=(
            "Directory of .dart files to scan. Repeatable. Defaults to the "
            "client and the design system package."
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="File of accepted existing violations, one path:line:rule per line.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite the baseline from the violations found now, then exit 0.",
    )
    parser.add_argument(
        "--strict-baseline",
        action="store_true",
        help="Fail when a baseline entry no longer matches a violation.",
    )
    parser.add_argument(
        "--quiet-warnings",
        action="store_true",
        help="Suppress the over-length Text warning list.",
    )
    args = parser.parse_args(argv)

    roots: list[Path] = args.roots if args.roots else list(default_roots(repo_root))
    for root in roots:
        if not root.is_dir():
            print(f"check_ui_strings: {root} is not a directory", file=sys.stderr)
            return 2

    failures: list[Finding] = []
    baselined: list[Finding] = []
    warnings: list[Finding] = []
    # Sorted per root and then overall, so a finding's position in the output
    # does not depend on which root it came from.
    files = sorted({file for root in roots for file in root.rglob("*.dart")})
    baseline = read_baseline(args.baseline) if args.baseline else set()

    for file in files:
        try:
            relative = file.resolve().relative_to(repo_root)
        except ValueError:
            relative = file
        for literal in scan_literals(relative, file.read_text(encoding="utf-8")):
            for finding in check(literal):
                if finding.key in baseline:
                    baselined.append(finding)
                else:
                    failures.append(finding)
            warning = warn(literal)
            if warning is not None:
                warnings.append(warning)

    if args.write_baseline:
        if not args.baseline:
            print(
                "check_ui_strings: --write-baseline needs --baseline", file=sys.stderr
            )
            return 2
        keys = sorted({finding.key for finding in failures + baselined})
        write_baseline(args.baseline, keys)
        print(f"check_ui_strings: wrote {len(keys)} entries to {args.baseline}")
        return 0

    if warnings and not args.quiet_warnings:
        print(
            f"Warning: {len(warnings)} Text literal(s) over {MAX_TEXT_WORDS} "
            "words. Section 7 length budgets, not a gate."
        )
        for finding in warnings:
            print(finding.describe())
        print()

    stale = sorted(baseline - {finding.key for finding in baselined})
    if stale:
        prefix = "FAIL: stale" if args.strict_baseline else "Stale"
        print(
            f"{prefix} baseline entries: {len(stale)}. "
            "These no longer match a violation; delete them from the baseline."
        )
        for key in stale:
            print(f"  {key}")
        print()

    if failures:
        print(f"FAIL: {len(failures)} UI string violation(s) outside the baseline.")
        for finding in failures:
            print(finding.describe())
        print()

    print(
        f"check_ui_strings: {len(files)} file(s) scanned, "
        f"{len(failures)} violation(s), {len(baselined)} baselined, "
        f"{len(warnings)} warning(s)."
    )
    if failures:
        return 1
    if stale and args.strict_baseline:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
