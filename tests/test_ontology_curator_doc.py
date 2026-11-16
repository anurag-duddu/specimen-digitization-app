"""The curator's page on the specimen ontology (docs/execution/units/PLAN.md, WP 2.7) against the file it documents.

docs/product-requirements/SPECIMEN_ONTOLOGY_FOR_CURATORS.md copies the ontology's lists into tables and cites
the lines it describes. These tests fail when a table and src/specimen_digitization/ontology/specimen.yaml
disagree, or when a cited line, file or test stops holding what the page says it holds, so a change to the
file is followed by the page in the same pull request. Each failure names the row or citation to write.
"""

from pathlib import Path
import re
import sys

import pytest

from specimen_digitization import ontology

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/product-requirements/SPECIMEN_ONTOLOGY_FOR_CURATORS.md"
# The page's short names for the files it cites most.
SHORT = {"specimen.yaml": ontology.PATH, "ontology/__init__.py": ontology.PATH.with_name("__init__.py")}
# A citation: `path:line` or `path:first-last`, optionally followed by (`text the first line holds`).
CITED = re.compile(r"`([\w./-]+\.\w+):(\d+)(?:-(\d+))?`(?: \(`([^`]+)`\))?")
TEST = re.compile(r"`(tests/[\w/]+\.py)::(\w+)`")


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def section(heading: str) -> str:
    """The page's text under a heading (## or ###), up to the next heading of any level."""
    lines = page().splitlines()
    start = next(index for index, line in enumerate(lines) if re.fullmatch(rf"#{{2,3}} {re.escape(heading)}", line))
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("#")), len(lines))
    return "\n".join(lines[start + 1:end])


def rows(heading: str) -> list[list[str]]:
    """The cells of each body row of the tables under a heading."""
    found = []
    for line in section(heading).splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            found.append([cell.strip() for cell in line.strip().strip("|").split(" | ")])
    return found[1:] if found else found  # the first row is the header


def labels(keys) -> list[str]:
    names = {entry.key: entry.label for entry in ontology.ontology().fields}
    return [names[key] for key in keys]


def fields_cell(keys, empty: str) -> str:
    return ", ".join(labels(keys)) or empty


def forms(written) -> str:
    return ", ".join(f"`{form}`" for form in written)


def yaml_line(prefix: str) -> int:
    """The line of specimen.yaml that holds an entry's `- id: ...` or `- key: ...`."""
    lines = ontology.PATH.read_text(encoding="utf-8").splitlines()
    return next(index + 1 for index, line in enumerate(lines) if line.strip() == f"- {prefix}")


def test_the_things_table_is_the_files():
    expected = [[thing.name, thing.examples, thing.darwin_core] for thing in ontology.ontology().things]

    assert rows("The things on a label") == expected


def test_the_field_table_is_the_files_20_fields_with_their_darwin_core_terms():
    loaded = ontology.ontology()
    expected = [[f"`{entry.key}`", entry.label, f"`{entry.darwin_core}`"] for entry in loaded.fields]

    assert [row[:3] for row in rows("The 20 fields")] == expected


def test_the_field_table_names_every_rule_that_derives_a_field():
    """The last column names each `derives` rule whose fields hold the row's field, and no other `derives` rule."""
    loaded = ontology.ontology()
    deriving = {rule.id for rule in loaded.rules if rule.derives}
    for row in rows("The 20 fields"):
        key = row[0].strip("`")
        named = set(re.findall(r"`(\w+)`", row[-1])) & deriving
        expected = {rule.id for rule in loaded.rules if rule.derives and key in rule.fields}
        assert named == expected, (key, sorted(expected))


def test_the_notation_table_is_the_files_notations_with_their_forms_and_fields():
    expected = [[f"`{notation.id}`", forms(notation.written), fields_cell(notation.fields, "No field")]
                for notation in ontology.ontology().notations]

    assert [row[:3] for row in rows("The notations")] == expected


