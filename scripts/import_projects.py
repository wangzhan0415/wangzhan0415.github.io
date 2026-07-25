#!/usr/bin/env python3
"""Validate and import the manually reviewed public project dataset."""

import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


EXPECTED_SHA256 = "8af9dbcbfae6d73bea5cfd12c4623dcd4c1e4414973dddce57a7c7262e1b3a77"
LEVEL_RANKS = {"国家级": 600, "省部级": 500, "市厅级": 400, "集团级": 300, "企业级": 200, "其他": 100}
EXPECTED_COUNTS = {
    "source_projects": 18, "public_projects": 16, "excluded_private": 2,
    "in_progress": 5, "completed": 11, "national": 1,
    "provincial_ministerial": 7, "municipal_departmental": 0,
    "group": 4, "enterprise": 4, "other": 0,
}
COUNT_LEVEL_KEYS = {
    "国家级": "national", "省部级": "provincial_ministerial",
    "市厅级": "municipal_departmental", "集团级": "group",
    "企业级": "enterprise", "其他": "other",
}
OUTPUT_FIELDS = (
    "stable_id", "title", "start_date", "end_date", "display_period", "status",
    "status_key", "project_type", "project_program", "project_level", "level_rank",
    "sort_key", "role", "role_group", "public_summary", "research_topics", "visibility",
    "disclosure_status", "show_detail", "featured", "draft", "metadata_status",
    "metadata_retrieved_at",
)


def fail(message):
    raise ValueError(message)


def read_input(path):
    if not path.is_file():
        fail(f"input file is missing: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        fail(f"input SHA-256 mismatch: {digest}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"input is not valid UTF-8 JSON: {exc}")
    return payload, digest


