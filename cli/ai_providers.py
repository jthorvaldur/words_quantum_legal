"""ai_providers.py — Unified LLM provider abstraction for qwparse.

Discovers and queries models across:
  - Ollama (local, localhost:11434)
  - Anthropic (Claude family)
  - OpenAI (GPT family)
  - Google Gemini

Also provides vector DB search for citation filling.

All providers implement the same interface:
  list_models() -> list[ModelInfo]
  complete(model, system, user, max_tokens) -> str
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Model info
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    id: str               # e.g. "claude-sonnet-4-6", "gemma4:e4b"
    provider: str         # "ollama", "anthropic", "openai", "gemini"
    name: str             # human-friendly name
    size_gb: float = 0.0  # local model size (0 for API)
    context: int = 0      # context window tokens
    local: bool = False   # True if runs locally
    available: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Provider base
# ---------------------------------------------------------------------------

class Provider:
    name: str = ""

    def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 4096) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, host: str = "localhost", port: int = 11434):
        self.base = f"http://{host}:{port}"

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base}/api/tags", method="GET")
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False

    def list_models(self) -> list[ModelInfo]:
        try:
            req = urllib.request.Request(f"{self.base}/api/tags", method="GET")
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                # skip embedding models
                if "embed" in name.lower():
                    continue
                size = m.get("size", 0) / 1e9
                models.append(ModelInfo(
                    id=name,
                    provider="ollama",
                    name=name.split(":")[0],
                    size_gb=round(size, 1),
                    context=m.get("details", {}).get("context_length", 0),
                    local=True,
                ))
            return models
        except Exception:
            return []

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 4096) -> str:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(
            f"{self.base}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

ANTHROPIC_MODELS = [
    ModelInfo(id="claude-opus-4-6", provider="anthropic", name="Claude Opus 4.6", context=1_000_000),
    ModelInfo(id="claude-sonnet-4-6", provider="anthropic", name="Claude Sonnet 4.6", context=200_000),
    ModelInfo(id="claude-haiku-4-5-20251001", provider="anthropic", name="Claude Haiku 4.5", context=200_000),
]


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[ModelInfo]:
        if not self.api_key:
            return [ModelInfo(**{**asdict(m), "available": False}) for m in ANTHROPIC_MODELS]
        return [m for m in ANTHROPIC_MODELS]

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 4096) -> str:
        payload = json.dumps({
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

OPENAI_MODELS = [
    ModelInfo(id="gpt-4.1", provider="openai", name="GPT-4.1", context=1_000_000),
    ModelInfo(id="gpt-4.1-mini", provider="openai", name="GPT-4.1 Mini", context=1_000_000),
    ModelInfo(id="gpt-4.1-nano", provider="openai", name="GPT-4.1 Nano", context=1_000_000),
    ModelInfo(id="o3", provider="openai", name="o3", context=200_000),
    ModelInfo(id="o4-mini", provider="openai", name="o4-mini", context=200_000),
]


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[ModelInfo]:
        if not self.api_key:
            return [ModelInfo(**{**asdict(m), "available": False}) for m in OPENAI_MODELS]
        return [m for m in OPENAI_MODELS]

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 4096) -> str:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

GEMINI_MODELS = [
    ModelInfo(id="gemini-2.5-flash", provider="gemini", name="Gemini 2.5 Flash", context=1_000_000),
    ModelInfo(id="gemini-2.5-pro", provider="gemini", name="Gemini 2.5 Pro", context=1_000_000),
]


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[ModelInfo]:
        if not self.api_key:
            return [ModelInfo(**{**asdict(m), "available": False}) for m in GEMINI_MODELS]
        return [m for m in GEMINI_MODELS]

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 4096) -> str:
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }).encode()
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={self.api_key}")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)
        return ""


# ---------------------------------------------------------------------------
# Registry — discover all providers
# ---------------------------------------------------------------------------

ALL_PROVIDERS: list[Provider] = [
    OllamaProvider(),
    AnthropicProvider(),
    OpenAIProvider(),
    GeminiProvider(),
]

# Default model preference order (fast + cheap first for --ai default)
DEFAULT_MODEL_PREFERENCE = [
    "gemini-2.5-flash",        # free/cheap, fast, 1M context
    "claude-haiku-4-5-20251001",  # cheap, fast
    "gpt-4.1-mini",           # cheap, fast
    "qwen3.5:latest",         # local, free
    "gemma4:e4b",             # local, free
    "llama3.1:8b",            # local, free
    "claude-sonnet-4-6",      # mid-tier
    "gpt-4.1",               # mid-tier
    "gemini-2.5-pro",         # mid-tier
    "claude-opus-4-6",        # expensive
    "o3",                     # expensive
]


def discover_models() -> list[ModelInfo]:
    """Discover all available models across all providers."""
    all_models = []
    for provider in ALL_PROVIDERS:
        all_models.extend(provider.list_models())
    return all_models


def get_provider(model_id: str) -> Optional[Provider]:
    """Find the provider that serves a given model ID."""
    for provider in ALL_PROVIDERS:
        for m in provider.list_models():
            if m.id == model_id and m.available:
                return provider
    return None


def pick_default_model() -> Optional[str]:
    """Pick the best available model from preference list."""
    available = {m.id for m in discover_models() if m.available}
    for model_id in DEFAULT_MODEL_PREFERENCE:
        if model_id in available:
            return model_id
    return None


def complete(model_id: str, system: str, user: str,
             max_tokens: int = 4096) -> str:
    """Route a completion request to the right provider."""
    provider = get_provider(model_id)
    if not provider:
        raise ValueError(f"Model '{model_id}' not found or provider unavailable")
    return provider.complete(model_id, system, user, max_tokens)


# ---------------------------------------------------------------------------
# AI critique prompt for qwparse scan --ai
# ---------------------------------------------------------------------------

CRITIQUE_SYSTEM = """\
You are a legal document analyst specializing in structural language analysis.

