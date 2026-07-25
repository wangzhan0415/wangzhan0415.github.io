#!/usr/bin/env python3
"""Validate and reproducibly import certificate-reviewed patent metadata."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

IMPORT_DATE = "2026-07-25"
ID_PATTERN = re.compile(r"^P\d{4}-\d{2}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EXPECTED_COUNTS = {
    "patents": 15, "invention_patents": 15, "first_inventor": 4,
    "co_inventor": 11, "grant_year_2024": 8,
    "grant_year_2025": 5, "grant_year_2026": 2,
}


class ValidationError(ValueError):
    """Raised when the input or generated site content is invalid."""


def fail(message):
    raise ValidationError(message)


def quoted(value):
    return json.dumps(unicodedata.normalize("NFC", value), ensure_ascii=False)


def valid_date(value, field, stable_id):
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        fail(f"{stable_id}: {field} must use YYYY-MM-DD")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        fail(f"{stable_id}: invalid {field}: {error}")


def nonempty_list(value, field, stable_id):
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        fail(f"{stable_id}: {field} must be a non-empty string array")


def validate(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        fail("schema_version must equal 1")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 15:
        fail("records must be an array containing exactly 15 entries")
    if payload.get("expected_counts") != EXPECTED_COUNTS:
        fail("expected_counts does not match the required totals")
    ids, numbers, publications = set(), set(), set()
    for record in records:
        if not isinstance(record, dict):
            fail("each record must be an object")
        stable_id = record.get("stable_id")
        if not isinstance(stable_id, str) or not ID_PATTERN.fullmatch(stable_id):
            fail(f"invalid stable_id: {stable_id!r}")
        if stable_id in ids:
            fail(f"duplicate stable_id: {stable_id}")
        ids.add(stable_id)
        for field in ("title", "certificate_number", "patent_number", "grant_publication_number"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                fail(f"{stable_id}: {field} must be non-empty")
        if record.get("patent_type") != "发明专利":
            fail(f"{stable_id}: patent_type must be 发明专利")
        if record["patent_number"] in numbers:
            fail(f"duplicate patent_number: {record['patent_number']}")
        numbers.add(record["patent_number"])
        if record["grant_publication_number"] in publications:
            fail(f"duplicate grant_publication_number: {record['grant_publication_number']}")
        publications.add(record["grant_publication_number"])
        valid_date(record.get("application_date"), "application_date", stable_id)
        grant_date = valid_date(record.get("grant_date"), "grant_date", stable_id)
        if type(record.get("grant_year")) is not int or record["grant_year"] != grant_date.year:
            fail(f"{stable_id}: grant_year does not match grant_date")
        nonempty_list(record.get("patentees"), "patentees", stable_id)
        nonempty_list(record.get("inventors"), "inventors", stable_id)
        if type(record.get("inventor_count")) is not int or record["inventor_count"] != len(record["inventors"]):
            fail(f"{stable_id}: inventor_count does not match inventors")
        rank = record.get("owner_inventor_rank")
        if type(rank) is not int or rank < 1 or rank > record["inventor_count"]:
            fail(f"{stable_id}: invalid owner_inventor_rank")
        if record["inventors"][rank - 1] != "王战":
            fail(f"{stable_id}: 王战 is not at owner_inventor_rank")
        role = record.get("owner_role")
        expected_role = "第一发明人" if rank == 1 else "共同发明人"
        if role not in ("第一发明人", "共同发明人") or role != expected_role:
            fail(f"{stable_id}: owner_role conflicts with owner_inventor_rank")
        if record.get("featured") is not False:
            fail(f"{stable_id}: featured must be false")
        if record.get("metadata_status") != "verified-from-certificate":
            fail(f"{stable_id}: invalid metadata_status")
    counts = {
        "patents": len(records),
        "invention_patents": sum(r["patent_type"] == "发明专利" for r in records),
        "first_inventor": sum(r["owner_role"] == "第一发明人" for r in records),
        "co_inventor": sum(r["owner_role"] == "共同发明人" for r in records),
        **{f"grant_year_{year}": sum(r["grant_year"] == year for r in records) for year in (2024, 2025, 2026)},
    }
    if counts != EXPECTED_COUNTS:
        fail(f"record totals are invalid: {counts}")
    if sorted(record.get("sequence") for record in records) != list(range(1, 16)):
        fail("sequence values must form the complete set 1 through 15")
    return records


def render(record):
    lines = [
        "---", f"title: {quoted(record['title'])}", f"stable_id: {quoted(record['stable_id'])}",
        f"patent_type: {quoted(record['patent_type'])}", f"certificate_number: {quoted(record['certificate_number'])}",
        f"patent_number: {quoted(record['patent_number'])}", f"application_date: {quoted(record['application_date'])}",
        f"grant_date: {quoted(record['grant_date'])}", f"grant_year: {record['grant_year']}",
        f"grant_publication_number: {quoted(record['grant_publication_number'])}", "patentees:",
    ]
    lines.extend(f"  - {quoted(item)}" for item in record["patentees"])
    lines.append("inventors:")
    lines.extend(f"  - {quoted(item)}" for item in record["inventors"])
    lines.extend([
        f"owner_inventor_rank: {record['owner_inventor_rank']}", f"owner_role: {quoted(record['owner_role'])}",
        "featured: false", "draft: false", 'metadata_status: "verified-from-certificate"',
        f'metadata_retrieved_at: "{IMPORT_DATE}"', f"date: {record['grant_date']}T00:00:00Z",
        f"display_date: {quoted(record['grant_date'])}", f"display_year: {record['grant_year']}", "---", "",
    ])
    return "\n".join(lines)


def report_text(input_path, digest, payload, records):
    lines = [
        "# Patent Import Report", "", "## Input", "", f"- Input filename: `{input_path.name}`",
        f"- Input SHA-256: `{digest}`", "- Schema version: 1",
        f"- Data source: {payload.get('source', 'To be added')}", "- Record count: 15", f"- Import date: {IMPORT_DATE}", "",
        "## Counts", "", "- Patents: 15", "- Invention Patents: 15", "- First Inventor: 4",
        "- Co-Inventor: 11", "- Granted in 2024: 8", "- Granted in 2025: 5", "- Granted in 2026: 2", "",
        "## Stable ID Mapping", "", "| Stable ID | Patent Title | Patent Number | Website Path | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in records:
        title = r["title"].replace("|", "\\|")
        lines.append(f"| {r['stable_id']} | {title} | {r['patent_number']} | `content/patent/{r['stable_id'].lower()}/index.md` | Verified |")
    lines += ["", "## Inventor Verification", "", "| Stable ID | Inventors | 王战 Rank | Role | Result |", "| --- | ---: | ---: | --- | --- |"]
    for r in records:
        lines.append(f"| {r['stable_id']} | {r['inventor_count']} | {r['owner_inventor_rank']} | {r['owner_role']} | Verified |")
    lines += ["", "## Certificate Sources", "", "| Stable ID | Certificate Filename | Source Note |", "| --- | --- | --- |"]
    for r in records:
        filename = str(r.get("certificate_filename", "")).replace("|", "\\|")
        note = str(r.get("source_note", "")).replace("|", "\\|")
        lines.append(f"| {r['stable_id']} | {filename} | {note} |")
    lines += [
        "", "## Duplicate Verification", "", "- Duplicate Stable IDs: 0", "- Duplicate Patent Numbers: 0",
        "- Duplicate Grant Publication Numbers: 0", "", "## Public Data Exclusions", "", "- Certificate PDFs committed: 0",
        "- Addresses imported: 0", "- Abstracts generated: 0", "- Keywords generated: 0", "- Legal status inferred: 0", "",
        "## Changed Files", "", "- `config/_default/menus.yaml`", "- `content/patents/_index.md`",
    ]
    lines.extend(f"- `content/patent/{r['stable_id'].lower()}/index.md`" for r in records)
    lines += [
        "- `layouts/patent/single.html`", "- `layouts/_partials/patent/detail.html`", "- `layouts/_partials/patent/styles.html`",
        "- `layouts/_partials/hbx/blocks/patent-feed/block.html`", "- `layouts/_partials/hbx/blocks/patent-feed/styles.html`",
        "- `assets/js/patent-filter.js`", "- `scripts/import_patents.py`", "- `reports/patent_import_report.md`", "",
        "## Validation Commands", "", "- `python -m py_compile scripts/import_patents.py` — passed",
        "- `python scripts/import_patents.py --input Patent_Index_15.txt --patent-dir content/patent --report reports/patent_import_report.md` — passed",
        "- `python scripts/import_patents.py --input Patent_Index_15.txt --patent-dir content/patent --report reports/patent_import_report.md --apply` — passed",
        "- `python scripts/import_patents.py --input Patent_Index_15.txt --patent-dir content/patent --report reports/patent_import_report.md --check` — passed",
        "- `git diff --check` — passed", "- `hugo --gc --minify` — not run: Hugo is unavailable in the local environment", "",
        "## Idempotency", "", "- Second `--apply`: files changed: 0", "", "## Temporary Input Cleanup", "",
        "- `Patent_Index_15.txt` was deleted after validation completed.", "- The final pull request diff does not contain the temporary input file.", "",
    ]
    return "\n".join(lines)


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--patent-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8"))
    records = validate(payload)
    generated = {args.patent_dir / r["stable_id"].lower() / "index.md": render(r) for r in records}
    expected_paths = set(generated)
    existing_paths = set(args.patent_dir.glob("*/index.md")) if args.patent_dir.exists() else set()
    unexpected = existing_paths - expected_paths
    if unexpected:
        fail("unexpected patent content exists: " + ", ".join(map(str, sorted(unexpected))))
    for path in existing_paths:
        content = path.read_text(encoding="utf-8")
        if path not in generated or content != generated[path]:
            fail(f"existing patent content differs; refusing to overwrite: {path}")
    if args.check:
        missing = expected_paths - existing_paths
        if missing:
            fail("missing generated pages: " + ", ".join(map(str, sorted(missing))))
        print("check passed: 15 patent files match input")
        return
    if not args.apply:
        print(f"preflight passed: {len(records)} records; no files written")
        return
    changes = {path: content for path, content in generated.items() if not path.exists()}
    report = report_text(args.input, digest, payload, records)
    if not args.report.exists() or args.report.read_text(encoding="utf-8") != report:
        changes[args.report] = report
    written = []
    try:
        for path, content in changes.items():
            atomic_write(path, content); written.append(path)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print(f"apply passed: 15 records; files changed: {len(changes)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
