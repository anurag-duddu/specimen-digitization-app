"""Score field values against the reference set's truth: plan criteria 1 and 2.

`docs/execution/units/PLAN.md` section 1 defines the measurement; this module is its scorer (WP 0). It moves
the 2026-10-25 rig's strict rule (`~/specimen-golive/runs/free-harness-20261025/score.py`, run without
`--lenient`) into the repository and adapts it from one label to one whole specimen and to criterion 1's
outcomes.

The strict rule reads a field's value as its parsed value, else its normalized value, else its literal
(`compared_value`), and `value_ok` compares it with the truth field by field. A field is settled when its
state is `supported` with a value, or `not_present` / `not_applicable` (settled as absent). A settled field is
marked when the run carries the units path's code `marked:<field>:<label>:<why>` in its reasons or in a
finding's code (spec section 4, "Marked"); today's code writes no such code, so on today's code every settled
field is cleared.

For a field the truth holds (category primary or derived): cleared right, cleared wrong, marked with a right
value, marked with a wrong value, or left without a value. A field settled as absent holds no value, so it is
wrong. A precise location within 0.85 similarity of the truth is right; one that only names the place is
partial, and partial counts as wrong (2026-10-18 convention).
For a field the truth says is absent (category absent): settled as absent is right, settled with a value is
wrong (wrongly settled), else left without a value.
Right values (criterion 1 (b)) are cleared right plus marked right. A specimen with no truth is counted
(cleared, marked, left without a value) and never scored for accuracy.

Criterion 2 compares two runs of the same specimens. A field is cleared in a run when it is settled (with a value
or as absent) and not marked; the denominator is the fields cleared in both runs, and a difference is any change
between the two cleared results: a value against absence, or two values whose compared values differ after `norm`
(elevations compared as numbers). `norm` folds letter case and keeps ASCII letters and digits only, deleting every
other character: "R.D.Mitchell" and "R.D.mitchell" are the same, "Mexico" and "México" differ ("mexico" against
"mxico"), and "México" and "Mèxico" are the same ("mxico" both). Each difference carries its kind: "value_absent"
when one run has a value and the other absence, "two_values" when both have values.

Usage:
  python tests/reference/units_program/score.py RESULTS.jsonl [RESULTS.jsonl ...] [--json OUT]
Each results file holds one JSON row per specimen run: `subject`, `fields` ({key: {state, literal, parsed,
normalized}}), `reasons`, `findings` ([{code, field}]) and `disposition`. A file is one arm and repeat, named
by its folder and stem (`r1/pair`).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = HERE / "manifest.json"
FIXTURE = ROOT / "tests" / "fixtures" / "field_model_pilot_rows.json"

PRIMARY = ("fmnh_ins_number", "country", "province_state", "precise_location", "elevation_from_ft",
           "date_visited_from", "collectors")
DERIVED = ("elevation_from_m", "elevation_to_m", "elevation_to_ft", "date_visited_to")
SCORED = PRIMARY + DERIVED
CATEGORIES = ("primary", "derived", "absent")
OUTCOMES = ("cleared_right", "cleared_wrong", "marked_right", "marked_wrong", "left_without_value")
SETTLED_ABSENT = {"not_present", "not_applicable"}
COUNTRY = {"Philippines": {"philippines", "philippineislands", "republicofthephilippines"},
           "Guatemala": {"guatemala", "republicofguatemala"}}
CORE = ("mckinley", "mckimley", "mtapo", "yepocapa", "slope")
MARKED = re.compile(r"^marked:([a-z_]+):")


def norm(text):
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def compared_value(field):
    """The strict rule's value: parsed, else normalized, else literal."""
    return field.get("parsed") or field.get("normalized") or field.get("literal")


def value_ok(key, field, expected):
    """True, False, or "partial" (a precise location that only names the place)."""
    value = compared_value(field)
    if key == "country":
        return norm(value) in COUNTRY.get(expected, {norm(expected)})
    if key == "province_state":
        return norm(value) in {norm(expected) + suffix for suffix in ("", "prov", "province", "department")}
    if key == "precise_location":
        best = max(similar(field.get("literal") or "", expected), similar(value or "", expected))
        return True if best >= 0.85 else ("partial" if any(c in norm(value) for c in CORE) else False)
    if key.startswith("elevation_"):
        try:
            return abs(float(value) - float(expected)) < 0.011
        except (TypeError, ValueError):
            return False
    if key.startswith("date_visited"):
        return value == expected
    if key == "collectors":
        return norm(value) == norm(expected)
    if key == "fmnh_ins_number":
        return re.sub(r"\D", "", value or "") == expected
    raise KeyError(key)


