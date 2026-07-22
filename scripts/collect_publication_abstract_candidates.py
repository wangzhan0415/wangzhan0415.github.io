#!/usr/bin/env python3
"""Collect review-only publication abstract candidates from DOI metadata."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, build_opener

PUBLICATION_GLOB = "content/publication/*/index.md"
CSV_FIELDS = ["stable_id","doi","local_title","local_year","publication","candidate_title","candidate_year","abstract_source","abstract_source_url","retrieved_at","doi_match","title_match","year_match","source_match","confidence","candidate_abstract","decision","replacement_abstract","reviewer_notes"]
FAILED_FIELDS = ["stable_id", "doi", "local_title", "reason", "detail"]

@dataclass
class Publication:
    path: Path
    title: str
    year: str
    publication: str
    doi: str
    stable_id: str

class MetadataHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._capture_script = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = attr.get("name") or attr.get("property")
            content = attr.get("content", "")
            if key and content:
                self.meta[key.lower()] = content
        if tag.lower() == "script" and attr.get("type", "").lower() == "application/ld+json":
            self._capture_script = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._capture_script:
            self.json_ld.append("".join(self._script_parts))
            self._capture_script = False

    def handle_data(self, data: str) -> None:
        if self._capture_script:
            self._script_parts.append(data)

def scalar(front: str, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", front)
    if not m:
        return ""
    value = m.group(1).strip()
    if value in {'""', "''"}:
        return ""
    return value.strip('"\'')

def read_publications() -> list[Publication]:
    pubs: list[Publication] = []
    for path in sorted(Path().glob(PUBLICATION_GLOB)):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        front = parts[1] if len(parts) > 1 else ""
        date = scalar(front, "date")
        year = scalar(front, "display_year") or (date[:4] if date else "")
        stable = scalar(front, "stable_id") or path.parent.name
        pubs.append(Publication(path, scalar(front, "title"), year, scalar(front, "publication"), scalar(front, "doi"), stable))
    return pubs

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def norm_doi(doi: str) -> str:
    return doi.strip().lower().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")

def norm_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", html.unescape(title)).lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()

def clean_abstract(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?i)^\s*abstract\s*[:：.-]?\s*", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()

def opener_get(url: str, user_agent: str, timeout: float = 20.0) -> tuple[int, str, str]:
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.8"})
    with build_opener().open(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, resp.read().decode(charset, errors="replace"), final_url

def fetch_json(url: str, user_agent: str, delay: float) -> dict[str, Any]:
    last_error = ""
    for attempt in range(3):
        if attempt or delay:
            time.sleep(delay)
        try:
            status, body, _ = opener_get(url, user_agent)
            if status == 200:
                data = json.loads(body)
                return data if isinstance(data, dict) else {}
            last_error = f"http_{status}"
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc.__class__.__name__
    raise RuntimeError(last_error or "request_failed")

def evaluate(pub: Publication, doi: str, title: str, year: str, source_pub: str, source: str, url: str, raw: str, errors: list[str]) -> dict[str, Any]:
    dmatch = norm_doi(doi) == norm_doi(pub.doi)
    tmatch = "exact" if title.strip() == pub.title.strip() else ("normalized" if norm_title(title) == norm_title(pub.title) else "failed")
    ymatch: bool | str = "unknown" if not year or not pub.year else (year == pub.year)
    smatch: bool | str = "unknown"
    if pub.publication and source_pub:
        smatch = norm_title(pub.publication) == norm_title(source_pub) or norm_title(pub.publication) in norm_title(source_pub) or norm_title(source_pub) in norm_title(pub.publication)
    confidence = "rejected"
    if dmatch and tmatch != "failed" and (ymatch is True or smatch is True):
        confidence = "high"
    elif dmatch and tmatch != "failed":
        confidence = "medium"
    elif dmatch:
        confidence = "low"
    return {"stable_id": pub.stable_id, "doi": pub.doi, "local_title": pub.title, "local_year": pub.year, "publication": pub.publication, "candidate_title": title, "candidate_year": year, "raw_abstract": raw, "cleaned_abstract": clean_abstract(raw), "abstract_source": source, "abstract_source_url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "doi_match": dmatch, "title_match": tmatch, "year_match": ymatch, "source_match": smatch, "confidence": confidence, "errors": errors}

def crossref(pub: Publication, ua: str, delay: float) -> dict[str, Any] | None:
    url = "https://api.crossref.org/works/" + quote(pub.doi, safe="")
    if os.environ.get("CROSSREF_MAILTO"):
        url += "?mailto=" + quote(os.environ["CROSSREF_MAILTO"])
    data = fetch_json(url, ua, delay).get("message", {})
    raw = data.get("abstract") or ""
    if not raw:
        return None
    title = (data.get("title") or [""])[0]
    container = (data.get("container-title") or [""])[0]
    year_parts = (((data.get("published") or {}).get("date-parts") or [[""]])[0])
    return evaluate(pub, data.get("DOI", ""), title, str(year_parts[0]) if year_parts else "", container or data.get("publisher", ""), "crossref", data.get("URL", url), raw, [])

def datacite(pub: Publication, ua: str, delay: float) -> dict[str, Any] | None:
    data = fetch_json("https://api.datacite.org/dois/" + quote(pub.doi, safe=""), ua, delay).get("data", {}).get("attributes", {})
    descs = data.get("descriptions") or []
    raw = next((d.get("description", "") for d in descs if d.get("description")), "")
    if not raw:
        return None
    titles = data.get("titles") or []
    return evaluate(pub, data.get("doi", ""), titles[0].get("title", "") if titles else "", str(data.get("publicationYear", "")), data.get("publisher", ""), "datacite", data.get("url", ""), raw, [])

def jsonld_values(obj: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and isinstance(v, (str, list)):
                found.append(", ".join(v) if isinstance(v, list) else v)
            found.extend(jsonld_values(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(jsonld_values(item, key))
    return found

def publisher(pub: Publication, ua: str, delay: float) -> dict[str, Any] | None:
    time.sleep(delay)
    status, body, final_url = opener_get("https://doi.org/" + quote(pub.doi, safe="/"), ua)
    host = urlparse(final_url).netloc.lower()
    if status != 200 or any(bad in host for bad in ["researchgate", "semanticscholar", "scholar.google"]):
        return None
    parser = MetadataHTMLParser(); parser.feed(body[:500000])
    raw = next((parser.meta.get(k) for k in ["citation_abstract", "dc.description", "dc.description", "og:description"] if parser.meta.get(k)), "")
    for block in parser.json_ld:
        if raw:
            break
        try:
            raw = next(iter(jsonld_values(json.loads(block), "description")), "")
        except json.JSONDecodeError:
            continue
    if not raw:
        return None
    title = parser.meta.get("citation_title", "") or parser.meta.get("og:title", pub.title)
    year = (parser.meta.get("citation_publication_date", "") or "")[:4]
    return evaluate(pub, pub.doi, title, year, parser.meta.get("citation_journal_title", ""), "publisher", final_url, raw, [])

def write_outputs(out: Path, pubs: list[Publication], candidates: list[dict[str, Any]], failures: list[dict[str, str]], before: dict[Path, str]) -> None:
    out.mkdir(parents=True, exist_ok=True); (out / "abstracts").mkdir(exist_ok=True)
    with (out / "abstract_candidates_review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS); w.writeheader()
        for c in candidates:
            w.writerow({**{k: c.get(k, "") for k in CSV_FIELDS}, "candidate_abstract": c.get("cleaned_abstract", ""), "decision": "", "replacement_abstract": "", "reviewer_notes": ""})
    (out / "abstract_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "failed_records.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FAILED_FIELDS); w.writeheader(); w.writerows(failures)
    for c in candidates:
        (out / "abstracts" / f"{c['stable_id']}.md").write_text(f"# {c['stable_id']}\n\nDOI: {c['doi']}\n\nSource: {c['abstract_source']}\n\nConfidence: {c['confidence']}\n\n## Abstract\n\n{c['cleaned_abstract']}\n", encoding="utf-8")
    counts = {name: sum(1 for c in candidates if c.get("abstract_source") == name) for name in ["crossref", "datacite", "publisher"]}
    conf = {name: sum(1 for c in candidates if c.get("confidence") == name) for name in ["high", "medium", "low", "rejected"]}
    modified = sum(1 for p, h in before.items() if p.exists() and sha256(p) != h)
    summary = ["# Publication Abstract Candidate Collection Summary", "", f"- Publications processed: {len(pubs)}", f"- Publications with DOI: {sum(1 for p in pubs if p.doi)}", f"- Publications without DOI: {sum(1 for p in pubs if not p.doi)}", f"- Crossref successes: {counts['crossref']}", f"- DataCite successes: {counts['datacite']}", f"- Publisher successes: {counts['publisher']}", f"- Abstract candidates obtained: {len(candidates)}", f"- High confidence: {conf['high']}", f"- Medium confidence: {conf['medium']}", f"- Low confidence: {conf['low']}", f"- Rejected: {conf['rejected']}", f"- Failed records: {len(failures)}", f"- Publication source files modified: {modified}"]
    (out / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (out / "review_instructions.md").write_text("# Publication Abstract 人工审核说明\n\n1. 打开 `abstract_candidates_review.csv`。\n2. 逐条比较标题、DOI 和 Abstract。\n3. 在 `decision` 列填写 `approve` 或 `reject`。\n4. 不要修改 `stable_id`、`doi` 和 `local_title`。\n5. `replacement_abstract` 仅用于人工修正明显的编码或排版问题。\n6. 保存为 UTF-8 CSV。\n7. 将审核后的 CSV 交给 Codex 执行导入。\n", encoding="utf-8")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--stable-id", default="")
    ap.add_argument("--include-publisher-pages", action="store_true")
    ap.add_argument("--delay-seconds", type=float, default=1.0)
    args = ap.parse_args()
    ua = os.environ.get("METADATA_USER_AGENT", "wangzhan0415.github.io abstract candidate collector")
    pubs = [p for p in read_publications() if not args.stable_id or p.stable_id == args.stable_id]
    before = {p.path: sha256(p.path) for p in pubs}
    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for pub in pubs:
        if not pub.doi:
            failures.append({"stable_id": pub.stable_id, "doi": "", "local_title": pub.title, "reason": "no_doi_manual_source_required", "detail": ""}); continue
        errors: list[str] = []
        for func in (crossref, datacite):
            try:
                result = func(pub, ua, args.delay_seconds)
                if result:
                    candidates.append(result); break
            except RuntimeError as exc:
                errors.append(f"{func.__name__}:{exc}")
        else:
            if args.include_publisher_pages:
                try:
                    result = publisher(pub, ua, args.delay_seconds)
                    if result:
                        candidates.append(result); continue
                except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
                    errors.append(f"publisher:{exc.__class__.__name__}")
            failures.append({"stable_id": pub.stable_id, "doi": pub.doi, "local_title": pub.title, "reason": "no_abstract_candidate", "detail": "; ".join(errors)})
    write_outputs(Path(args.output_dir), pubs, candidates, failures, before)
    return 0

if __name__ == "__main__":
    sys.exit(main())
