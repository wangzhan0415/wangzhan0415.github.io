#!/usr/bin/env python3
"""Apply manually approved publication abstracts with strict safeguards."""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ALLOWED_FIELDS = ["abstract", "abstract_source", "abstract_source_url", "abstract_retrieved_at", "abstract_verified"]
FORBIDDEN_FIELDS = ["title", "authors", "date", "display_date", "publication", "publication_type", "doi", "stable_id", "featured", "draft", "jcr"]

@dataclass
class Publication:
    path: Path
    front: str
    body: str
    title: str
    doi: str
    stable_id: str

def scalar(front: str, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", front)
    if not m:
        return ""
    return m.group(1).strip().strip('"\'')

def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()

def normalize_doi(doi: str) -> str:
    return doi.strip().lower().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")

def load_publications() -> dict[str, Publication]:
    pubs: dict[str, Publication] = {}
    for path in sorted(Path().glob("content/publication/*/index.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        front = parts[1]
        stable = scalar(front, "stable_id") or path.parent.name
        pubs[stable] = Publication(path, front, parts[2], scalar(front, "title"), scalar(front, "doi"), stable)
    return pubs

def yaml_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'

def set_scalar(front: str, key: str, value: str | bool) -> str:
    rendered = "true" if value is True else "false" if value is False else yaml_quote(value)
    pattern = rf"(?m)^{re.escape(key)}:\s*.*$"
    line = f"{key}: {rendered}"
    if re.search(pattern, front):
        return re.sub(pattern, line, front)
    return front.rstrip() + "\n" + line + "\n"

def validate(row: dict[str, str], pubs: dict[str, Publication]) -> tuple[Publication | None, str]:
    if row.get("decision", "").strip().lower() != "approve":
        return None, "skipped_not_approve"
    if row.get("confidence", "").strip().lower() in {"low", "rejected"}:
        return None, "rejected_confidence"
    stable = row.get("stable_id", "").strip()
    pub = pubs.get(stable)
    if not pub:
        return None, "stable_id_not_found"
    if normalize_doi(row.get("doi", "")) != normalize_doi(pub.doi):
        return None, "doi_mismatch"
    local_title = row.get("local_title", "")
    if local_title != pub.title and normalize_title(local_title) != normalize_title(pub.title):
        return None, "title_mismatch"
    abstract = (row.get("replacement_abstract") or row.get("candidate_abstract") or "").strip()
    if not abstract:
        return None, "empty_candidate_abstract"
    return pub, "ok"

def apply_row(pub: Publication, row: dict[str, str]) -> str:
    abstract = (row.get("replacement_abstract") or row.get("candidate_abstract") or "").strip()
    front = pub.front
    front = set_scalar(front, "abstract", abstract)
    front = set_scalar(front, "abstract_source", row.get("abstract_source", ""))
    front = set_scalar(front, "abstract_source_url", row.get("abstract_source_url", ""))
    front = set_scalar(front, "abstract_retrieved_at", row.get("retrieved_at", ""))
    front = set_scalar(front, "abstract_verified", True)
    return "---" + front + "---" + pub.body

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-file", required=True)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    pubs = load_publications()
    report: list[dict[str, str]] = []
    backup_dir = Path("artifacts/abstract-import-backup")
    with open(args.review_file, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            pub, status = validate(row, pubs)
            stable = row.get("stable_id", "")
            if not pub:
                report.append({"stable_id": stable, "status": status, "path": ""}); continue
            report.append({"stable_id": stable, "status": "would_apply" if not args.apply else "applied", "path": str(pub.path)})
            if args.apply:
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pub.path, backup_dir / f"{stable}.index.md.bak")
                pub.path.write_text(apply_row(pub, row), encoding="utf-8")
    for item in report:
        print(f"{item['stable_id']}: {item['status']} {item['path']}")
    if args.apply:
        Path("reports").mkdir(exist_ok=True)
        with open("reports/approved_abstract_import_report.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["stable_id", "status", "path"]); writer.writeheader(); writer.writerows(report)
    return 0

if __name__ == "__main__":
    sys.exit(main())