def settled(field):
    """"value", "absent" or None (left without a value)."""
    state = field.get("state")
    if state == "supported" and any(field.get(k) for k in ("parsed", "normalized", "literal")):
        return "value"
    return "absent" if state in SETTLED_ABSENT else None


def marked_fields(row):
    """Fields the run marks for a person: `marked:<field>:<label>:<why>` in its reasons or finding codes."""
    codes = list(row.get("reasons") or []) + [f.get("code") or "" for f in row.get("findings") or []]
    return {m.group(1) for m in (MARKED.match(code) for code in codes) if m}


def outcome(key, field, expected, marked):
    """One field's criterion-1 outcome, and whether a wrong value was a partial precise location."""
    how = settled(field)
    if how is None:
        return "left_without_value", False
    prefix = "marked_" if marked else "cleared_"
    if expected is None:
        return prefix + ("right" if how == "absent" else "wrong"), False
    if how == "absent":
        return prefix + "wrong", False
    ok = value_ok(key, field, expected)
    return prefix + ("right" if ok is True else "wrong"), ok == "partial"


def truth(manifest=None, fixture=None):
    """{subject: {field: value} for a specimen with truth, None for one without}."""
    manifest = manifest or json.loads(MANIFEST.read_text())
    fixture = fixture or json.loads(FIXTURE.read_text())
    rows = {r["subject"]: r for r in fixture["rows"]}
    out = {}
    for entry in manifest["specimens"]:
        source = entry["truth"]
        if source == "fixture":
            out[entry["subject"]] = dict(rows[entry["subject"]]["expected"])
        elif source == "none":
            out[entry["subject"]] = None
        else:
            raise ValueError(f"unknown truth source {source!r}")
    return out


def score_specimen(row, expected):
    """Cells {field: (category, outcome)} for a specimen with truth; counts by settlement for one without."""
    fields = row.get("fields") or {}
    marked = marked_fields(row)
    if expected is None:
        counts = Counter()
        for key, field in fields.items():
            how = settled(field)
            counts["left_without_value" if how is None else ("marked" if key in marked else "cleared")
                   + ("" if how is None else "_" + how)] += 1
        return {"subject": row["subject"], "truth": False, "counts": dict(counts),
                "disposition": row.get("disposition")}
    cells, partial = {}, []
    for key in SCORED:
        value = expected.get(key)
        category = "absent" if value is None else ("primary" if key in PRIMARY else "derived")
        result, is_partial = outcome(key, fields.get(key) or {}, value, key in marked)
        cells[key] = (category, result)
        if is_partial:
            partial.append(key)
    unscored = Counter()
    for key, field in fields.items():
        if key in SCORED:
            continue
        how = settled(field)
        unscored["left_without_value" if how is None else ("marked" if key in marked else "cleared")
                 + ("" if how is None else "_" + how)] += 1
    return {"subject": row["subject"], "truth": True, "cells": cells, "partial": partial,
            "counts": dict(unscored), "disposition": row.get("disposition")}


def tally(scored):
    """Per category: every outcome's count and the denominator n (fields scored in that category)."""
    out = {c: dict.fromkeys(OUTCOMES, 0) | {"n": 0, "of_which_partial": 0} for c in CATEGORIES}
    for s in scored:
        if not s["truth"]:
            continue
        for key, (category, result) in s["cells"].items():
            out[category][result] += 1
            out[category]["n"] += 1
            if key in s["partial"]:
                out[category]["of_which_partial"] += 1
    for c in CATEGORIES:
        out[c]["right"] = out[c]["cleared_right"] + out[c]["marked_right"]
        out[c]["marked"] = out[c]["marked_right"] + out[c]["marked_wrong"]
    return out


def counts(scored, with_truth):
    """Settlement counts (cleared, marked, left without a value) over the fields not scored for accuracy."""
    total = Counter()
    for s in scored:
        if s["truth"] == with_truth:
            total.update(s["counts"])
    return dict(sorted(total.items()))


