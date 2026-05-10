"""effectiveness.py — Practical document effectiveness scoring.

Parallel to the parse-syntax score, this measures whether a document
would survive scrutiny from a judge, mediator, or opposing counsel
who reads it cold.

Dimensions:
  1. CITATION DENSITY    — are claims sourced?
  2. FACTUAL DENSITY     — ratio of nouns/facts to filler
  3. SPECIFICITY         — dates, amounts, names present?
  4. COMPLETENESS        — does it identify parties, case, relief?
  5. STAND-ALONE         — can a stranger follow it without context?
  6. STRUCTURAL CLARITY  — sections, headings, logical flow?

Returns both a score (0-100) and a detailed breakdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass
class EffectivenessScore:
    """Multi-dimensional effectiveness assessment."""
    # Overall
    total: int = 0       # 0-100
    grade: str = "?"

    # Dimensions (each 0-100)
    citation: int = 0
    factual: int = 0
    specificity: int = 0
    completeness: int = 0
    standalone: int = 0
    clarity: int = 0

    # Raw metrics
    total_claims: int = 0
    cited_claims: int = 0
    uncited_claims: int = 0
    date_count: int = 0
    amount_count: int = 0
    name_count: int = 0
    has_case_number: bool = False
    has_parties: bool = False
    has_date: bool = False
    has_relief_requested: bool = False
    section_count: int = 0
    word_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def score_effectiveness(text: str, original_text: str = "") -> EffectivenessScore:
    """Score a document's practical effectiveness.

    Args:
        text: The document to score
        original_text: The original (pre-revision) for comparison
    """
    s = EffectivenessScore()
    s.word_count = len(text.split())

    # ── 1. CITATION DENSITY ───────────────────────────────────────
    # Count factual claims (sentences with assertions)
    sentences = [sent.strip() for sent in re.split(r'[.!?\n]', text) if len(sent.strip()) > 20]
    s.total_claims = len(sentences)

    # Count cited claims (has a source reference, date, or exhibit)
    cite_patterns = [
        r'\(Source:',           # Our citation format
        r'Exhibit\s+[A-Z0-9]', # Exhibit references
        r'filed\s+(?:on\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+',
        r'dated\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)',
        r'docket\s+(?:entry|number|no)',
        r'pursuant\s+to\s+(?:Rule|Section|§)',
        r'\d{4}\s*D\s*\d{4}',  # Case numbers
    ]
    cited = 0
    for sent in sentences:
        if any(re.search(p, sent, re.I) for p in cite_patterns):
            cited += 1
    s.cited_claims = cited

    # Uncited = has [CITE NEEDED] or [NO EVIDENCE]
    s.uncited_claims = text.count("[CITE NEEDED") + text.count("[NO EVIDENCE")

    # Score: % of claims that are cited (penalize uncited markers)
    if s.total_claims > 0:
        cite_ratio = s.cited_claims / s.total_claims
        uncite_penalty = min(0.3, s.uncited_claims * 0.02)
        s.citation = max(0, min(100, int((cite_ratio - uncite_penalty) * 100)))
    else:
        s.citation = 0

    # ── 2. FACTUAL DENSITY ────────────────────────────────────────
    # Noun/fact ratio vs filler words
    words = text.split()
    total_words = len(words)
    # Simple heuristic: words that carry information
    filler = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
              'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
              'shall', 'would', 'could', 'should', 'may', 'might', 'can',
              'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
              'that', 'this', 'it', 'its', 'and', 'or', 'but', 'not', 'no',
              'if', 'then', 'than', 'so', 'as', 'up', 'out', 'about'}
    content_words = sum(1 for w in words if w.lower().strip('.,;:()[]') not in filler and len(w) > 2)
    if total_words > 0:
        s.factual = min(100, int((content_words / total_words) * 150))  # Scale so 66% content = 100

    # ── 3. SPECIFICITY ────────────────────────────────────────────
    # Dates
    s.date_count = len(re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}|'
        r'\d{1,2}/\d{1,2}/\d{4}|'
        r'\b20\d{2}-\d{2}-\d{2}\b|'
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b',
        text, re.I
    ))
    # Dollar amounts
    s.amount_count = len(re.findall(r'\$[\d,]+(?:\.\d{2})?', text))
    # Named parties
    s.name_count = len(re.findall(
        r'\b(?:Joel\s+Thorarinson|Heather\s+(?:Kim\s+)?Atagan|'
        r'Tarara|Fitzpatrick|Conniff|Jannusch)\b', text, re.I
    ))

    # Score: more specifics = higher score
    spec_score = 0
    spec_score += min(30, s.date_count * 5)      # Up to 30 for dates
    spec_score += min(30, s.amount_count * 3)    # Up to 30 for amounts
    spec_score += min(20, s.name_count * 4)      # Up to 20 for names
    spec_score += min(20, len(re.findall(r'\b\d{4,}\b', text)) * 2)  # Account numbers etc
    s.specificity = min(100, spec_score)

    # ── 4. COMPLETENESS ───────────────────────────────────────────
    # Does it have the essential elements?
    s.has_case_number = bool(re.search(r'\b\d{4}\s*D\s*\d{4}\b', text))
    s.has_parties = bool(re.search(r'(?:Petitioner|Respondent|Plaintiff|Defendant)', text, re.I))
    s.has_date = bool(re.search(r'(?:DATE|Date).*\d|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d', text, re.I))
    s.has_relief_requested = bool(re.search(
        r'(?:request|demand|propose|seek|ask|pray)(?:s|ing|ed)?.*(?:court|order|relief|judgment|resolution|settlement)',
        text, re.I
    ))
    has_signature = bool(re.search(r'(?:Pro Se|Respectfully|Sincerely|Joel Thorarinson)', text))
    has_subject = bool(re.search(r'(?:Subject|RE:|Re:)', text, re.I))

    comp_score = 0
    comp_score += 20 if s.has_case_number else 0
    comp_score += 20 if s.has_parties else 0
    comp_score += 15 if s.has_date else 0
    comp_score += 20 if s.has_relief_requested else 0
    comp_score += 15 if has_signature else 0
    comp_score += 10 if has_subject else 0
    s.completeness = comp_score

    # ── 5. STAND-ALONE ────────────────────────────────────────────
    # Can a stranger follow without context?
    # Penalize: pronouns without antecedents, assumed knowledge
    standalone_score = 100
    # Penalty for "your client" without naming them first
    if re.search(r'your client', text[:200], re.I) and not re.search(r'(?:Heather|Atagan)', text[:300], re.I):
        standalone_score -= 20
    # Penalty for [CITE NEEDED] markers (reader can't verify)
    standalone_score -= min(40, s.uncited_claims * 3)
    # Penalty for undefined abbreviations
    undefined_abbrevs = len(re.findall(r'\b[A-Z]{3,}\b', text[:500])) - len(re.findall(r'\b(?:IRMO|OFW|RE|PRO|SE)\b', text[:500]))
    standalone_score -= min(20, max(0, undefined_abbrevs) * 3)
    # Bonus for explicit definitions
    if re.search(r'(?:Case No\.|Case Number|In re|In the matter)', text[:500], re.I):
        standalone_score += 10
    s.standalone = max(0, min(100, standalone_score))

    # ── 6. STRUCTURAL CLARITY ─────────────────────────────────────
    # Headings, sections, logical organization
    s.section_count = len(re.findall(r'^#{1,3}\s+|^[IVX]+\.\s+|^\*\*[A-Z]', text, re.M))
    has_numbered_list = bool(re.search(r'^\s*\d+\.\s', text, re.M))
    has_bullet_list = bool(re.search(r'^\s*[-•]\s', text, re.M))
    avg_para_length = _avg_paragraph_length(text)

    clarity_score = 0
    clarity_score += min(30, s.section_count * 6)   # Sections
    clarity_score += 15 if has_numbered_list else 0  # Lists
    clarity_score += 10 if has_bullet_list else 0
    # Paragraphs: penalize too long (>200 words) or too short (<20)
    if 40 <= avg_para_length <= 150:
        clarity_score += 25
    elif 20 <= avg_para_length <= 200:
        clarity_score += 15
    else:
        clarity_score += 5
    # Bonus for word count (substantive doc)
    if s.word_count >= 500:
        clarity_score += 20
    elif s.word_count >= 200:
        clarity_score += 10
    s.clarity = min(100, clarity_score)

    # ── TOTAL ─────────────────────────────────────────────────────
    # Weighted average
    weights = {
        'citation': 0.25,
        'specificity': 0.20,
        'completeness': 0.20,
        'standalone': 0.15,
        'clarity': 0.10,
        'factual': 0.10,
    }
    s.total = int(
        s.citation * weights['citation'] +
        s.specificity * weights['specificity'] +
        s.completeness * weights['completeness'] +
        s.standalone * weights['standalone'] +
        s.clarity * weights['clarity'] +
        s.factual * weights['factual']
    )

    # Grade
    if s.total >= 85:
        s.grade = "A"
    elif s.total >= 70:
        s.grade = "B"
    elif s.total >= 55:
        s.grade = "C"
    elif s.total >= 40:
        s.grade = "D"
    else:
        s.grade = "F"

    return s


def _avg_paragraph_length(text: str) -> int:
    """Average paragraph length in words."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        return 0
    return sum(len(p.split()) for p in paras) // len(paras)


