"""The curator's page on the specimen ontology (docs/execution/units/PLAN.md, WP 2.7) against the file it documents.

docs/product-requirements/SPECIMEN_ONTOLOGY_FOR_CURATORS.md copies the ontology's lists and words into tables and
cites the lines it describes. These tests fail when a table and src/specimen_digitization/ontology/specimen.yaml
disagree, when the text of a cited range of the file changes, or when a cited line, file or test stops holding what
the page says it holds, so a change to the file is followed by the page in the same pull request. Each failure names
the row, or the page lines to re-read.
"""

from collections import defaultdict
import hashlib
from pathlib import Path
import re
import sys

import pytest

from specimen_digitization import ontology

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/product-requirements/SPECIMEN_ONTOLOGY_FOR_CURATORS.md"
# A citation: `path:line` or `path:first-last`, optionally followed by (`text the first line holds`).
CITED = re.compile(r"`([\w./-]+\.\w+):(\d+)(?:-(\d+))?`(?:\s+\(`([^`]+)`\))?")
TEST = re.compile(r"`(tests/[\w/]+\.py)::(\w+)`")

# The text of each range of specimen.yaml the page cites, keyed by the text its first line holds and its length in
# lines: the first 6 hex digits of the SHA-256 of those lines. A change inside a cited range fails
# test_the_text_of_every_cited_range_is_the_text_the_page_was_written_against until the page lines citing it are
# re-read and the fingerprint is renewed; a range that only moved keeps its fingerprint. A single line that is
# its own cited text, such as "- id: cnhm", is pinned by that text alone.
CITED_TEXT = {
    'A source "<path>:<lines>" is a file of this repository +8': 'c72613',
    'the organiser, which proposes every field +1': 'f07299',
    'Version 1.0 held no meaning the engineer invented +8': '872e39',
    'Version 2.0 (plan WP 2.1, 2026-11-14) +1': '266fa6',
    'Version 2.0 also resolves the meanings +2': '8fcb50',
    'Version 2.0 also resolves the meanings +5': 'b18bfc',
    'Each resolved meaning is a notation or a rule +4': 'aa0d94',
    "forms are matched in a unit's text +13": '4ec887',
    'A word in angle brackets stands for what the label writes there +5': '1e2fdb',
    'A match inside a longer match is dropped +3': 'db233d',
    'frame: +5': 'f7aad8',
    'things: +41': 'b209d1',
    'id: locality +3': '424690',
    'id: agent +4': '55b4db',
    'id: determination +4': 'c8b86d',
    'id: code +4': '5b1642',
    'id: label +3': '294e05',
    "The profile's 20 fields +4": 'ed7883',
    'key: elevation_from_ft +8': 'd85131',
    'key: collection_code +4': '8c95e4',
    "Darwin Core's locality is its interpretation and may equal it. +1": '87c56e',
    "The brief's first line states this +5": '1d607d',
    'The EMu Parties record number (IRN) +1': '9cf43b',
    "The museum's Darwin Core mapping resolves +3": '427dad',
    'The fields a kind of unit could belong to +3': 'f35854',
    'notation_rule: +11': 'f09710',
    'The label notations and every reading each allows +1': 'b7d1f7',
    'The label notations and every reading each allows +4': '2c7fad',
    'id: lewis_collection_heading +6': '0ae0de',
    'Meanings version 1.0 left open +7': 'bff360',
    'id: cnhm +6': 'a6e35a',
    'id: species_number +4': '76c7c0',
    'a morphocode, a species number +1': '0faabe',
    'id: female_sign +4': '599120',
    'id: p_code +12': '8b6b9e',
    'The rules (version 2.0) +6': '754a13',
    "WP 2.2 puts the rules into the models' instructions +7": '3d5a03',
    'id: one_collecting_event +7': 'ac9387',
    'id: place_within_settled_places +16': '7520b6',
    'settled on a source record that names +2': 'b006ee',
    'ISO 3166-1 codes +1': 'df202b',
    "settled on Wikidata's nation (GE) +2": 'a266f6',
    'id: place_chain +15': '9fea42',
    'id: place_chain +3': 'f961ca',
    'id: date_order +3': '256ba9',
    'id: date_order +8': 'cd84da',
    'id: day_month_order +4': '2aea98',
    'id: code_is_no_date +11': 'd0f1fb',
    'id: code_is_no_date +4': '15bcb8',
    'id: label_type_routing +7': 'dee2c3',
    'id: elevation_unit_feet +15': 'edaa89',
    'Basis: inferred, rule elevation_unit_feet +1': '2d95cd',
    'decision D5 +1': '7f2f77',
    "Keep an elevation's foot mark +2": '4157fe',
    'id: elevation_needs_a_unit +5': '90f872',
    'id: elevation_unit_decides_field +4': 'b83ea9',
    'id: place_parents_derived +15': 'f742c9',
    'Leave a larger place the label does not write empty +2': 'd805a3',
    'id: elevation_conversion +13': '98720b',
    'Never convert an elevation to the other unit +2': 'a638f2',
    'id: end_date_from_one_date +10': '40a5a7',
    'id: end_date_from_one_date +4': 'fd7d00',
    'Give Date Visited To only from an end date the label writes +2': 'ad4968',
    'confirmed by the reference truth +2': 'a8a095',
    'id: precise_location_extent +13': '0a88c3',
    "The rule's meaning +6": '277907',
    'id: taxon_in_collection_scope +15': '3315e6',
    'id: taxon_in_collection_scope +5': '26c7f0',
    'id: host_is_no_taxon +14': '7eb436',
    'id: host_is_no_taxon +8': 'd31868',
    'id: parts_on_different_labels +22': 'eef9c3',
    'id: taxon_regional_occurrence +5': '989c2a',
    'decision D4 +1': 'ded1d6',
    "Each country's highest point and its elevation, from Wikidata +10": 'd24fa3',
    "Each country's highest point and its elevation, from Wikidata +6": '5711b1',
    'point_name: "Mount Apo" +1': '024b57',
    "The code's own notation tables +80": '867e6f',
}


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def resolve(path: str) -> Path | None:
    """The file a citation names: the page's short names, else a path from the root or beside the page."""
    short = {"specimen.yaml": ontology.PATH, "ontology/__init__.py": Path(ontology.__file__)}
    return short.get(path) or next((file for file in (ROOT / path, DOC.parent / path) if file.is_file()), None)