def test_each_notations_sources_are_as_the_file_records_them():
    expected = [[f"`{notation.id}`", f"`specimen.yaml:{yaml_line('id: ' + notation.id)}` (`id: {notation.id}`)",
                 "; ".join(f"`{source}`" for source in notation.source)]
                for notation in ontology.ontology().notations]

    assert rows("Where each notation comes from") == expected


def test_the_routing_table_is_the_files():
    expected = [[f"`{route.id}`", fields_cell(route.fields, "No field")] for route in ontology.ontology().routing]

    assert [[row[0], row[2]] for row in rows("The routing entries")] == expected


def test_the_questions_table_is_the_files():
    expected = [[f"`{question.id}`", forms(question.written), question.question]
                for question in ontology.ontology().questions]

    assert [row[:3] for row in rows("Open questions")] == expected


def test_the_rules_table_is_the_files_rules_with_how_each_is_checked_and_its_fields():
    loaded = ontology.ontology()
    expected = [[f"`{rule.id}`", rule.check, fields_cell(rule.fields, "None")] for rule in loaded.rules]

    assert [row[:3] for row in rows("The rules")] == expected
    for entry in loaded.not_rules:
        assert f"(`id: {entry.id}`)" in section("The rules"), entry.id


def test_each_example_units_fields_are_the_ones_the_file_gives_it():
    examples = rows("Examples from the pilot labels")
    assert examples
    for unit, judged, fields, _ in examples:
        kind = re.findall(r"`(\w+)`", judged)
        advice = ontology.ontology().advice(unit.strip("`"), kind[0] if kind else None)
        assert fields == fields_cell(advice.fields, "No field"), unit


def test_every_cited_line_exists_and_holds_the_text_after_it():
    """A cited file exists and has the cited lines; a cited line of specimen.yaml, whose numbers move when the
    file changes, always names the text it holds, and that text is on the first cited line."""
    citations = CITED.findall(page())
    assert len(citations) > 50
    problems = []
    for path, first, last, text in citations:
        file = SHORT.get(path) or next(
            (candidate for candidate in (ROOT / path, DOC.parent / path) if candidate.is_file()), None)
        if file is None:
            problems.append(f"{path}: no such file")
            continue
        lines = file.read_text(encoding="utf-8").splitlines()
        first, last = int(first), int(last or first)
        if not 1 <= first <= last <= len(lines):
            problems.append(f"{path}:{first}-{last}: past the file's {len(lines)} lines")
        elif text and text not in lines[first - 1]:
            problems.append(f"{path}:{first}: does not hold {text!r}")
        elif not text and file == ontology.PATH:
            problems.append(f"{path}:{first}: names no text")
    assert problems == []


def test_every_cited_test_exists():
    cited = TEST.findall(page())
    assert len(cited) > 10
    missing = [f"{path}::{name}" for path, name in cited
               if not re.search(rf"^def {name}\(", (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)]
    assert missing == []


@pytest.mark.parametrize("change", ["field", "notation"])
def test_a_page_that_disagrees_with_the_file_fails(change, monkeypatch):
    """The check's failure, shown on a copy of the page: a Darwin Core term or a notation's form changed."""
    text = page()
    if change == "field":
        altered = text.replace("| `collection_code` | Collection Code | `collectionCode` |",
                               "| `collection_code` | Collection Code | `institutionCode` |")
        check = test_the_field_table_is_the_files_20_fields_with_their_darwin_core_terms
    else:
        altered = text.replace("| `lewis_collection_heading` | `LEWIS COLLECTION` |",
                               "| `lewis_collection_heading` | `LEWIS COLLECTIONS` |")
        check = test_the_notation_table_is_the_files_notations_with_their_forms_and_fields
    assert altered != text
    monkeypatch.setattr(sys.modules[__name__], "page", lambda: altered)

    with pytest.raises(AssertionError):
        check()