def dispositions(scored):
    found = Counter(s["disposition"] for s in scored)
    return {"specimens": len(scored), "cleared": found.get("cleared", 0), "by_disposition": dict(found)}


def same_value(key, a, b):
    if key.startswith("elevation_"):
        try:
            return abs(float(a) - float(b)) < 0.011
        except (TypeError, ValueError):
            pass
    return norm(a) == norm(b)


def cleared_result(field):
    """What a cleared field holds, for criterion 2: its compared value, or "(absent)" when settled as absent."""
    return compared_value(field) if settled(field) == "value" else "(absent)"


def cleared_differences(rows_a, rows_b):
    """Criterion 2: the fields cleared (settled with a value or as absent, unmarked) in both runs, and those whose
    cleared results differ: a value against absence, or two values that differ after `norm`."""
    by_subject = {r["subject"]: r for r in rows_b}
    both, different = 0, []
    for a in rows_a:
        b = by_subject.get(a["subject"])
        if b is None:
            continue
        marked_a, marked_b = marked_fields(a), marked_fields(b)
        for key, fa in (a.get("fields") or {}).items():
            fb = (b.get("fields") or {}).get(key) or {}
            how_a, how_b = settled(fa), settled(fb)
            if how_a is None or how_b is None or key in marked_a or key in marked_b:
                continue
            both += 1
            if how_a != how_b or (how_a == "value"
                                  and not same_value(key, compared_value(fa), compared_value(fb))):
                different.append({"subject": a["subject"], "field": key, "kind":
                                  "value_absent" if how_a != how_b else "two_values",
                                  "a": cleared_result(fa), "b": cleared_result(fb)})
    return {"cleared_in_both": both, "different": len(different), "fields": different}


def load(path):
    latest = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            latest[row["subject"]] = row    # a specimen run again keeps its latest row
    return list(latest.values())


def report(files, manifest=None, fixture=None):
    expected = truth(manifest, fixture)
    runs = {f"{Path(f).parent.name}/{Path(f).stem}": load(f) for f in files}
    out = {"runs": {}, "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}
    for name, rows in runs.items():
        missing = sorted(set(expected) - {r["subject"] for r in rows})
        scored = [score_specimen(r, expected[r["subject"]]) for r in rows]
        out["runs"][name] = {"specimens": len(rows), "missing": missing, "criterion_1": tally(scored),
                             "unscored_fields_with_truth_specimens": counts(scored, True),
                             "no_truth_specimens": counts(scored, False),
                             "dispositions": dispositions(scored), "specimen_cells": scored}
    names = list(runs)
    out["criterion_2"] = {f"{a} vs {b}": cleared_differences(runs[a], runs[b])
                          for i, a in enumerate(names) for b in names[i + 1:]}
    return out


def markdown(result):
    lines = ["| run | category | n | cleared right | cleared wrong (partial) | marked right | marked wrong | "
             "left without a value | right |", "|---|---|---|---|---|---|---|---|---|"]
    for name, run in result["runs"].items():
        for category in CATEGORIES:
            t = run["criterion_1"][category]
            lines.append(f"| {name} | {category} | {t['n']} | {t['cleared_right']} | {t['cleared_wrong']} "
                         f"({t['of_which_partial']}) | {t['marked_right']} | {t['marked_wrong']} | "
                         f"{t['left_without_value']} | {t['right']} |")
    lines += ["", "| run | specimens | missing | cleared disposition | no-truth specimens: settlement counts |",
              "|---|---|---|---|---|"]
    for name, run in result["runs"].items():
        d = run["dispositions"]
        lines.append(f"| {name} | {run['specimens']} | {', '.join(run['missing']) or '-'} | "
                     f"{d['cleared']} of {d['specimens']} | {run['no_truth_specimens']} |")
    lines += ["", "| comparison | fields cleared in both | cleared on different values |", "|---|---|---|"]
    for name, c in result["criterion_2"].items():
        lines.append(f"| {name} | {c['cleared_in_both']} | {c['different']} |")
    return "\n".join(lines)


def main(argv):
    files = [a for a in argv if not a.startswith("--") and not a.endswith(".json")]
    result = report(files)
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(markdown(result))


if __name__ == "__main__":
    main(sys.argv[1:])