def format_effectiveness(score: EffectivenessScore, label: str = "") -> str:
    """Format effectiveness score for terminal display."""
    lines = []
    if label:
        lines.append(f"  {label}")

    # Grade bar
    gc = "\033[32m" if score.grade in ("A", "B") else "\033[33m" if score.grade == "C" else "\033[31m"
    lines.append(f"  {gc}EFFECTIVENESS: {score.total}/100 ({score.grade})\033[0m")
    lines.append("")

    # Dimension bars
    dims = [
        ("Citation", score.citation, f"{score.cited_claims} cited / {score.uncited_claims} uncited"),
        ("Specificity", score.specificity, f"{score.date_count} dates, {score.amount_count} amounts, {score.name_count} names"),
        ("Completeness", score.completeness, _completeness_detail(score)),
        ("Stand-alone", score.standalone, f"{score.uncited_claims} unverifiable claims"),
        ("Clarity", score.clarity, f"{score.section_count} sections, {score.word_count} words"),
        ("Factual", score.factual, "content word density"),
    ]

    for name, val, detail in dims:
        bar = _bar(val)
        vc = "\033[32m" if val >= 70 else "\033[33m" if val >= 40 else "\033[31m"
        lines.append(f"    {name:<14} {vc}{bar} {val:>3}\033[0m  \033[90m{detail}\033[0m")

    return "\n".join(lines)


def _bar(val: int, width: int = 20) -> str:
    """Simple bar chart."""
    filled = int(val / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _completeness_detail(score: EffectivenessScore) -> str:
    parts = []
    if score.has_case_number:
        parts.append("case#")
    if score.has_parties:
        parts.append("parties")
    if score.has_date:
        parts.append("date")
    if score.has_relief_requested:
        parts.append("relief")
    missing = []
    if not score.has_case_number:
        missing.append("case#")
    if not score.has_parties:
        missing.append("parties")
    if not score.has_relief_requested:
        missing.append("relief")
    result = "✓ " + ", ".join(parts) if parts else ""
    if missing:
        result += (" | " if result else "") + "missing: " + ", ".join(missing)
    return result
