#!/usr/bin/env python3
"""Check the cost meter's month against the real Hugging Face and Google Cloud bills.

    uv run --frozen python scripts/ops/reconcile_costs.py --month 2026-10 --print-queries
    uv run --frozen python scripts/ops/reconcile_costs.py --month 2026-10 \\
        --meter-rows cost_rows_2026-10_0.json [--meter-rows ...] \\
        --huggingface hf_usage_2026-10.json \\
        --google google_export_2026-10.json [--google console_lines_2026-10.json] \\
        --out-json reconcile_2026-10.json --out-md reconcile_2026-10.md

Offline: this script reads the files you give it and writes the two reports. It calls no API, reads no
production data and runs no `gcloud`, `bq` or browser command; `--print-queries` only prints the read-only
commands you run yourself. The inputs and the judging rules are in
docs/execution/golive/COST_RECONCILIATION.md; the logic is application/cost_reconciliation.py.

Inputs: --meter-rows (repeatable: Data Connect `costEntries` pages or a list of rows; duplicates are dropped),
--huggingface (the usage page's inferenceUsageMetrics, or {"days": ...}), --google (repeatable: standard export
rows, or {"lines": ...} read from the console report; give the hourly export and the console lines together to
run the billing-day check). Without --out-md the Markdown report is printed.

Parameters: --project (the Google project whose export rows count; default the committed one), --billing-zone
(the zone Google's days are cut in; default America/Los_Angeles), --abs-usd and --relative (a gap is flagged
above the larger of the two), --free-credit-type (repeatable: credit types counted as the free allowance, in
addition to FREE_TIER), --bq-table (the export table, printed in the SQL).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import ops_common as ops

sys.path.insert(0, str(ops.ROOT / "src"))
from specimen_digitization.application import cost_reconciliation as cr  # noqa: E402

PAGE = 1000
DATA_CONNECT = "specimen-digitization-service"
# usage is read for one number, a field research call's model_calls: the requests it made, which
# the check compares with the requests Hugging Face billed.
FIELDS = ("organizationId collectionId id source specimenId runId step stage attempt kind ordinal provider resource "
          "usage reservedMicros costMicros listCostMicros costBasis outcome failureCode priceListVersion priceListAsOf "
          "occurredAt month allocationMethodId updatedAt")
OFFSET_MARK = "__OFFSET__"
# Runs in the browser console of the signed-in usage page. It reads the page's own data-props and copies one
# object to the clipboard; it never touches cookies, storage, headers or the network.
HF_CONSOLE_SNIPPET = (
    "copy(JSON.stringify((function f(o){if(o&&typeof o==='object'){if('inferenceUsageMetrics' in o)return "
    "o.inferenceUsageMetrics;for(const k in o){const r=f(o[k]);if(r)return r}}})(JSON.parse("
    "[...document.querySelectorAll('[data-props]')].map(e=>e.getAttribute('data-props'))"
    ".find(t=>t.includes('inferenceUsageMetrics'))))))")
HF_PAGE = "https://huggingface.co/settings/inference-providers/overview"


def graphql_query(month: str, offset: int | str = 0, limit: int = PAGE) -> str:
    """The read-only query for one page of a month's CostEntry rows, deployment-wide (all organizations)."""
    return (f'query {{ costEntries(where: {{month: {{eq: "{month}"}}}}, '
            "orderBy: [{organizationId: ASC}, {collectionId: ASC}, {id: ASC}], "
            f"limit: {limit}, offset: {offset}) {{ {FIELDS} }} }}")


def read_url(project: str, region: str) -> str:
    return (f"https://firebasedataconnect.googleapis.com/v1/projects/{project}/locations/{region}"
            f"/services/{DATA_CONNECT}:executeGraphqlRead")


MAX_PAGES = 100
COUNT_ROWS = "import json,sys; print(len(json.load(sys.stdin)['data']['costEntries']))"


def curl_loop(month: str, project: str, region: str) -> str:
    """A shell loop that pages through the month with curl until a page holds fewer than PAGE rows (at most
    MAX_PAGES pages). The token is Application Default Credentials' own, fetched by gcloud when the command
    runs; this script never sees it. A response that is not a page of rows (an error body) stops the loop and
    stays in its file for the operator to read."""
    body = json.dumps({"query": graphql_query(month, OFFSET_MARK)}).replace(OFFSET_MARK, "'\"$OFFSET\"'")
    return "\n".join([
        "OFFSET=0",
        f"for PAGE in $(seq 1 {MAX_PAGES}); do",
        f'  FILE="cost_rows_{month}_${{OFFSET}}.json"',
        "  curl -sS -X POST \\",
        '    -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \\',
        f'    -H "x-goog-user-project: {project}" \\',
        '    -H "Content-Type: application/json" \\',
        f"    '{read_url(project, region)}' \\",
        f"    -d '{body}' \\",
        '    -o "$FILE" || break',
        f'  ROWS=$(python3 -c "{COUNT_ROWS}" < "$FILE") || {{ echo "stopped: $FILE is not a page of cost rows" >&2; break; }}',
        f'  [ "$ROWS" -lt {PAGE} ] && break',
        f"  OFFSET=$((OFFSET + {PAGE}))",
        "done"])


