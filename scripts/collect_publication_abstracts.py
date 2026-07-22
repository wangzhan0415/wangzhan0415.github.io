#!/usr/bin/env python3
"""Collect publication abstract candidates for manual review.

The collector only reads HugoBlox publication markdown files and writes review
artifacts outside content/publication. It never edits publication sources.
"""

import argparse
import csv
import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib import error, parse, request

TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
CSV_FIELDS = [
    "stable_id",
    "doi",
    "local_title",
    "local_year",
    "publication",
    "candidate_title",
    "candidate_year",
    "abstract_source",
    "abstract_source_url",
    "retrieved_at",
    "doi_match",
    "title_match",
    "year_match",
    "confidence",
    "candidate_abstract",
    "review_notes",
]
FAILED_FIELDS = [
    "stable_id",
    "doi",
    "local_title",
    "local_year",
    "publication",
    "reason",
    "source_attempted",
    "retrieved_at",
    "details",
]


class MetadataHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = []
        self.json_ld = []
        self._in_json_ld = False
        self._script = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k and v is not None}
        if tag.lower() == "meta":
            self.meta.append(attrs_dict)
        if tag.lower() == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._script = []

    def handle_data(self, data):
        if self._in_json_ld:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script))
            self._in_json_ld = False
            self._script = []


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_scalar(value):
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        value = value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return value.strip("[] ").replace('"', "").replace("'", "")
    return value


def read_publication(path):
    text = path.read_text(encoding="utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else text
    data = {}
    for line in front.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"title", "doi", "date", "publication", "publication_types", "publication_type"}:
            data[key] = parse_scalar(value)
    date = data.get("date", "")
    year_match = re.search(r"(19|20)\d{2}", date)
    title = data.get("title", "")
    stable_id = path.parent.name
    return {
        "stable_id": stable_id,
        "title": title,
        "doi": normalize_doi(data.get("doi", "")),
        "display_year": year_match.group(0) if year_match else "",
        "date": date,
        "publication": data.get("publication", ""),
        "publication_type": data.get("publication_types") or data.get("publication_type", ""),
        "path": path,
    }


def normalize_doi(doi):
    doi = html.unescape(str(doi or "")).strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    return doi.strip().lower()


def normalize_title(title):
    title = unicodedata.normalize("NFKD", html.unescape(title or "")).lower()
    title = re.sub(r"[\W_]+", " ", title, flags=re.UNICODE)
    return re.sub(r"\s+", " ", title).strip()


def clean_abstract(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    return value.strip()


def request_json(url, user_agent, delay):
    text, final_url = request_text(url, user_agent, delay, accept="application/json")
    return json.loads(text), final_url


def request_text(url, user_agent, delay, accept="text/html,application/json"):
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        if delay:
            time.sleep(delay)
        try:
            req = request.Request(url, headers={"User-Agent": user_agent, "Accept": accept})
            with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace"), response.geturl()
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt == MAX_RETRIES:
                raise
    raise last


def crossref(record, user_agent, mailto, delay):
    doi = parse.quote(record["doi"], safe="")
    url = f"https://api.crossref.org/works/{doi}"
    if mailto:
        url += "?mailto=" + parse.quote(mailto)
    payload, final_url = request_json(url, user_agent, delay)
    msg = payload.get("message", {})
    abstract = msg.get("abstract", "")
    titles = msg.get("title") or []
    years = (((msg.get("published-print") or msg.get("published-online") or msg.get("issued") or {}).get("date-parts") or [[""]])[0])
    return build_candidate(record, titles[0] if titles else "", str(years[0]) if years else "", abstract, "Crossref", final_url)


def datacite(record, user_agent, delay):
    doi = parse.quote(record["doi"], safe="")
    url = f"https://api.datacite.org/dois/{doi}"
    payload, final_url = request_json(url, user_agent, delay)
    attrs = payload.get("data", {}).get("attributes", {})
    descriptions = attrs.get("descriptions") or []
    abstract = ""
    for item in descriptions:
        if item.get("descriptionType", "").lower() == "abstract":
            abstract = item.get("description", "")
            break
    return build_candidate(record, attrs.get("title", ""), str(attrs.get("publicationYear", "")), abstract, "DataCite", final_url)


def publisher(record, user_agent, delay):
    url = "https://doi.org/" + parse.quote(record["doi"], safe="/")
    text, final_url = request_text(url, user_agent, delay, accept="text/html")
    parser = MetadataHTMLParser()
    parser.feed(text[:1000000])
    title = ""
    abstract = ""
    keywords = ""
    for meta in parser.meta:
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = meta.get("content", "")
        if name in {"citation_title", "dc.title", "dc.title"} and not title:
            title = content
        if name in {"citation_abstract", "dc.description"} and not abstract:
            abstract = content
        if name in {"keywords", "citation_keywords"} and not keywords:
            keywords = content
    for raw in parser.json_ld:
        try:
            nodes = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(nodes, dict):
            nodes = [nodes]
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict):
                title = title or str(node.get("name", ""))
                abstract = abstract or str(node.get("description", ""))
                kw = node.get("keywords", "")
                keywords = keywords or (", ".join(kw) if isinstance(kw, list) else str(kw))
    if not abstract and keywords:
        abstract = "Keywords: " + keywords
    return build_candidate(record, title, "", abstract, "publisher_page", final_url)