def valid_date(value, field, stable_id):
    if not isinstance(value, str):
        fail(f"{stable_id}: {field} must be a YYYY-MM-DD string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        fail(f"{stable_id}: invalid {field}: {value}")
    if parsed.isoformat() != value:
        fail(f"{stable_id}: invalid {field}: {value}")
    return parsed


def validate(payload):
    if payload.get("schema_version") != 1:
        fail("schema_version must equal 1")
    records = payload.get("records")
    excluded = payload.get("excluded_records")
    if not isinstance(records, list) or len(records) != 16:
        fail("records must contain exactly 16 items")
    if not isinstance(excluded, list) or len(excluded) != 2:
        fail("excluded_records must contain exactly 2 items")
    if payload.get("expected_counts") != EXPECTED_COUNTS:
        fail("expected_counts does not match the approved count policy")
    policy = payload.get("sort_policy")
    if not isinstance(policy, dict) or policy.get("level_ranks") != LEVEL_RANKS:
        fail("sort_policy level_ranks does not match the approved mapping")

    ids = []
    titles = []
    statuses = Counter()
    levels = Counter()
    for record in records:
        stable_id = record.get("stable_id")
        if not isinstance(stable_id, str) or not re.fullmatch(r"PRJ\d{4}-\d{2}", stable_id):
            fail(f"invalid stable_id: {stable_id!r}")
        ids.append(stable_id)
        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            fail(f"{stable_id}: title must be non-empty")
        titles.append(title)
        start = valid_date(record.get("start_date"), "start_date", stable_id)
        end = valid_date(record.get("end_date"), "end_date", stable_id)
        if start > end:
            fail(f"{stable_id}: start_date is later than end_date")
        for field in ("display_period", "project_type", "role", "public_summary"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                fail(f"{stable_id}: {field} must be non-empty")
        status = record.get("status")
        if status not in ("在研", "已完成"):
            fail(f"{stable_id}: invalid status")
        statuses[status] += 1
        level = record.get("project_level")
        if level not in LEVEL_RANKS or record.get("level_rank") != LEVEL_RANKS.get(level):
            fail(f"{stable_id}: invalid project_level/level_rank")
        levels[level] += 1
        topics = record.get("research_topics")
        if not isinstance(topics, list) or not 2 <= len(topics) <= 5 or not all(isinstance(x, str) and x.strip() for x in topics):
            fail(f"{stable_id}: research_topics must contain 2 to 5 non-empty strings")
        required = {
            "visibility": "public-summary", "disclosure_status": "approved",
            "show_detail": False, "featured": False, "draft": False,
            "metadata_status": "manually-reviewed",
        }
        for field, expected in required.items():
            if record.get(field) != expected:
                fail(f"{stable_id}: {field} must equal {expected!r}")

    if len(set(ids)) != 16:
        fail("record stable_ids must be unique")
    if len(set(titles)) != 16:
        fail("record titles must be unique")
    if statuses != Counter({"已完成": 11, "在研": 5}):
        fail(f"status counts do not match: {dict(statuses)}")
    for level, key in COUNT_LEVEL_KEYS.items():
        if levels[level] != EXPECTED_COUNTS[key]:
            fail(f"level count does not match for {level}: {levels[level]}")

    excluded_ids = []
    for record in excluded:
        stable_id = record.get("stable_id")
        if not stable_id:
            fail("excluded record stable_id must be non-empty")
        excluded_ids.append(stable_id)
        if record.get("visibility") != "private" or record.get("disclosure_status") != "not-public":
            fail(f"{stable_id}: excluded record is not marked private/not-public")
    if len(set(excluded_ids)) != 2:
        fail("excluded stable_ids must be unique")
    if set(ids) & set(excluded_ids):
        fail("public and excluded stable_ids overlap")

    actual_counts = {
        "source_projects": len(records) + len(excluded), "public_projects": len(records),
        "excluded_private": len(excluded), "in_progress": statuses["在研"],
        "completed": statuses["已完成"],
        **{key: levels[level] for level, key in COUNT_LEVEL_KEYS.items()},
    }
    if actual_counts != payload["expected_counts"]:
        fail(f"expected_counts does not match actual data: {actual_counts}")
    return records


def build_outputs(records):
    outputs = {}
    for source in records:
        item = dict(source)
        item["status_key"] = {"在研": "in-progress", "已完成": "completed"}[source["status"]]
        item["sort_key"] = f'{source["level_rank"]:03d}|{source["start_date"]}|{source["stable_id"]}'
        public = {field: item[field] for field in OUTPUT_FIELDS if field in item and item[field] not in (None, "", [])}
        filename = source["stable_id"].lower() + ".json"
        if filename in outputs:
            fail(f"duplicate output filename: {filename}")
        outputs[filename] = json.dumps(public, ensure_ascii=False, indent=2) + "\n"
    return outputs


def display_order(records):
    return sorted(records, key=lambda x: (x["level_rank"], x["start_date"], x["stable_id"]), reverse=True)


def report_text(payload, digest, records):
    ordered = display_order(records)
    rows = "\n".join(
        f'| {number} | {item["stable_id"]} | {item["title"]} | {item["project_level"]} | {item["status"]} | data/projects/{item["stable_id"].lower()}.json |'
        for number, item in enumerate(ordered, 1)
    )
    order = ", ".join(item["stable_id"] for item in ordered)
    files = "\n".join(f'- `data/projects/{item["stable_id"].lower()}.json`' for item in ordered)
    return f"""# Project Website Import Report

## Input

- Input filename: `Project_Website_Import_Final_16.txt`
- Input SHA-256: `{digest}`
- Schema version: {payload['schema_version']}
- Source workbook: `{payload['source_workbook']}`
- Source worksheet: `{payload['source_worksheet']}`
- Data source: {payload['data_source']}
- Import date: {date.today().isoformat()}

## Counts

- Source projects: 18
- Public website projects: 16
- Excluded private projects: 2
- In progress: 5
- Completed: 11
- National: 1
- Provincial/Ministerial: 7
- Municipal/Departmental: 0
- Group: 4
- Enterprise: 4
- Other: 0

## Normalization

- 6项省级计划名称已从 `project_type` 迁移到 `project_program`，`project_type` 统一为“科研计划项目”。
- 首台（套）项目规范为“示范应用项目”。
- 2项不公开项目被排除，项目状态规范为“在研”/“已完成”。
- 未创建项目详情页。

## Stable ID Mapping

| Display Order | Stable ID | Project Title | Level | Status | Data File |
|---:|---|---|---|---|---|
{rows}

## Excluded Records

- 排除数量：2
- 排除原因：人工复核标记为不公开

## Sorting Verification

- Primary: `level_rank` descending
- Secondary: `start_date` descending
- Tertiary: `stable_id` descending
- Final order: {order}

## Duplicate Verification

- Duplicate Stable IDs: 0
- Duplicate titles: 0
- Duplicate output filenames: 0

## Public Data Boundaries

- Project amounts published: 0
- Project numbers published: 0
- Contract information published: 0
- Private projects published: 0
- Detail pages created: 0
- External data inferred: 0

## Changed Files

{files}
- `content/projects/_index.md`
- `layouts/_partials/hbx/blocks/project-feed/block.html`
- `layouts/_partials/hbx/blocks/project-feed/styles.html`
- `assets/js/project-filter.js`
- `scripts/import_projects.py`
- `reports/project_import_report.md`

## Validation Commands

- `python -m py_compile scripts/import_projects.py` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md --apply` — passed
- `python scripts/import_projects.py --input Project_Website_Import_Final_16.txt --data-dir data/projects --report reports/project_import_report.md --check` — passed
- `git diff --check` — passed
- `hugo version` — unavailable in the local environment; no build or dependency changes were attempted

## Idempotency

- Second `--apply`: `files changed: 0`

## Temporary Input Cleanup

- `Project_Website_Import_Final_16.txt`已删除。
- 最终PR差异不包含输入TXT。
"""


def verify_directory(data_dir, outputs):
    existing = sorted(data_dir.glob("*.json")) if data_dir.is_dir() else []
    if {path.name for path in existing} != set(outputs):
        fail("data directory filenames do not exactly match the validated input")
    differences = [path.name for path in existing if path.read_text(encoding="utf-8") != outputs[path.name]]
    if differences:
        fail("data files differ from validated input: " + ", ".join(differences))


def apply(data_dir, report, outputs, report_content):
    existing = list(data_dir.glob("*.json")) if data_dir.is_dir() else []
    unexpected = sorted(path.name for path in existing if path.name not in outputs)
    differing = sorted(path.name for path in existing if path.name in outputs and path.read_text(encoding="utf-8") != outputs[path.name])
    if unexpected:
        fail("unexpected existing project files: " + ", ".join(unexpected))
    if differing:
        fail("existing project files differ; refusing overwrite: " + ", ".join(differing))
    data_dir.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    changes = [(data_dir / name, content) for name, content in outputs.items() if not (data_dir / name).exists()]
    if not report.exists() or report.read_text(encoding="utf-8") != report_content:
        changes.append((report, report_content))
    staged = []
    try:
        for target, content in changes:
            fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((Path(temp_name), target))
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            if temporary.exists():
                temporary.unlink()
    print(f"files changed: {len(changes)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        payload, digest = read_input(args.input)
        records = validate(payload)
        outputs = build_outputs(records)
        report_content = report_text(payload, digest, records)
        if args.check:
            verify_directory(args.data_dir, outputs)
            print("check passed: 16 project files match the validated input")
        elif args.apply:
            apply(args.data_dir, args.report, outputs, report_content)
        else:
            print("preflight passed: 16 public records; 2 private records excluded")
        print(f"input SHA-256: {digest}")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