def section(heading: str) -> str:
    """The page's text under a heading (## or ###), up to the next heading of any level."""
    lines = page().splitlines()
    start = next(index for index, line in enumerate(lines) if re.fullmatch(rf"#{{2,3}} {re.escape(heading)}", line))
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("#")), len(lines))
    return "\n".join(lines[start + 1:end])


def rows(heading: str) -> list[list[str]]:
    """The cells of each body row of the tables under a heading, whatever the spacing around the pipes."""
    found = []
    for line in section(heading).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            found.append(cells)
    return found[1:]  # the first row is the header


def prose(text: str) -> str:
    """The file's words as the page writes them: a word in angle brackets in a code span."""
    return re.sub(r"(<[^<>]+>)", r"`\1`", text)


def sentence(text: str) -> str:
    return text if text.endswith(".") else text + "."


def fields_cell(keys, empty: str) -> str:
    names = {entry.key: entry.label for entry in ontology.ontology().fields}
    return ", ".join(names[key] for key in keys) or empty


def forms(written) -> str:
    return ", ".join(f"`{form}`" for form in written)


def yaml_line(prefix: str) -> int:
    """The line of specimen.yaml that holds an entry's `- id: ...` or `- key: ...`."""
    lines = ontology.PATH.read_text(encoding="utf-8").splitlines()
    return next(index + 1 for index, line in enumerate(lines) if line.strip() == f"- {prefix}")


def citations() -> list[tuple[int, str, int, int, str]]:
    """Each citation on the page: its page line, path, first and last cited line, and the text it names."""
    text = page()
    return [(text.count("\n", 0, match.start()) + 1, match[1], int(match[2]), int(match[3] or match[2]), match[4] or "")
            for match in CITED.finditer(text)]


def fingerprint(lines: list[str], first: int, last: int) -> str:
    return hashlib.sha256("\n".join(lines[first - 1:last]).encode("utf-8")).hexdigest()[:6]