def build_candidate(record, candidate_title, candidate_year, raw_abstract, source, source_url):
    cleaned = clean_abstract(raw_abstract)
    title_match = normalize_title(record["title"]) == normalize_title(candidate_title)
    year_match = bool(candidate_year) and bool(record["display_year"]) and str(candidate_year) == str(record["display_year"])
    doi_match = True
    confidence = "rejected"
    if cleaned and doi_match and title_match and year_match:
        confidence = "high"
    elif cleaned and doi_match and title_match:
        confidence = "medium"
    elif cleaned and doi_match:
        confidence = "low"
    errors = [] if cleaned else ["no_abstract"]
    return {
        "stable_id": record["stable_id"],
        "doi": record["doi"],
        "local_title": record["title"],
        "local_year": record["display_year"],
        "publication": record["publication"],
        "candidate_title": candidate_title,
        "candidate_year": candidate_year,
        "raw_abstract": raw_abstract or "",
        "cleaned_abstract": cleaned,
        "abstract_source": source,
        "abstract_source_url": source_url,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "doi_match": doi_match,
        "title_match": "normalized" if title_match else "mismatch",
        "year_match": year_match,
        "confidence": confidence,
        "errors": errors,
    }


def write_outputs(out, candidates, failures, stats, modified_count):
    out.mkdir(parents=True, exist_ok=True)
    candidates_dir = out / "candidates"
    candidates_dir.mkdir(exist_ok=True)
    with (out / "abstract_candidates_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for c in candidates:
            writer.writerow({**{k: c.get(k, "") for k in CSV_FIELDS}, "candidate_abstract": c.get("cleaned_abstract", ""), "review_notes": ""})
    (out / "abstract_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "failed_records.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FAILED_FIELDS)
        writer.writeheader()
        writer.writerows(failures)
    for c in candidates:
        (candidates_dir / f"{c['stable_id']}.md").write_text(f"# {c['local_title']}\n\n- DOI: {c['doi']}\n- Source: {c['abstract_source']}\n- Confidence: {c['confidence']}\n\n## Candidate Abstract\n\n{c['cleaned_abstract']}\n", encoding="utf-8")
    lines = [
        "# Publication Abstract 候选采集汇总",
        "",
        f"- Publication总数：{stats['total']}",
        f"- 有DOI数量：{stats['with_doi']}",
        f"- 无DOI数量：{stats['without_doi']}",
        f"- Crossref成功数量：{stats['Crossref']}",
        f"- DataCite成功数量：{stats['DataCite']}",
        f"- 官方出版社页面成功数量：{stats['publisher_page']}",
        f"- 获得Abstract数量：{len(candidates)}",
        f"- high confidence数量：{stats['high']}",
        f"- medium confidence数量：{stats['medium']}",
        f"- low confidence数量：{stats['low']}",
        f"- rejected数量：{stats['rejected']}",
        f"- 失败数量：{len(failures)}",
        f"- Publication source files modified: {modified_count}",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publication-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--delay-seconds", type=float, default=1.5)
    parser.add_argument("--include-publisher-pages", action="store_true")
    args = parser.parse_args()
    pub_paths = sorted(Path(args.publication_dir).glob("*/index.md"))
    before = {p: sha256_file(p) for p in pub_paths}
    records = [read_publication(p) for p in pub_paths]
    user_agent = "wangzhan0415.github.io abstract collector"
    user_agent = getattr(request, "os").environ.get("METADATA_USER_AGENT", user_agent)
    mailto = getattr(request, "os").environ.get("CROSSREF_MAILTO", "")
    candidates, failures = [], []
    stats = {"total": len(records), "with_doi": 0, "without_doi": 0, "Crossref": 0, "DataCite": 0, "publisher_page": 0, "high": 0, "medium": 0, "low": 0, "rejected": 0}
    for record in records:
        if not record["doi"]:
            stats["without_doi"] += 1
            failures.append({"stable_id": record["stable_id"], "doi": "", "local_title": record["title"], "local_year": record["display_year"], "publication": record["publication"], "reason": "no_doi_manual_source_required", "source_attempted": "none", "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "details": ""})
            continue
        stats["with_doi"] += 1
        errors = []
        candidate = None
        for source_name, func in (("Crossref", crossref), ("DataCite", datacite)):
            try:
                candidate = func(record, user_agent, mailto, args.delay_seconds) if source_name == "Crossref" else func(record, user_agent, args.delay_seconds)
                if candidate["cleaned_abstract"] and candidate["confidence"] != "rejected":
                    break
                errors.extend(candidate.get("errors", []))
            except Exception as exc:  # collect error and continue batch
                errors.append(f"{source_name}: {type(exc).__name__}: {exc}")
                candidate = None
        if (not candidate or not candidate["cleaned_abstract"] or candidate["confidence"] == "rejected") and args.include_publisher_pages:
            try:
                candidate = publisher(record, user_agent, args.delay_seconds)
            except Exception as exc:
                errors.append(f"publisher_page: {type(exc).__name__}: {exc}")
        if candidate and candidate["cleaned_abstract"] and candidate["confidence"] != "rejected":
            candidates.append(candidate)
            stats[candidate["abstract_source"]] += 1
            stats[candidate["confidence"]] += 1
        else:
            failures.append({"stable_id": record["stable_id"], "doi": record["doi"], "local_title": record["title"], "local_year": record["display_year"], "publication": record["publication"], "reason": "no_approved_candidate", "source_attempted": "Crossref;DataCite;publisher_page", "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "details": "; ".join(errors)})
            if candidate:
                stats[candidate["confidence"]] += 1
    after = {p: sha256_file(p) for p in pub_paths}
    modified_count = sum(1 for p in pub_paths if before[p] != after[p])
    write_outputs(Path(args.output_dir), candidates, failures, stats, modified_count)
    if modified_count:
        raise SystemExit("Publication source files changed during collection")


if __name__ == "__main__":
    main()
