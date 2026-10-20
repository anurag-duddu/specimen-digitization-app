"""reconcile_costs.py: the offline monthly check of the cost meter against the bills (COST_RECONCILIATION.md)."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import re
import shlex
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


def test_the_curl_loop_sends_the_same_query_with_each_offset_and_never_handles_a_token():
    loop = cli.curl_loop("2026-10", "specimen-digitization", "us-east4")
    assert loop.startswith("for OFFSET in 0 1000 2000 3000 4000; do") and loop.endswith("done")
    assert "gcloud auth application-default print-access-token" in loop
    command = " ".join(line.strip().rstrip("\\") for line in loop.splitlines()[1:-1])
    argv = shlex.split(command)
    assert argv[:3] == ["curl", "-sS", "-X"]
    body = json.loads(argv[argv.index("-d") + 1].replace("$OFFSET", "2000"))
    assert body == {"query": cli.graphql_query("2026-10", 2000)}
    assert "offset: 2000)" in body["query"] and argv[argv.index("-o") + 1] == "cost_rows_2026-10_${OFFSET}.json"
    assert "Bearer $(gcloud" in " ".join(argv)


def test_the_graphql_reads_only_and_names_every_column_the_check_uses():
    query = cli.graphql_query("2026-10")
    assert query.startswith("query {") and "mutation" not in query
    for column in ("organizationId", "collectionId", "id", "provider", "resource", "costMicros", "listCostMicros",
                   "costBasis", "occurredAt", "month", "allocationMethodId", "stage", "kind", "source",
                   "priceListVersion"):
        assert re.search(rf"\b{column}\b", query), column
    assert "usage " not in query  # the bulky usage column is not needed


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


def test_an_unreadable_input_stops_with_a_named_error_and_writes_nothing(tmp_path):
    meter = write(tmp_path, "m.json", [row(1, 1)])
    out_json = tmp_path / "never.json"
    for name, value, message in (("bad_hf.json", {"histogram": 7}, "huggingface histogram: unrecognized layout"),
                                 ("bad_google.json", {"nope": 1}, "google bill: expected a list"),
                                 ("not_json.json", "{{", "is not JSON or JSON Lines")):
        path = write(tmp_path, name, value)
        flag = "--google" if name == "bad_google.json" else "--huggingface"
        code, out, err = run("--month", "2026-10", "--meter-rows", meter, flag, path, "--out-json", str(out_json))
        assert code != 0 and out == "" and message in err, (name, err)
    assert not out_json.exists()
    bad_rows = write(tmp_path, "bad_rows.json", [{"provider": "huggingface", "resource": "x", "month": "2026-10"}])
    code, _, err = run("--month", "2026-10", "--meter-rows", bad_rows, "--huggingface",
                       write(tmp_path, "empty.json", {"days": {}}))
    assert code == 2 and "error: meter row 0 costMicros" in err