def bigquery_sql(month: str, table: str, by_usage: bool) -> str:
    """The standard-export columns the reconciliation reads, for one invoice month or one usage window."""
    year, number = cr.month_of(month)
    first = f"{year:04d}-{number:02d}-01"
    after = f"{year + (number == 12):04d}-{number % 12 + 1:02d}-01"
    before = (date.fromisoformat(first) - timedelta(days=1)).isoformat()
    later = (date.fromisoformat(after) + timedelta(days=1)).isoformat()
    where = (f"usage_start_time >= TIMESTAMP('{before}') AND usage_start_time < TIMESTAMP('{later}')" if by_usage
             else f"invoice.month = '{year:04d}{number:02d}'")
    return "\n".join([
        "SELECT service, sku, STRUCT(project.id AS id) AS project, usage_start_time, usage_end_time,",
        "       cost, currency, cost_type, credits, usage, invoice",
        f"FROM `{table}`",
        f"WHERE {where}",
        "ORDER BY usage_start_time, service.description, sku.description"])


def queries(month: str, project: str, region: str, table: str) -> str:
    sql_invoice, sql_usage = bigquery_sql(month, table, False), bigquery_sql(month, table, True)
    out = [
        f"# Read-only queries for {month}. Run them yourself; nothing here runs them.",
        "",
        "## 1. Meter rows (Data Connect executeGraphqlRead, every organization)",
        "",
        "Run as a project owner with Application Default Credentials (`gcloud auth application-default login`).",
        "Each page is up to %d rows. The loop below fetches page after page until one holds fewer rows than that" % PAGE,
        "(at most %d pages), writing one file per page. Pass every file to --meter-rows. The query as plain GraphQL" % MAX_PAGES,
        "(page 1):",
        "",
        graphql_query(month),
        "",
        curl_loop(month, project, region),
        "",
        "## 2. Google bill (BigQuery standard billing export)",
        "",
        "Needs the export enabled once (see COST_RECONCILIATION.md). Set --bq-table to PROJECT.DATASET.TABLE.",
        "Save one statement as query.sql and run: bq query --nouse_legacy_sql --format=json --max_rows=1000000 \\",
        "  < query.sql > google_export_%s.json" % month,
        "",
        "-- by invoice month, as the statement groups it",
        sql_invoice + ";",
        "",
        "-- by usage time (a day either side of the month), which also catches usage invoiced the next month;",
        "-- the report assigns each row to a day in the billing zone and drops the days outside the month",
        sql_usage + ";",
        "",
        "## 3. Hugging Face bill (browser console, signed in)",
        "",
        f"Open {HF_PAGE}, choose the month on the page, open the browser console, paste the line below, then",
        "paste the clipboard into hf_usage_%s.json. It reads the page's data-props only:" % month,
        "",
        HF_CONSOLE_SNIPPET,
        ""]
    return "\n".join(out)


class UnreadableInput(Exception):
    """An input file that cannot be read as JSON or JSON Lines; the text says which file and why."""