def sits(lines: list[str], text: str) -> list[int]:
    """The lines that hold a cited text: the lines that are that text alone ("- id: code"), else every line holding
    it ("id: code" is also in "- id: code_is_no_date")."""
    alone = [index + 1 for index, line in enumerate(lines) if line.strip().lstrip("- ") == text]
    return alone or [index + 1 for index, line in enumerate(lines) if text in line]


def citation_problems() -> list[str]:
    """A cited file that does not exist, a line past its end, a cited line without the text named after it (with,
    for specimen.yaml, where that text now sits), and a citation of specimen.yaml that names no text."""
    problems = []
    for at, path, first, last, text in citations():
        file = resolve(path)
        if file is None:
            problems.append(f"page line {at}: {path}: no such file")
            continue
        lines = file.read_text(encoding="utf-8").splitlines()
        if not 1 <= first <= last <= len(lines):
            problems.append(f"page line {at}: {path}:{first}-{last}: past the file's {len(lines)} lines")
        elif text and text not in lines[first - 1]:
            now = sits(lines, text) if file == ontology.PATH else []
            span = "" if not now else f"{now[0]}" if first == last else f"{now[0]}-{now[0] + last - first}"
            where = (f"; it now sits at line {now[0]}, cite {path}:{span}" if len(now) == 1
                     else f"; it sits at lines {', '.join(map(str, now))}" if now else "")
            problems.append(f"page line {at}: {path}:{first}: does not hold {text!r}{where}")
        elif not text and file == ontology.PATH:
            problems.append(f"page line {at}: {path}:{first}: names no text")
    return problems


def fingerprint_problems(pinned: dict[str, str]) -> list[str]:
    """A cited range of specimen.yaml whose text differs from its pinned fingerprint, named with the page lines that
    cite it; a cited range with no fingerprint; a fingerprint no citation uses. A range that moved is read where its
    text now sits (citation_problems reports the move)."""
    lines = ontology.PATH.read_text(encoding="utf-8").splitlines()
    cited, used = defaultdict(list), set()
    for at, path, first, last, text in citations():
        if resolve(path) != ontology.PATH or not text:
            continue
        key = f"{text} +{last - first + 1}"
        used.add(key)
        if last > len(lines) or text not in lines[first - 1]:
            now = sits(lines, text)
            if len(now) != 1:
                continue
            first, last = now[0], now[0] + last - first
        if last > len(lines) or first == last and lines[first - 1].strip().lstrip("- ") == text:
            continue
        cited[(key, first, last)].append(at)
    problems = []
    for (key, first, last), pages in cited.items():
        actual = fingerprint(lines, first, last)
        if pinned.get(key) != actual:
            lines_cited = f"{first}" if first == last else f"{first}-{last}"
            problems.append(f"page lines {', '.join(map(str, pages))}: specimen.yaml:{lines_cited} changed; re-read "
                            f"those page lines against the file, then pin {key!r}: {actual!r}")
    problems += [f"{key!r}: pinned, but no citation uses it" for key in sorted(set(pinned) - used)]
    return problems


def test_the_things_table_is_the_files():
    expected = [[thing.name, thing.examples, thing.darwin_core] for thing in ontology.ontology().things]

    assert rows("The things on a label") == expected


def test_the_field_table_is_the_files_20_fields_word_for_word():
    loaded = ontology.ontology()
    expected = [[f"`{entry.key}`", entry.label, f"`{entry.darwin_core}`", prose(entry.holds)] for entry in loaded.fields]

    assert [row[:4] for row in rows("The 20 fields")] == expected


def test_the_field_table_names_every_rule_that_derives_a_field():
    """The last column names each `derives` rule whose fields hold the row's field, and no other `derives` rule."""
    loaded = ontology.ontology()
    deriving = {rule.id for rule in loaded.rules if rule.derives}
    for row in rows("The 20 fields"):
        key = row[0].strip("`")
        named = set(re.findall(r"`(\w+)`", row[-1])) & deriving
        expected = {rule.id for rule in loaded.rules if rule.derives and key in rule.fields}
        assert named == expected, (key, sorted(expected))