You have received a structural analysis of a document from the qwparse tool,
which evaluates documents using the Quantum Verbal Meaning framework:
- VCC negation (vowel-consonant-consonant prefix = negation of root)
- C.S.S.C.P.S.G.P. sentence structure grading
- DOG-LATIN detection (unhyphenated all-caps as fraudulent typography)
- Null adverb-verb chain detection (sentences that command but state no facts)
- Jurisdiction classification (land/soil vs sea/water)

Your job is to provide a PRACTICAL critique of this analysis:

1. USEFUL FINDINGS — Which findings from the structural analysis would actually
   matter in a legal proceeding, mediation, or negotiation? Which are structurally
   interesting but practically irrelevant?

2. DOCUMENT EFFECTIVENESS — Setting aside the framework's rules, how effective
   is this document at its apparent purpose? Does it persuade? Does it establish
   facts? Does it create a clear record?

3. SPECIFIC REWRITES — Take the 2-3 weakest sentences identified by the tool
   and suggest concrete rewrites that would be stronger BOTH in conventional
   legal writing AND in parse-syntax terms. Show both versions.

4. STRATEGIC ASSESSMENT — What does this document reveal about the author's
   position, strategy, and leverage? What would a judge or opposing counsel
   take from it?

5. WHAT THE TOOL MISSED — What issues does the document have that the
   structural analysis did NOT catch? Logical gaps, unsupported claims,
   missing evidence references, tone problems?

Be direct. No hedging. Give the kind of feedback a sharp litigation partner
would give a junior associate's draft."""


def build_critique_prompt(document_text: str, scan_result: dict) -> str:
    """Build the user prompt for AI critique."""
    # Compact the scan result for the prompt
    compact = {
        "overall_score": scan_result.get("overall_score"),
        "overall_grade": scan_result.get("overall_grade"),
        "jurisdiction": scan_result.get("jurisdiction"),
        "dog_latin_pct": scan_result.get("dog_latin_pct"),
        "null_chain_count": scan_result.get("null_chain_count"),
        "findings": scan_result.get("findings", []),
        "recommendations": scan_result.get("recommendations", []),
        "factual_score": scan_result.get("factual_score", {}),
    }
    # Include worst sentences
    worst = sorted(
        scan_result.get("sentence_analyses", []),
        key=lambda x: x.get("score", 100),
    )[:5]
    compact["worst_sentences"] = [
        {"text": s.get("original", "")[:150], "score": s.get("score", 0),
         "issues": s.get("issues", [])}
        for s in worst
    ]

    return f"""## DOCUMENT TEXT

{document_text}

## STRUCTURAL ANALYSIS (qwparse scan output)

{json.dumps(compact, indent=2, default=str)}

Provide your critique following the 5-section structure from your instructions."""


# ---------------------------------------------------------------------------
# AI revise prompt for qwparse revise
# ---------------------------------------------------------------------------