def load_json(path: str):
    """The file's JSON, or its JSON Lines as a list. A missing, unreadable, empty or non-JSON file is refused."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise UnreadableInput(f"{path}: cannot read it ({error.strerror or type(error).__name__})") from None
    except UnicodeDecodeError:
        raise UnreadableInput(f"{path}: not UTF-8 text") from None
    if not text.strip():
        raise UnreadableInput(f"{path}: the file is empty")
    try:
        document = json.loads(text)
    except ValueError:
        pass
    else:
        if document is None:  # A bare null is no bill and no rows, not "not supplied".
            raise UnreadableInput(f"{path}: the file holds only null")
        return document
    try:  # JSON Lines, as `bq` and some exports write them
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError:
        raise UnreadableInput(f"{path}: not JSON or JSON Lines") from None


def merged_rows(paths: list[str]) -> tuple[list, list[str]]:
    """Every page's rows, and a warning for each file whose row count is a multiple of the page size: a
    full page may mean the next one was never fetched."""
    rows: list = []
    warnings: list[str] = []
    for path in paths:
        page = cr.unwrap_rows(load_json(path), path, ("costEntries", "rows", "items"))
        if page and len(page) % PAGE == 0:
            warnings.append(f"{path} holds exactly {len(page)} rows, a multiple of the page size ({PAGE}); the next page "
                            "may not have been fetched. Fetch from the next offset and pass that file too.")
        rows.extend(page)
    return rows, warnings


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check the cost meter's month against the Hugging Face and Google bills.")
    p.add_argument("--month", required=True, help="the month to check, YYYY-MM (UTC for meter rows)")
    p.add_argument("--meter-rows", action="append", default=[], metavar="FILE", help="CostEntry rows (repeatable)")
    p.add_argument("--huggingface", metavar="FILE", help="the Hugging Face usage bill")
    p.add_argument("--google", action="append", default=[], metavar="FILE", help="the Google bill (repeatable)")
    p.add_argument("--project", default=ops.settings.PROJECT, help="the Google project whose export rows count")
    p.add_argument("--billing-zone", default=cr.DEFAULT_BILLING_ZONE, help="the zone Google's days are cut in")
    p.add_argument("--free-credit-type", action="append", default=[], metavar="TYPE",
                   help="a credit type counted as the free allowance, besides FREE_TIER (repeatable)")
    p.add_argument("--abs-usd", default="0.05", help="flag a gap above max(this, --relative x billed); default 0.05")
    p.add_argument("--relative", default="0.05", help="the relative part of the limit; default 0.05 (5%%)")
    p.add_argument("--out-json", metavar="FILE", help="write the JSON report here")
    p.add_argument("--out-md", metavar="FILE", help="write the Markdown report here")
    p.add_argument("--print-queries", action="store_true", help="print the read-only queries and exit")
    p.add_argument("--bq-table", default="BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID",
                   help="the billing export table, for the printed SQL")
    p.add_argument("--update-bills", metavar="FILE",
                   help="put the month's Hugging Face days into this provider_bills.json (commit it by pull request), "
                        "then exit; needs --huggingface")
    p.add_argument("--bills-as-of", metavar="YYYY-MM-DD", help="the day the bill was read, for --update-bills")
    return p


def thresholds(args, fail) -> cr.Thresholds:
    try:
        absolute = int((Decimal(args.abs_usd) * cr.MICRO).to_integral_value())
        relative = float(Decimal(args.relative))
    except (InvalidOperation, ValueError):
        fail("--abs-usd and --relative must be numbers")
    if absolute < 0 or relative < 0:
        fail("--abs-usd and --relative must not be negative")
    return cr.Thresholds(absolute_micros=absolute, relative=relative)


def main(argv=None) -> int:
    p = parser()
    args = p.parse_args(argv)
    try:
        cr.month_of(args.month)
    except ValueError:
        p.error("--month must be YYYY-MM")
    if args.print_queries:
        print(queries(args.month, ops.project(), ops.region(), args.bq_table))
        return 0
    if args.update_bills:
        if not args.huggingface or not args.bills_as_of:
            p.error("--update-bills needs --huggingface and --bills-as-of")
        try:
            committed = load_json(args.update_bills)
            updated = cr.bills_with_month(committed, load_json(args.huggingface), args.month, args.bills_as_of)
        except (cr.ReconciliationInputError, UnreadableInput, KeyError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        Path(args.update_bills).write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        days = [day for day in updated["huggingface"]["days"] if day.startswith(args.month + "-")]
        print(f"{args.month}: {len(days)} days in {args.update_bills}, version {updated['version']}.")
        return 0
    if not args.meter_rows:
        p.error("--meter-rows is required (see --print-queries)")
    if not args.huggingface and not args.google:
        p.error("give at least one bill: --huggingface and/or --google")
    limits = thresholds(args, p.error)
    for out_path in (args.out_json, args.out_md):
        if out_path and not Path(out_path).resolve().parent.is_dir():
            p.error(f"the folder for {out_path} does not exist")
        if out_path and Path(out_path).is_dir():
            p.error(f"{out_path} is a folder, not a file")
    try:
        rows, warnings = merged_rows(args.meter_rows)
        report = cr.reconcile(
            meter_rows=rows, month=args.month, thresholds=limits, project_id=args.project,
            huggingface=load_json(args.huggingface) if args.huggingface else None,
            google=tuple(load_json(path) for path in args.google) if args.google else None,
            billing_zone=args.billing_zone, free_credit_types=cr.FREE_CREDIT_TYPES | set(args.free_credit_type),
            input_warnings=warnings)
    except (cr.ReconciliationInputError, UnreadableInput) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for text in warnings:
        print(f"warning: {text}", file=sys.stderr)
    markdown = cr.render_markdown(report)
    wrote = []
    outputs = [(path, text) for path, text in ((args.out_json, json.dumps(report, indent=2) + "\n"),
                                               (args.out_md, markdown)) if path]
    try:
        for path, text in outputs:
            Path(path).write_text(text, encoding="utf-8")
            wrote.append(path)
    except OSError as error:
        for path in wrote:  # All or nothing: never leave half a report.
            Path(path).unlink(missing_ok=True)
        print(f"error: {error.filename or path}: cannot write it ({error.strerror or type(error).__name__})",
              file=sys.stderr)
        return 2
    if wrote:
        totals = report["totals"]
        print(f"{args.month}: billed {cr.usd(totals['billed_micros'])}, metered {cr.usd(totals['metered_micros'])}, "
              f"{len(report['flags'])} flagged. Wrote {', '.join(wrote)}.")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
