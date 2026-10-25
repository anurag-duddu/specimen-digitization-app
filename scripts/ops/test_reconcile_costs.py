"""reconcile_costs.py: the offline monthly check of the cost meter against the bills (COST_RECONCILIATION.md)."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
cli = importlib.import_module("reconcile_costs")

from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES  # noqa: E402

QWEN = HUGGINGFACE_ROUTES["handwriting-qwen"].model_id
ORG, COLLECTION = "0b7e2f4c-1d3a-4c5e-9f60-7a8b9c0d1e2f", "5f4e3d2c-1b0a-4987-8654-3210fedcba98"


def run(*args):
    result = subprocess.run([sys.executable, str(HERE / "reconcile_costs.py"), *args], capture_output=True, text=True,
                            timeout=120)
    return result.returncode, result.stdout, result.stderr


def row(index, cost, month="2026-10", resource="handwriting-qwen", provider="huggingface", basis="computed"):
    return {"organizationId": ORG, "collectionId": COLLECTION, "id": f"00000000-0000-4000-8000-{index:012d}",
            "source": "paid_call", "kind": "model", "stage": "reading", "provider": provider, "resource": resource,
            "costMicros": str(cost), "listCostMicros": str(cost), "costBasis": basis, "month": month,
            "occurredAt": f"{month}-10T12:00:00Z", "allocationMethodId": None}


def write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return str(path)


def inputs(tmp_path):
    """Two overlapping meter pages, a raw Hugging Face page object, and Google export plus console lines."""
    page_one = {"data": {"costEntries": [row(1, 1_000_000), row(2, 2_000_000)]}}
    page_two = {"data": {"costEntries": [row(2, 2_000_000), row(3, 500_000), row(4, 9, month="2026-09")]}}
    raw = {"props": {"inferenceUsageMetrics": {"histogram": [
        {"date": "2026-10-10", "bars": [{"model": QWEN, "numRequests": 3, "usedNanoUsd": 2_500_000_000}]}]}}}
    export = [{"service": {"description": "Cloud Run"}, "sku": {"description": "Jobs CPU in us-east4"},
               "project": {"id": "specimen-digitization"}, "usage_start_time": "2026-10-10 12:00:00",
               "usage_end_time": "2026-10-10 13:00:00", "cost": "0.30",
               "credits": [{"amount": "-0.10", "type": "FREE_TIER"}]}]
    console = {"lines": [{"service": "Cloud Run", "sku": "Jobs CPU in us-east4", "day": "2026-10-10", "cost_usd": 0.30,
                          "credits_usd": -0.10}]}
    return {"meter": [write(tmp_path, "page1.json", page_one), write(tmp_path, "page2.json", page_two)],
            "hf": write(tmp_path, "hf.json", raw),
            "google": [write(tmp_path, "export.json", export), write(tmp_path, "console.json", console)]}


def args_for(files, *extra):
    out = ["--month", "2026-10"]
    for path in files["meter"]:
        out += ["--meter-rows", path]
    out += ["--huggingface", files["hf"]]
    for path in files["google"]:
        out += ["--google", path]
    return out + list(extra)


# ---- --print-queries --------------------------------------------------------

def test_print_queries_needs_only_a_month_and_prints_the_three_read_only_commands():
    code, out, err = run("--month", "2026-10", "--print-queries")
    assert code == 0 and err == ""
    assert 'costEntries(where: {month: {eq: "2026-10"}}' in out and "limit: 1000, offset: 0" in out
    assert ("https://firebasedataconnect.googleapis.com/v1/projects/specimen-digitization/locations/us-east4/services/"
            "specimen-digitization-service:executeGraphqlRead") in out
    assert "WHERE invoice.month = '202610'" in out
    assert "usage_start_time >= TIMESTAMP('2026-09-30') AND usage_start_time < TIMESTAMP('2026-11-02')" in out
    assert "gcp_billing_export_v1_BILLING_ACCOUNT_ID" in out
    assert "inferenceUsageMetrics" in out and "[data-props]" in out
    assert "bq query" in out and "executeGraphql:" not in out
    assert "mutation" not in out.lower()


def test_the_bigquery_table_is_the_operators_and_a_december_window_rolls_into_january():
    code, out, _ = run("--month", "2026-12", "--print-queries", "--bq-table", "p.d.gcp_billing_export_v1_AAA_BBB_CCC")
    assert code == 0
    assert "FROM `p.d.gcp_billing_export_v1_AAA_BBB_CCC`" in out and "BILLING_ACCOUNT_ID" not in out
    assert "invoice.month = '202612'" in out
    assert "TIMESTAMP('2026-11-30') AND usage_start_time < TIMESTAMP('2027-01-02')" in out


FAKE_CURL = '''#!PYTHON
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_LOG"]
calls = sum(1 for _ in open(log)) if os.path.exists(log) else 0
plan = json.loads(os.environ["FAKE_PAGES"])
size = plan[min(calls, len(plan) - 1)]
query = json.loads(args[args.index("-d") + 1])["query"]
offset = int(query.split("offset: ")[1].split(")")[0])
with open(log, "a") as handle:
    handle.write(json.dumps({"offset": offset, "header": args[args.index("-H") + 1], "query": query}) + "\\n")
body = ({"data": {"costEntries": [{"id": str(offset + i)} for i in range(size)]}} if size is not None
        else {"error": {"message": "denied"}})
with open(args[args.index("-o") + 1], "w") as out:
    json.dump(body, out)
'''


def run_loop(tmp_path, plan, shell="bash"):
    """Run the printed curl loop with a stand-in curl (page sizes from ``plan``; None is an error body) and a
    stand-in gcloud, so nothing leaves the machine. Returns the offsets asked for, the files written and stderr."""
    shell_path = shutil.which(shell)
    if shell_path is None:
        pytest.skip(f"{shell} is not installed")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(FAKE_CURL.replace("PYTHON", sys.executable))
    (bin_dir / "gcloud").write_text("#!/bin/sh\necho fake-token\n")
    for name in ("curl", "gcloud"):
        (bin_dir / name).chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    environment = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(work / "calls.log"),
                   "FAKE_PAGES": json.dumps(plan)}
    result = subprocess.run([shell_path, "-c", cli.curl_loop("2026-10", "specimen-digitization", "us-east4")], cwd=work,
                            env=environment, capture_output=True, text=True, timeout=120)
    log = work / "calls.log"
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    files = sorted(path.name for path in work.glob("cost_rows_*"))
    return result, calls, files


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_the_curl_loop_pages_until_a_short_page_with_each_offset_and_never_handles_a_token(tmp_path, shell):
    result, calls, files = run_loop(tmp_path, [1000] * 7 + [250], shell)
    assert result.returncode == 0 and result.stderr == ""
    assert [c["offset"] for c in calls] == [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000]
    assert files == sorted(f"cost_rows_2026-10_{offset}.json" for offset in range(0, 8000, 1000))
    assert all(c["query"] == cli.graphql_query("2026-10", c["offset"]) for c in calls)
    assert {c["header"] for c in calls} == {"Authorization: Bearer fake-token"}  # gcloud's answer reaches only curl


def test_the_curl_loop_stops_after_a_short_empty_failed_or_endless_page(tmp_path):
    cases = {"short first page": ([12], [0]), "an empty page ends it": ([1000, 1000, 0], [0, 1000, 2000]),
             "a full page and an error body": ([1000, None], [0, 1000])}
    for name, (plan, offsets) in cases.items():
        folder = tmp_path / name.replace(" ", "_")
        folder.mkdir()
        result, calls, _ = run_loop(folder, plan)
        assert [c["offset"] for c in calls] == offsets, name
        if None in plan:
            assert "stopped: cost_rows_2026-10_1000.json is not a page of cost rows" in result.stderr
    # An API that ignores the offset and always answers a full page cannot keep it running for ever.
    endless = tmp_path / "endless"
    endless.mkdir()
    _, calls, files = run_loop(endless, [1000])
    assert len(calls) == len(files) == cli.MAX_PAGES == 100


def test_the_curl_loop_text_names_no_fixed_page_count_and_the_queries_say_it_continues():
    loop = cli.curl_loop("2026-10", "specimen-digitization", "us-east4")
    assert "for OFFSET in" not in loop and "OFFSET=$((OFFSET + 1000))" in loop and '[ "$ROWS" -lt 1000 ] && break' in loop
    code, out, _ = run("--month", "2026-10", "--print-queries")
    assert code == 0 and "until one holds fewer rows than that" in out and "< query.sql > google_export_2026-10.json" in out


def test_the_graphql_reads_only_and_names_every_column_the_check_uses():
    query = cli.graphql_query("2026-10")
    assert query.startswith("query {") and "mutation" not in query
    for column in ("organizationId", "collectionId", "id", "provider", "resource", "costMicros", "listCostMicros",
                   "costBasis", "occurredAt", "month", "allocationMethodId", "stage", "kind", "source",
                   "priceListVersion", "usage"):
        assert re.search(rf"\b{column}\b", query), column


def test_the_console_snippet_only_reads_the_pages_data_props():
    snippet = cli.HF_CONSOLE_SNIPPET
    assert "data-props" in snippet and snippet.startswith("copy(")
    for forbidden in ("cookie", "localstorage", "sessionstorage", "fetch", "xmlhttprequest", "authorization", "token",
                      "bearer", "password", "indexeddb", "navigator", "eval", "document.write"):
        assert forbidden not in snippet.lower(), forbidden


# ---- the report -------------------------------------------------------------

def test_end_to_end_writes_the_json_and_markdown_reports(tmp_path):
    files = inputs(tmp_path)
    out_json, out_md = str(tmp_path / "report.json"), str(tmp_path / "report.md")
    code, out, err = run(*args_for(files, "--out-json", out_json, "--out-md", out_md))
    assert code == 0 and err == ""
    report = json.loads(Path(out_json).read_text())
    assert report["month"] == "2026-10"
    assert report["inputs"]["rows_supplied"] == 5 and report["inputs"]["duplicates_dropped"] == 1
    assert report["inputs"]["rows_other_month"] == 1 and report["inputs"]["meter_rows_in_month"] == 3
    qwen = next(m for m in report["huggingface"]["models"] if m["label"] == QWEN)
    assert (qwen["billed_micros"], qwen["metered_micros"], qwen["gap_micros"]) == (2_500_000, 3_500_000, 1_000_000)
    # Three settled calls and three billed requests, but the bill is 2,500,000 of 3,500,000 at list: a discount.
    assert qwen["flagged"] and [e["code"] for e in qwen["explanations"]] == ["provider_discount"]
    worker = next(f for f in report["google"]["families"] if f["family"] == "specimen-worker")
    assert (worker["billed_cost_micros"], worker["billed_credits_micros"]) == (300_000, -100_000)
    assert report["google"]["source"] == "export"
    markdown = Path(out_md).read_text()
    assert markdown.startswith("# Cost meter check, 2026-10\n") and "## What needs a look" in markdown
    assert out.startswith("2026-10: billed $") and "Wrote " + out_json in out and out_md in out


def test_without_an_output_file_the_markdown_goes_to_standard_output(tmp_path):
    code, out, _ = run(*args_for(inputs(tmp_path)))
    assert code == 0 and out.startswith("# Cost meter check, 2026-10\n")
    assert "## Hugging Face, by model" in out


def test_thresholds_and_extra_free_credit_types_reach_the_report(tmp_path):
    files = inputs(tmp_path)
    out_json = str(tmp_path / "lax.json")
    assert run(*args_for(files, "--out-json", out_json, "--abs-usd", "100", "--relative", "0"))[0] == 0
    lax = json.loads(Path(out_json).read_text())
    assert lax["thresholds"] == {"absolute_micros": 100_000_000, "relative": 0.0} and lax["flags"] == []
    discount = [{"service": {"description": "Cloud Run"}, "sku": {"description": "Jobs CPU in us-east4"},
                 "usage_start_time": "2026-10-10 12:00:00", "cost": "0.30",
                 "credits": [{"amount": "-0.10", "type": "SPENDING_BASED_DISCOUNT"}]}]
    google = write(tmp_path, "discount.json", discount)
    base = ["--month", "2026-10", "--meter-rows", files["meter"][0], "--google", google]
    run(*base, "--out-json", out_json)
    assert json.loads(Path(out_json).read_text())["google"]["totals"]["billed_credits_micros"] == 0
    run(*base, "--free-credit-type", "SPENDING_BASED_DISCOUNT", "--out-json", out_json)
    assert json.loads(Path(out_json).read_text())["google"]["totals"]["billed_credits_micros"] == -100_000


def test_json_lines_and_a_billing_zone_option_are_accepted(tmp_path):
    lines = "\n".join(json.dumps(r) for r in [row(1, 100_000), row(2, 200_000)]) + "\n"
    meter = write(tmp_path, "rows.jsonl", lines)
    hf = write(tmp_path, "hf.json", {"days": {"2026-10-10": {QWEN: {"requests": 2, "nano_usd": 300_000_000}}}})
    out_json = str(tmp_path / "r.json")
    code, _, err = run("--month", "2026-10", "--meter-rows", meter, "--huggingface", hf, "--billing-zone", "UTC-5",
                       "--out-json", out_json)
    assert code == 0, err
    report = json.loads(Path(out_json).read_text())
    assert report["billing_zone"]["used"] == "UTC-5" and report["flags"] == []


@pytest.mark.parametrize("args,message", [
    (["--month", "2026-13", "--print-queries"], "--month must be YYYY-MM"),
    (["--month", "2026-10"], "--meter-rows is required"),
    (["--month", "2026-10", "--meter-rows", "{meter}"], "give at least one bill"),
    (["--month", "2026-10", "--meter-rows", "{meter}", "--huggingface", "{meter}", "--abs-usd", "lots"], "must be numbers"),
    (["--month", "2026-10", "--meter-rows", "{meter}", "--huggingface", "{meter}", "--relative", "-1"], "must not be negative"),
])
def test_bad_arguments_exit_with_status_two_and_say_what_to_fix(tmp_path, args, message):
    meter = write(tmp_path, "m.json", [])
    code, out, err = run(*[a.replace("{meter}", meter) for a in args])
    assert code == 2 and out == "" and message in err


UNREADABLE = {  # kind -> (how to make the file, what the error says)
    "missing": ("missing", "cannot read it (No such file or directory)"),
    "empty": ("", "the file is empty"),
    "blank": ("  \n\t\n", "the file is empty"),
    "not_json": ("{{", "not JSON or JSON Lines"),
    "not_utf8": (b"\xff\xfe\x00\xff", "not UTF-8 text"),
    "directory": ("directory", "cannot read it (Is a directory)"),
    "null": ("null", "the file holds only null"),
}


def test_an_output_that_is_a_folder_or_cannot_be_written_exits_two_and_leaves_no_half_report(tmp_path):
    meter, hf = write(tmp_path, "m.json", [row(1, 1)]), write(tmp_path, "hf.json", {"days": {}})
    folder = tmp_path / "already-a-folder"
    folder.mkdir()
    code, out, err = run("--month", "2026-10", "--meter-rows", meter, "--huggingface", hf, "--out-json", str(folder))
    assert code == 2 and out == "" and "is a folder, not a file" in err, err
    locked = tmp_path / "locked"
    locked.mkdir()
    out_json, out_md = tmp_path / "report.json", locked / "report.md"
    locked.chmod(0o500)
    try:
        code, out, err = run("--month", "2026-10", "--meter-rows", meter, "--huggingface", hf,
                             "--out-json", str(out_json), "--out-md", str(out_md))
    finally:
        locked.chmod(0o700)
    assert code == 2 and out == "", (code, err)
    assert err.startswith(f"error: {out_md}: cannot write it"), err
    assert not out_json.exists() and not out_md.exists()


@pytest.mark.parametrize("flag", ["--meter-rows", "--huggingface", "--google"])
@pytest.mark.parametrize("kind", sorted(UNREADABLE))
def test_a_missing_empty_or_unreadable_input_exits_two_with_an_error_line_and_writes_nothing(tmp_path, flag, kind):
    content, message = UNREADABLE[kind]
    bad = tmp_path / f"{kind}.json"
    if kind == "directory":
        bad.mkdir()
    elif kind != "missing":
        bad.write_bytes(content if isinstance(content, bytes) else content.encode())
    good = {"--meter-rows": write(tmp_path, "m.json", [row(1, 1)]), "--huggingface": write(tmp_path, "hf.json", {"days": {}}),
            "--google": write(tmp_path, "g.json", {"lines": []})}
    good[flag] = str(bad)
    out_json, out_md = tmp_path / "never.json", tmp_path / "never.md"
    code, out, err = run("--month", "2026-10", "--meter-rows", good["--meter-rows"], "--huggingface", good["--huggingface"],
                         "--google", good["--google"], "--out-json", str(out_json), "--out-md", str(out_md))
    assert code == 2 and out == "", (code, err)
    assert err == f"error: {bad}: {message}\n", err
    assert not out_json.exists() and not out_md.exists()


def test_a_file_that_reads_but_is_the_wrong_shape_also_exits_two_and_writes_nothing(tmp_path):
    meter = write(tmp_path, "m.json", [row(1, 1)])
    out_json = tmp_path / "never.json"
    for name, value, flag, message in (("bad_hf.json", {"histogram": 7}, "--huggingface", "huggingface histogram: unrecognized layout"),
                                       ("bad_google.json", {"nope": 1}, "--google", "google bill: expected a list")):
        code, out, err = run("--month", "2026-10", "--meter-rows", meter, flag, write(tmp_path, name, value),
                             "--out-json", str(out_json))
        assert code == 2 and out == "" and f"error: {message}" in err, (name, err)
    assert not out_json.exists()
    bad_rows = write(tmp_path, "bad_rows.json", [{"provider": "huggingface", "resource": "x", "month": "2026-10"}])
    code, _, err = run("--month", "2026-10", "--meter-rows", bad_rows, "--huggingface",
                       write(tmp_path, "empty.json", {"days": {}}))
    assert code == 2 and "error: meter row 0 costMicros" in err
    # An empty list of rows is a valid (empty) page, unlike an empty file.
    code, _, _ = run("--month", "2026-10", "--meter-rows", write(tmp_path, "none.json", []), "--huggingface",
                     write(tmp_path, "days.json", {"days": {}}), "--out-json", str(tmp_path / "ok.json"))
    assert code == 0


def test_an_output_folder_that_does_not_exist_is_refused_before_anything_is_read(tmp_path):
    files = inputs(tmp_path)
    code, out, err = run(*args_for(files, "--out-md", str(tmp_path / "no_such_folder" / "r.md")))
    assert code == 2 and out == "" and "does not exist" in err


def test_a_page_file_holding_a_multiple_of_the_page_size_is_warned_about(tmp_path):
    rows = [row(index, 1) for index in range(1, 2001)]
    hf = write(tmp_path, "hf.json", {"days": {}})
    out_json, out_md = str(tmp_path / "r.json"), str(tmp_path / "r.md")
    full, partial = write(tmp_path, "full.json", {"data": {"costEntries": rows[:1000]}}), write(tmp_path, "part.json", rows[1000:1999])
    code, out, err = run("--month", "2026-10", "--meter-rows", full, "--meter-rows", partial, "--huggingface", hf,
                         "--out-json", out_json, "--out-md", out_md)
    assert code == 0
    assert err.count("warning:") == 1 and f"{full} holds exactly 1000 rows, a multiple of the page size (1000)" in err
    report = json.loads(Path(out_json).read_text())
    assert report["warnings"] == [err.removeprefix("warning: ").strip()] and report["inputs"]["meter_rows_in_month"] == 1999
    assert f"## Warnings\n\n- {report['warnings'][0]}\n" in Path(out_md).read_text()
    # Two full pages in one file warn once for the file; a short page and an empty list do not warn.
    both = write(tmp_path, "both.json", rows)
    code, _, err = run("--month", "2026-10", "--meter-rows", both, "--huggingface", hf, "--out-json", out_json)
    assert code == 0 and "holds exactly 2000 rows" in err
    code, _, err = run("--month", "2026-10", "--meter-rows", partial, "--meter-rows", write(tmp_path, "none.json", []),
                       "--huggingface", hf, "--out-json", out_json)
    assert code == 0 and err == "" and json.loads(Path(out_json).read_text())["warnings"] == []


# ---- --update-bills -----------------------------------------------------------

def test_update_bills_puts_the_months_registered_models_into_the_committed_file(tmp_path):
    qwen, glm = HUGGINGFACE_ROUTES["handwriting-qwen"].model_id, HUGGINGFACE_ROUTES["first-pass-glm"].model_id
    bills = tmp_path / "provider_bills.json"
    bills.write_text(json.dumps({"version": "provider-bills-2026-09-30", "as_of": "2026-09-30", "currency": "USD",
                                 "huggingface": {"cached_input_routes": ["harness-deepseek"], "days": {
                                     "2026-09-29": {qwen: {"requests": 3, "nano_usd": 900_000}},
                                     "2026-10-01": {qwen: {"requests": 1, "nano_usd": 1}}}}}))
    hf = tmp_path / "hf.json"
    hf.write_text(json.dumps({"days": {
        "2026-10-02": {qwen: {"requests": 2, "nano_usd": 600_000}, "someone/unregistered-model": {"requests": 9, "nano_usd": 9},
                       glm: {"requests": 0, "nano_usd": 0}},
        "2026-11-01": {qwen: {"requests": 5, "nano_usd": 5}}}}))
    code, out, err = run("--month", "2026-10", "--huggingface", str(hf), "--update-bills", str(bills),
                         "--bills-as-of", "2026-11-02")
    assert (code, err) == (0, "") and "1 days" in out
    written = json.loads(bills.read_text())
    assert (written["version"], written["as_of"]) == ("provider-bills-2026-11-02", "2026-11-02")
    # Another month is kept, the month is replaced whole; unregistered models, empty cells and other months' days left out.
    assert written["huggingface"]["days"] == {"2026-09-29": {qwen: {"requests": 3, "nano_usd": 900_000}},
                                              "2026-10-02": {qwen: {"requests": 2, "nano_usd": 600_000}}}
    assert written["huggingface"]["cached_input_routes"] == ["harness-deepseek"]
    code, _, err = run("--month", "2026-10", "--update-bills", str(bills))
    assert code == 2 and "--update-bills needs --huggingface and --bills-as-of" in err


def test_the_committed_bills_are_what_update_bills_writes_from_the_october_bill():
    committed = json.loads((Path(cli.cr.__file__).parent / "profiles" / "provider_bills.json").read_text())
    days = committed["huggingface"]["days"]
    normalized = {"days": {day: dict(cells) for day, cells in days.items()}}
    assert cli.cr.bills_with_month(committed, normalized, "2026-10", committed["as_of"]) == committed