REVISE_SYSTEM = """\
You are a context-free legal document judge.

You know NOTHING about this case. You have no backstory, no prior documents,
no sympathies. You see ONLY the text on this page. Your job is to evaluate
whether this document would survive scrutiny from a judge, opposing counsel,
or tribunal who also knows nothing beyond what is written here.

This is the core test: **does the document stand alone?**

A document that assumes the reader knows the backstory is a weak document.
A document that makes claims without citing specific evidence is an
unsupported document. A document that uses emotional language where factual
language would be stronger is an amateur document.

You will receive:
1. The document text
2. A structural analysis from qwparse (scores, findings, weaknesses)

Your output must be a REVISED VERSION of the document that fixes:

## REVISION PRIORITIES (in order)

1. **UNSUPPORTED CLAIMS → CITED FACTS**
   Every factual claim must cite its source: document name, date, paragraph,
   exhibit number. If the document says "Your firm filed X" but doesn't say
   WHEN, WHERE, or which filing — flag it and add a placeholder: [CITE: date
   and filing reference needed].

2. **ASSUMED CONTEXT → EXPLICIT CONTEXT**
   If a sentence only makes sense to someone who already knows the case,
   rewrite it so a stranger (the judge) can follow. Front-load the who/what/
   when/where.

3. **EMOTIONAL APPEALS → FACTUAL FRAMING**
   Replace rhetoric with math. "Your fees are eating the estate" becomes
   "Attorney fees of $[X] against remaining equity of $[Y] yield a net
   recovery of $[Z], a [N]% reduction." Let the numbers do the persuading.

4. **STRUCTURAL WEAKNESSES**
   Fix issues from the qwparse scan: null chains, pronoun substitutions,
   jurisdiction mixing. But only where the fix improves clarity — don't
   sacrifice readability for parse-syntax purity.

5. **MISSING ELEMENTS**
   Add what's absent: date, case number, parties identified by full name,
   specific relief requested, evidence references, deadlines.

## OUTPUT FORMAT

Return TWO sections:

### DEFICIENCIES
A numbered list of specific problems found, each with:
- What's wrong (one sentence)
- Why it matters to a judge (one sentence)
- Where in the document it occurs

### REVISED DOCUMENT
The complete revised text. Mark every change with:
- [ADDED] for new content you inserted
- [CITE NEEDED: description] for facts that need sourcing
- [REWRITTEN] at the start of substantially changed paragraphs

Preserve the author's intent and strategy. You are improving the execution,
not changing the argument. The author knows their case better than you do —
you are testing whether they communicated it to someone who doesn't."""


def build_revise_prompt(document_text: str, scan_result: dict) -> str:
    """Build the user prompt for AI revision."""
    compact = {
        "overall_score": scan_result.get("overall_score"),
        "overall_grade": scan_result.get("overall_grade"),
        "dog_latin_pct": scan_result.get("dog_latin_pct"),
        "null_chain_count": scan_result.get("null_chain_count"),
        "findings": scan_result.get("findings", []),
        "recommendations": scan_result.get("recommendations", []),
    }
    worst = sorted(
        scan_result.get("sentence_analyses", []),
        key=lambda x: x.get("score", 100),
    )[:5]
    compact["worst_sentences"] = [
        {"text": s.get("original", "")[:200], "score": s.get("score", 0),
         "issues": s.get("issues", [])}
        for s in worst
    ]

    return f"""## DOCUMENT TEXT (this is ALL you know about this case)

{document_text}

## STRUCTURAL ANALYSIS (qwparse scan output)

{json.dumps(compact, indent=2, default=str)}

Apply your revision process. Return DEFICIENCIES then REVISED DOCUMENT."""


# ---------------------------------------------------------------------------
# Vector DB search for citation filling
# ---------------------------------------------------------------------------

DEVCTL_PATH = Path.home() / "GitHub" / "policy-orchestrator"
SDATA_MD_DIR = Path.home() / "GitHub" / "div_legal" / "sdata" / "md"
SDATA_INDEX = Path.home() / "GitHub" / "div_legal" / "sdata" / "index.json"

# Lazy-loaded title→filename index
_title_index: dict[str, str] | None = None


def _get_title_index() -> dict[str, str]:
    """Load the sdata/index.json title→filename map (cached)."""
    global _title_index
    if _title_index is None:
        _title_index = {}
        try:
            import json as _json
            idx = _json.load(open(SDATA_INDEX))
            for f in idx.get("files", []):
                title = f.get("title", "").lower().strip()
                if title:
                    _title_index[title] = f["filename"]
        except Exception:
            pass
    return _title_index


