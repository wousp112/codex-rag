from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


_REF_HEADING_RE = re.compile(
    r"(?im)^\s{0,3}(#{1,6}\s*)?(references|bibliography)\s*$"
)


def split_body_and_references(md: str) -> Tuple[str, str]:
    """
    Split a markdown draft into (body, references_section).
    If no heading is found, returns (md, '').
    """
    m = _REF_HEADING_RE.search(md)
    if not m:
        return md, ""
    return md[: m.start()], md[m.start() :]


_PAREN_WITH_YEAR_RE = re.compile(r"\(([^()\n]*?\b(?:19|20)\d{2}[a-z]?\b[^()\n]*?)\)")
_NARRATIVE_RE = re.compile(
    r"(?P<authors>[A-Z][A-Za-z'’\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’\-]+)*)\s*\((?P<year>(?:19|20)\d{2}[a-z]?)\)"
)


def _looks_like_citation_chunk(s: str) -> bool:
    # Heuristic: has a 4-digit year and at least one letter.
    return bool(re.search(r"\b(?:19|20)\d{2}[a-z]?\b", s)) and bool(re.search(r"[A-Za-z]", s))


def iter_parenthetical_citations(text: str) -> Iterable[Tuple[int, int, str, str]]:
    """
    Yield (start, end, full_match, inner_text) for (...) blocks that look like citations.
    """
    for m in _PAREN_WITH_YEAR_RE.finditer(text):
        inner = m.group(1).strip()
        if not _looks_like_citation_chunk(inner):
            continue
        yield m.start(), m.end(), m.group(0), inner


def iter_narrative_citations(text: str) -> Iterable[Tuple[int, int, str, str]]:
    """
    Yield (start, end, full_match, normalized_query) for narrative citations like 'Smith (2019)'.
    """
    for m in _NARRATIVE_RE.finditer(text):
        authors = m.group("authors").strip()
        year = m.group("year").strip()
        yield m.start(), m.end(), m.group(0), f"{authors} {year}"


_SPLIT_MULTI_CITES_RE = re.compile(r"\s*;\s*")
_YEAR_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2}[a-z]?)\b")


def extract_citation_queries_from_parenthetical(inner_text: str) -> List[str]:
    """
    Turn '(Author, 2019; Other, 2020)' inner text into a list of query strings.
    """
    parts = [p.strip() for p in _SPLIT_MULTI_CITES_RE.split(inner_text) if p.strip()]
    queries: List[str] = []
    for part in parts:
        if not _looks_like_citation_chunk(part):
            continue
        # Remove common lead-ins.
        cleaned = re.sub(r"(?i)^\s*(e\.g\.|eg|i\.e\.|ie|see|cf\.|compare|for example)\s*", "", part).strip()
        ym = _YEAR_RE.search(cleaned)
        if not ym:
            continue
        year = ym.group("year")
        authors_raw = cleaned[: ym.start()].strip().strip(",;:")
        authors_raw = re.sub(r"\s+", " ", authors_raw)
        # Strip trailing 'et al.' noise for query stability.
        authors = re.sub(r"(?i)\bet\s+al\.?\b", "et al", authors_raw).strip()
        if not authors:
            queries.append(year)
        else:
            queries.append(f"{authors} {year}")
    # Dedup while preserving order.
    seen = set()
    out: List[str] = []
    for q in queries:
        qn = q.strip()
        if not qn or qn in seen:
            continue
        seen.add(qn)
        out.append(qn)
    return out


@dataclass(frozen=True)
class AlignmentHit:
    query: str
    doc_uid: str
    snippet: str
    score: Optional[float] = None


def choose_best_doc_uid(records: List[dict]) -> Optional[AlignmentHit]:
    if not records:
        return None
    r0 = records[0]
    score = None
    for key in ("_distance", "distance", "_score", "score"):
        if key in r0:
            try:
                score = float(r0[key])
            except Exception:
                score = None
            break
    snippet = str(r0.get("text", "")).strip().replace("\n", " ")
    if len(snippet) > 220:
        snippet = snippet[:220] + "…"
    doc_uid = r0.get("doc_uid")
    if not doc_uid:
        return None
    return AlignmentHit(query=str(r0.get("query", "")) or "", doc_uid=str(doc_uid), snippet=snippet, score=score)

