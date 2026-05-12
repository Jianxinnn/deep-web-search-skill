from __future__ import annotations

import concurrent.futures
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from .models import DEFAULT_WORKERS, QueryRecord, SourceRecord, now_iso, parse_year, slug, stable_id
from .net import fetch_json, fetch_text, post_json


PROVIDER_RATE_LIMIT_SECONDS = {"semantic_scholar": 1.0}
PROVIDER_RATE_LOCK = threading.Lock()
PROVIDER_NEXT_ALLOWED_AT: dict[str, float] = {}


def search_arxiv(query: str, limit: int) -> list[SourceRecord]:
    params = urllib.parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    text = fetch_text(f"https://export.arxiv.org/api/query?{params}")
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    rows: list[SourceRecord] = []
    for entry in root.findall("atom:entry", ns):
        url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        authors = [
            " ".join((author.findtext("atom:name", default="", namespaces=ns) or "").split())
            for author in entry.findall("atom:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
        arxiv_id = url.rsplit("/", 1)[-1] if url else ""
        rows.append(
            SourceRecord(
                source_id=stable_id("src", url or title),
                title=title,
                provider="arxiv",
                url=url,
                abstract=abstract,
                authors=[name for name in authors if name],
                year=parse_year(entry.findtext("atom:published", default="", namespaces=ns) or ""),
                venue="arXiv",
                arxiv_id=arxiv_id,
                pdf_url=pdf_url,
            )
        )
    return rows


def uninvert_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((int(pos), word))
    return " ".join(word for _, word in sorted(words))


def search_openalex(query: str, limit: int) -> list[SourceRecord]:
    params: dict[str, Any] = {"search": query, "per-page": limit, "sort": "relevance_score:desc"}
    email = os.getenv("OPENALEX_EMAIL", "").strip()
    if email:
        params["mailto"] = email
    payload = fetch_json(f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}")
    rows: list[SourceRecord] = []
    for item in payload.get("results", []):
        title = item.get("display_name") or ""
        url = item.get("doi") or item.get("id") or ""
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        authors = [
            (((authorship.get("author") or {}).get("display_name")) or "")
            for authorship in item.get("authorships", [])
        ]
        rows.append(
            SourceRecord(
                source_id=stable_id("src", url or title),
                title=title,
                provider="openalex",
                url=url,
                abstract=uninvert_abstract(item.get("abstract_inverted_index")),
                authors=[name for name in authors if name],
                year=item.get("publication_year"),
                venue=source.get("display_name") or "",
                doi=(item.get("doi") or "").replace("https://doi.org/", ""),
                openalex_id=item.get("id") or "",
                pdf_url=((location.get("pdf_url") or "") if isinstance(location, dict) else ""),
                citation_count=item.get("cited_by_count"),
            )
        )
    return rows


def search_tavily(query: str, limit: int) -> list[SourceRecord]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Tavily requires TAVILY_API_KEY")
    endpoint = os.getenv("TAVILY_BASE_URL", "").strip() or "https://api.tavily.com/search"
    payload = post_json(
        endpoint,
        {
            "api_key": key,
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "use_cache": True,
        },
    )
    rows: list[SourceRecord] = []
    for item in (payload or {}).get("results", []):
        url = item.get("url", "")
        title = item.get("title") or url
        snippet = item.get("content") or ""
        rows.append(
            SourceRecord(
                source_id=stable_id("src", f"tavily:{url or title}"),
                title=title,
                provider="tavily",
                source_type="web",
                url=url,
                snippet=snippet,
            )
        )
    return rows


def search_semantic_scholar(query: str, limit: int) -> list[SourceRecord]:
    fields = ",".join(
        [
            "paperId",
            "url",
            "title",
            "abstract",
            "authors",
            "year",
            "venue",
            "citationCount",
            "openAccessPdf",
            "externalIds",
            "fieldsOfStudy",
            "tldr",
        ]
    )
    params = urllib.parse.urlencode({"query": query, "limit": min(limit, 100), "fields": fields})
    headers = {}
    key = os.getenv("S2_API_KEY", os.getenv("Semantic_Search_API_KEY", "")).strip()
    if key:
        headers["x-api-key"] = key
    payload = fetch_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{params}", headers=headers)
    rows: list[SourceRecord] = []
    for paper in (payload or {}).get("data", []):
        ext = paper.get("externalIds") or {}
        pdf = paper.get("openAccessPdf") or {}
        tldr = paper.get("tldr") or {}
        title = paper.get("title") or ""
        paper_id = paper.get("paperId") or ""
        authors = [author.get("name", "") for author in paper.get("authors", []) if author.get("name")]
        rows.append(
            SourceRecord(
                source_id=stable_id("src", f"s2:{paper_id}:{ext.get('DOI', '')}:{title}"),
                title=title,
                provider="semantic_scholar",
                url=paper.get("url") or "",
                abstract=paper.get("abstract") or "",
                snippet=(tldr.get("text") if isinstance(tldr, dict) else "") or "",
                authors=authors,
                year=paper.get("year"),
                venue=paper.get("venue") or "",
                doi=ext.get("DOI", ""),
                arxiv_id=ext.get("ArXiv", ""),
                pubmed_id=ext.get("PubMed", ""),
                semantic_scholar_id=paper_id,
                pdf_url=(pdf.get("url") if isinstance(pdf, dict) else "") or "",
                citation_count=paper.get("citationCount"),
                fields=list(paper.get("fieldsOfStudy") or []),
            )
        )
    return rows


def xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(text.strip() for text in element.itertext() if text and text.strip())


def parse_pubmed_articles(xml_text_value: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text_value)
    articles: list[dict[str, Any]] = []
    for pubmed_article in root.findall("./PubmedArticle"):
        article = pubmed_article.find(".//Article")
        if article is None:
            continue
        abstract_parts = []
        for part in article.findall(".//Abstract/AbstractText"):
            label = part.attrib.get("Label")
            text = xml_text(part)
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        authors = []
        for author in article.findall(".//Author"):
            first = xml_text(author.find("./ForeName"))
            last = xml_text(author.find("./LastName"))
            name = " ".join(part for part in [first, last] if part)
            if name:
                authors.append(name)
        doi = ""
        for article_id in pubmed_article.findall(".//ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = xml_text(article_id)
                break
        articles.append(
            {
                "pmid": xml_text(pubmed_article.find(".//PMID")),
                "title": xml_text(article.find(".//ArticleTitle")),
                "abstract": " ".join(abstract_parts),
                "authors": authors,
                "year": parse_year(xml_text(article.find(".//Journal/JournalIssue/PubDate/Year"))),
                "venue": xml_text(article.find(".//Journal/Title")),
                "doi": doi,
            }
        )
    return articles


def search_pubmed(query: str, limit: int) -> list[SourceRecord]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    params: dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": min(limit, 100),
        "retmode": "json",
        "sort": "relevance",
        "tool": "DeepWebSearchSkill",
    }
    email = os.getenv("NCBI_EMAIL", "").strip()
    key = os.getenv("NCBI_API_KEY", "").strip()
    if email:
        params["email"] = email
    if key:
        params["api_key"] = key
    search_payload = fetch_json(f"{base}/esearch.fcgi?{urllib.parse.urlencode(params)}")
    ids = search_payload.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "tool": "DeepWebSearchSkill",
    }
    if email:
        fetch_params["email"] = email
    if key:
        fetch_params["api_key"] = key
    articles = parse_pubmed_articles(fetch_text(f"{base}/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"))
    rows: list[SourceRecord] = []
    for article in articles:
        pmid = article.get("pmid", "")
        title = article.get("title", "")
        rows.append(
            SourceRecord(
                source_id=stable_id("src", f"pubmed:{pmid}:{article.get('doi', '')}:{title}"),
                title=title,
                provider="pubmed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                abstract=article.get("abstract", ""),
                authors=list(article.get("authors") or []),
                year=article.get("year"),
                venue=article.get("venue", ""),
                doi=article.get("doi", ""),
                pubmed_id=pmid,
                fields=["Medicine", "Biology"],
            )
        )
    return rows


SEARCHERS = {
    "tavily": search_tavily,
    "semantic_scholar": search_semantic_scholar,
    "pubmed": search_pubmed,
    "arxiv": search_arxiv,
    "openalex": search_openalex,
}


def wait_for_provider_rate_limit(provider: str) -> None:
    interval = PROVIDER_RATE_LIMIT_SECONDS.get(provider, 0.0)
    if interval <= 0:
        return
    with PROVIDER_RATE_LOCK:
        now = time.monotonic()
        wait_seconds = PROVIDER_NEXT_ALLOWED_AT.get(provider, now) - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        PROVIDER_NEXT_ALLOWED_AT[provider] = now + interval


def provider_search(provider: str, query: QueryRecord, limit: int) -> tuple[list[SourceRecord], dict[str, Any]]:
    started = time.time()
    if provider not in SEARCHERS:
        raise ValueError(f"unsupported provider: {provider}")
    wait_for_provider_rate_limit(provider)
    rows = SEARCHERS[provider](query.query, limit)
    return rows, {
        "timestamp": now_iso(),
        "provider": provider,
        "query": query.query,
        "status": "ok",
        "result_count": len(rows),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def provider_error(provider: str, query: QueryRecord, exc: Exception) -> dict[str, Any]:
    return {
        "timestamp": now_iso(),
        "provider": provider,
        "query": query.query,
        "status": "error",
        "error": str(exc),
    }


PROVIDER_EXCEPTIONS = (urllib.error.URLError, TimeoutError, socket.timeout, RuntimeError, ValueError, json.JSONDecodeError, ET.ParseError)


def provider_task(index: int, provider: str, query: QueryRecord, limit: int) -> tuple[int, list[SourceRecord], dict[str, Any]]:
    try:
        rows, event = provider_search(provider, query, limit)
        return index, rows, event
    except PROVIDER_EXCEPTIONS as exc:
        return index, [], provider_error(provider, query, exc)


def run_provider_queries(queries: list[QueryRecord], providers: list[str], limit: int, workers: int = DEFAULT_WORKERS) -> tuple[list[SourceRecord], list[dict[str, Any]]]:
    tasks: list[tuple[int, str, QueryRecord]] = []
    for query in queries:
        for provider in providers:
            tasks.append((len(tasks), provider, query))
    if not tasks:
        return [], []

    worker_count = max(1, min(workers, len(tasks)))
    if worker_count == 1:
        results = [provider_task(index, provider, query, limit) for index, provider, query in tasks]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(provider_task, index, provider, query, limit) for index, provider, query in tasks]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

    sources: list[SourceRecord] = []
    provenance: list[dict[str, Any]] = []
    for _, rows, event in sorted(results, key=lambda item: item[0]):
        sources.extend(rows)
        provenance.append(event)
    return sources, provenance