def _read_source_file(title: str, snippet: str = "") -> str:
    """Given a devctl result title, read the full source markdown.

    Returns up to 3000 chars of relevant content from the source file.
    If the snippet is provided, extracts context around the matching area.
    """
    idx = _get_title_index()
    filename = idx.get(title.lower().strip(), "")
    if not filename:
        return ""

    md_path = SDATA_MD_DIR / filename
    if not md_path.exists():
        return ""

    try:
        full = md_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    # Strip YAML frontmatter
    if full.startswith("---"):
        end = full.find("---", 3)
        if end > 0:
            full = full[end + 3:].strip()

    # If we have a snippet, find it and extract surrounding context
    if snippet and len(snippet) > 30:
        search_frag = snippet[:60].strip()
        idx_pos = full.find(search_frag)
        if idx_pos >= 0:
            start = max(0, idx_pos - 500)
            end = min(len(full), idx_pos + 2500)
            return full[start:end]

    # Otherwise return first 3000 chars (skip tiny files)
    if len(full) < 50:
        return ""
    return full[:3000]


def search_db(query: str, limit: int = 5) -> list[dict]:
    """Search the vector DB via devctl then enrich with full source text.

    Pipeline:
    1. devctl search (BGE + SPLADE + reranking) for ranking
    2. Parse results to get title, collection, score, snippet
    3. Look up title in sdata/index.json → filename
    4. Read sdata/md/{filename} for full document context (up to 3000 chars)

    Returns list of {score, collection, source_type, title, date, text}.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "devctl", "search", query, "--limit", str(limit)],
            capture_output=True, text=True, timeout=60,
            cwd=str(DEVCTL_PATH),
        )
        results = _parse_devctl_results(result.stdout)
        # Enrich each result with full source text
        for r in results:
            full_text = _read_source_file(r.get("title", ""), r.get("snippet", ""))
            if full_text:
                r["text"] = full_text
            elif r.get("snippet"):
                r["text"] = r["snippet"]
            elif r.get("title", "").startswith("{"):
                # case_facts: the "title" IS the JSON fact payload
                r["text"] = r["title"]
            # else text stays as parsed
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _parse_devctl_results(output: str) -> list[dict]:
    """Parse devctl search output into structured results.

    devctl output format:
      [1] 3.387  case_docs  md  2024-11-15
          Title Of Document
          content snippet that may span multiple lines
    """
    results = []
    current: dict | None = None
    for line in output.split("\n"):
        m = re.match(
            r'\s+\[(\d+)\]\s+([-\d.]+)\s+(\S+)\s+(\S*)\s*([\d-]*\S*)',
            line,
        )
        if m:
            if current:
                results.append(current)
            current = {
                "rank": int(m.group(1)),
                "score": float(m.group(2)),
                "collection": m.group(3),
                "source_type": m.group(4).strip() or "unknown",
                "date": m.group(5).strip() or "",
                "title": "",
                "snippet": "",
                "text": "",
            }
            continue
        # Indented lines (6+ spaces)
        if current and line.startswith("      "):
            text = line.strip()
            if not text:
                continue
            # First indented line = title/filename
            if not current["title"]:
                current["title"] = text
            else:
                # Subsequent lines = content snippet
                if current["snippet"]:
                    current["snippet"] += " " + text
                else:
                    current["snippet"] = text
    if current:
        results.append(current)
    return results


def _enrich_text(result: dict) -> str:
    """Enrich a search result with full text from sdata/md/ source file.

    Reads the source markdown file and extracts a larger context window
    around the matched snippet.
    """
    snippet = result.get("text", "")
    filename = result.get("filename", "")

    # Try to load the full source file
    if filename:
        # Filename from devctl often has spaces/formatting — try direct match
        md_path = SDATA_MD_DIR / filename
        if not md_path.exists():
            # Try fuzzy match on the stem
            stem = filename.split(".")[0] if "." in filename else filename
            candidates = list(SDATA_MD_DIR.glob(f"*{stem[:30]}*"))
            if candidates:
                md_path = candidates[0]

        if md_path.exists():
            try:
                full = md_path.read_text(encoding="utf-8", errors="replace")
                # Find the snippet in the full text and extract surrounding context
                if snippet and len(snippet) > 30:
                    # Search for a fragment of the snippet
                    search_frag = snippet[:60].strip()
                    idx = full.find(search_frag)
                    if idx >= 0:
                        # Extract 2000 chars around the match
                        start = max(0, idx - 500)
                        end = min(len(full), idx + 1500)
                        return full[start:end]
                # If no match found, return first 2000 chars
                return full[:2000]
            except Exception:
                pass

    # For case_facts, the snippet IS the full fact
    if result.get("collection") == "case_facts":
        return snippet

    # Fallback: return whatever we have, padded
    return snippet


def extract_cite_queries(document: str) -> list[str]:
    """Extract [CITE NEEDED: ...] markers and build focused search queries.

    Keeps queries short and specific for better semantic search recall.
    Adds key context from the surrounding sentence.
    """
    queries = []
    lines = document.split("\n")
    for i, line in enumerate(lines):
        for m in re.finditer(r'\[CITE NEEDED:\s*([^\]]+)\]', line):
            marker = m.group(1).strip().rstrip(".,")
            if len(marker) < 10:
                continue

            # Extract just the core factual claim from surrounding text
            # Get the sentence fragment BEFORE the marker
            before = line[:m.start()]
            # Clean brackets and markdown
            before = re.sub(r'\[.*?\]', '', before)
            before = re.sub(r'[*#_]', '', before).strip()
            # Take last ~80 chars of context
            context = before[-80:].strip() if before else ""

            # Build query: context + marker, keep under 120 chars
            q = f"{context} {marker}".strip()[:120]
            queries.append(q)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for q in queries:
        key = q.lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


def gather_evidence(document: str, max_queries: int = 8,
                    results_per_query: int = 3) -> str:
    """Search DB for evidence matching all CITE NEEDED markers.

    Runs targeted searches then enriches with full source text.
    Limits to max_queries to avoid excessive API calls (each devctl
    search takes ~3s due to embedding model loading).
    """
    queries = extract_cite_queries(document)[:max_queries]
    if not queries:
        return ""

    all_evidence: list[dict] = []
    seen_texts: set[str] = set()

    for i, query in enumerate(queries):
        results = search_db(query, limit=results_per_query)
        for r in results:
            # Dedup by text content
            key = r["text"][:100] if r["text"] else r.get("filename", "")
            if key and key not in seen_texts:
                seen_texts.add(key)
                r["query"] = query[:100]
                all_evidence.append(r)

    if not all_evidence:
        return ""

    lines = ["## EVIDENCE FROM CASE DATABASE\n"]
    lines.append(f"Searched {len(queries)} citation gaps across all "
                 f"collections (case_docs 1.7M, legal_docs_v2 362K, "
                 f"case_facts 16K, etc.). Found {len(all_evidence)} "
                 f"evidence fragments.\n")
    lines.append("Use these to fill [CITE NEEDED] markers. Quote the "
                 "relevant portion and cite the source.\n")

    for e in all_evidence:
        lines.append(f"### Evidence for: {e.get('query', '')[:80]}")
        lines.append(f"**Source:** {e['collection']} / {e['source_type']} "
                     f"/ {e.get('filename', 'unknown')}")
        lines.append(f"**Date:** {e.get('date', 'undated')}  "
                     f"**Score:** {e['score']:.3f}")
        text = e["text"][:1500]
        lines.append(f"**Full text:**\n{text}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fill-citations prompt for qwparse draft
# ---------------------------------------------------------------------------

FILL_SYSTEM = """\
You are a legal document finalizer. You have:

1. A REVISED DOCUMENT with [CITE NEEDED: ...] placeholders
2. EVIDENCE retrieved from the case database (emails, filings, financial
   records, court transcripts, chat messages)

Your job is to fill every [CITE NEEDED] placeholder with REAL citations
from the evidence provided. Follow these rules:

- **ONLY use evidence that is actually provided.** Do not invent citations.
- If the evidence contains the specific fact (date, amount, filing reference),
  replace [CITE NEEDED: ...] with the actual citation in this format:
  (Source: [collection/source_type], [date], "[relevant quote]")
- If no evidence matches a particular [CITE NEEDED], keep the placeholder
  but add [NO EVIDENCE FOUND] after it.
- Do NOT change the document structure, argument, or wording beyond
  filling citations.
- If the evidence CONTRADICTS a claim in the document, insert a
  [WARNING: evidence contradicts — ...] note.
- Keep the document clean and professional — this is the FINAL version.

Return ONLY the final document text, ready to send. No preamble, no
explanation, no meta-commentary."""


def build_fill_prompt(revised_doc: str, evidence: str) -> str:
    """Build the prompt for citation-filling pass."""
    return f"""## REVISED DOCUMENT (with [CITE NEEDED] placeholders)

{revised_doc}

{evidence}

Fill every [CITE NEEDED] with real citations from the evidence above.
Return the final document only."""