def meaning(notation: ontology.Notation) -> str:
    """A notation's meaning cell: its readings, its note, and whether its final period is optional."""
    cell = sentence("; or ".join(prose(reading) for reading in notation.readings))
    if notation.note:
        cell += " " + sentence(prose(notation.note))
    return cell + (" The final period is optional." if notation.periods_optional else "")


def test_the_notation_table_is_the_files_notations_word_for_word():
    expected = [[f"`{notation.id}`", forms(notation.written), fields_cell(notation.fields, "No field"), meaning(notation)]
                for notation in ontology.ontology().notations]

    assert rows("The notations") == expected


def test_each_notations_sources_are_as_the_file_records_them():
    expected = [[f"`{notation.id}`", f"`specimen.yaml:{yaml_line('id: ' + notation.id)}` (`id: {notation.id}`)",
                 "; ".join(f"`{source}`" for source in notation.source)]
                for notation in ontology.ontology().notations]

    assert rows("Where each notation comes from") == expected


def test_the_routing_table_is_the_files_word_for_word():
    expected = [[f"`{route.id}`", prose(route.unit), fields_cell(route.fields, "No field"), prose(route.means)]
                for route in ontology.ontology().routing]

    assert [row[:4] for row in rows("The routing entries")] == expected


def test_the_questions_table_is_the_files_word_for_word():
    expected = [[f"`{question.id}`", forms(question.written), question.question, question.context, question.status]
                for question in ontology.ontology().questions]

    assert [row[:5] for row in rows("Open questions")] == expected


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
    assert len(citations()) > 50
    assert citation_problems() == []


def test_the_text_of_every_cited_range_is_the_text_the_page_was_written_against():
    assert fingerprint_problems(CITED_TEXT) == []


def test_every_cited_test_exists():
    cited = TEST.findall(page())
    assert len(cited) > 10
    missing = [f"{path}::{name}" for path, name in cited
               if not re.search(rf"^def {name}\(", (ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)]
    assert missing == []


@pytest.mark.parametrize("change", ["field", "notation"])
def test_a_page_that_disagrees_with_the_file_fails(change, monkeypatch):
    """The table checks' failure, shown on a copy of the page: a Darwin Core term or a notation's form changed."""
    text = page()
    if change == "field":
        altered = text.replace("| `collection_code` | Collection Code | `collectionCode` |",
                               "| `collection_code` | Collection Code | `institutionCode` |")
        check = test_the_field_table_is_the_files_20_fields_word_for_word
    else:
        altered = text.replace("| `lewis_collection_heading` | `LEWIS COLLECTION` |",
                               "| `lewis_collection_heading` | `LEWIS COLLECTIONS` |")
        check = test_the_notation_table_is_the_files_notations_word_for_word
    assert altered != text
    monkeypatch.setattr(sys.modules[__name__], "page", lambda: altered)

    with pytest.raises(AssertionError):
        check()


def test_a_changed_cited_range_names_the_page_lines_and_a_moved_one_where_it_sits(tmp_path, monkeypatch):
    """The range checks' failures, shown on copies of the file: day_month_order's statement reversed inside the
    range the page cites, and the whole file moved down by one line."""
    lines = ontology.PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    start = yaml_line("id: day_month_order")
    end = next(index for index in range(start, len(lines)) if "by the date check." in lines[index])
    copy = tmp_path / "specimen.yaml"
    copy.write_text("".join(lines).replace(lines[end], lines[end].replace(
        "never settled on either reading", "always settled on its first reading")), encoding="utf-8")
    monkeypatch.setattr(ontology, "PATH", copy)

    [problem] = fingerprint_problems(CITED_TEXT)
    assert problem.startswith("page lines ") and f"specimen.yaml:{start}-{end + 1} changed" in problem

    copy.write_text("# one line more\n" + "".join(lines), encoding="utf-8")
    assert fingerprint_problems(CITED_TEXT) == []
    shifted = [problem for problem in citation_problems() if "(`id: day_month_order`)" in problem
               or "'id: day_month_order'" in problem]
    assert shifted == [f"page line {at}: specimen.yaml:{start}: does not hold 'id: day_month_order'; it now sits at "
                       f"line {start + 1}, cite specimen.yaml:{start + 1}-{end + 2}"
                       for at, path, first, _, text in citations() if text == "id: day_month_order"]
