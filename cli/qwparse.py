#!/usr/bin/env python3
"""qwparse — Quantum Word Parse CLI.

Structural analysis of language: morpheme decomposition, DOG-LATIN detection,
null-chain identification, sentence grading, and full document evaluation
with actionable suggestions.

Usage:
    qwparse                                     # dashboard
    qwparse word insurance corporation attorney  # decompose words
    qwparse sentence "The court hereby orders…"  # grade a sentence
    qwparse scan document.md                     # full document analysis
    qwparse scan --dir ./legal-docs/             # batch evaluate
    qwparse dog-latin "THE STATE OF TEXAS"       # DOG-LATIN scan
    qwparse nullchain "hereby orders that…"      # null chain detection
    qwparse case "JOHN DOE" ":John-Doe:"         # jurisdiction by case form
    qwparse basis                                # 720-word basis summary
    qwparse basis --search contract              # search basis set
    qwparse eval --builtins                      # evaluate built-in docs

AI-enhanced:
    qwparse models                               # list all available models
    qwparse scan document.md --ai                # structural + AI critique
    qwparse scan document.md --ai --model claude-sonnet-4-6

Machine-readable:
    qwparse scan document.md --json              # JSON output
    qwparse word insurance --json | jq .         # pipe to jq

Deploy: symlink to ~/bin/qwparse
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root and wire up imports
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# ANSI colors (devctl pattern)
# ---------------------------------------------------------------------------
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[90m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "gold": "\033[93m",
    "cyan": "\033[36m",
    "red": "\033[31m",
    "mag": "\033[35m",
    "blue": "\033[34m",
}

NO_COLOR = os.environ.get("NO_COLOR") is not None


def c(key: str) -> str:
    """Return ANSI code, or empty string if NO_COLOR."""
    if NO_COLOR:
        return ""
    return C.get(key, "")


# ---------------------------------------------------------------------------
# Lazy imports — only load modules when needed
# ---------------------------------------------------------------------------

def _import_word_parser():
    from word_parser import parse_word
    return parse_word


def _import_sentence_analyzer():
    from sentence_analyzer import analyze_sentence
    return analyze_sentence


def _import_dog_latin():
    from dog_latin_detector import scan_document, detect_dog_latin, highlight_dog_latin
    return scan_document, detect_dog_latin, highlight_dog_latin


def _import_adverb_verb():
    from adverb_verb_detector import detect_null_chains, score_factual_content
    return detect_null_chains, score_factual_content


def _import_case_analyzer():
    from case_analyzer import analyze_case_form, compare_forms
    return analyze_case_form, compare_forms


def _import_document_evaluator():
    from document_evaluator import evaluate_document, format_evaluation
    return evaluate_document, format_evaluation


def _import_morpheme():
    from morpheme_negation import decompose, is_vcc_negated, decompose_batch
    return decompose, is_vcc_negated, decompose_batch


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a text file (.md, .txt) or extract text from PDF."""
    p = Path(path)
    if not p.exists():
        print(f"{c('red')}Error: file not found: {path}{c('reset')}", file=sys.stderr)
        sys.exit(1)

    suffix = p.suffix.lower()

    if suffix == ".pdf":
        return _read_pdf(p)
    else:
        return p.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extract text from PDF. Tries pymupdf, falls back to pdfplumber."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(path))
        text = "\n\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except ImportError:
        pass

    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            return "\n\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
    except ImportError:
        pass

    print(
        f"{c('red')}Error: PDF support requires pymupdf or pdfplumber.{c('reset')}\n"
        f"{c('dim')}  Install: uv pip install pymupdf{c('reset')}",
        file=sys.stderr,
    )
    sys.exit(1)


def read_stdin_or_arg(args) -> str | None:
    """Read text from args.text, args.file, or stdin.

    Auto-detects file paths in positional args: if the text looks like
    a path to an existing file, read the file instead of treating the
    path string as literal text.
    """
    if hasattr(args, "file") and args.file:
        return read_file(args.file)
    if hasattr(args, "text") and args.text:
        joined = " ".join(args.text) if isinstance(args.text, list) else args.text
        # Auto-detect file path: single arg that looks like a file path
        candidate = args.text[0] if isinstance(args.text, list) and len(args.text) == 1 else joined
        if (len(candidate.split()) == 1
                and not candidate.startswith("-")
                and Path(candidate).expanduser().exists()
                and Path(candidate).expanduser().is_file()):
            p = Path(candidate).expanduser()
            # Set file on args so title extraction works downstream
            args.file = str(p)
            return read_file(str(p))
        return joined
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def emit(data: dict | list, args, formatter=None):
    """Output data as JSON or formatted text."""
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    elif formatter:
        print(formatter(data))
    else:
        _default_format(data)


def _default_format(data):
    """Simple key-value formatter for dicts."""
    if isinstance(data, list):
        for item in data:
            _default_format(item)
            print()
        return
    if not isinstance(data, dict):
        print(data)
        return
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            continue
        print(f"  {c('dim')}{k}:{c('reset')} {v}")


def grade_color(grade: str) -> str:
    if grade == "A":
        return c("green")
    if grade in ("B", "C"):
        return c("yellow")
    return c("red")


def score_color(score: int | float) -> str:
    if score >= 75:
        return c("green")
    if score >= 50:
        return c("yellow")
    return c("red")


# ---------------------------------------------------------------------------
# Subcommand: word
# ---------------------------------------------------------------------------

def cmd_word(args):
    """Decompose words into prefix/root/suffix with VCC analysis."""
    parse_word = _import_word_parser()
    words = args.words
    if not words:
        if not sys.stdin.isatty():
            words = sys.stdin.read().split()
        else:
            print(f"{c('red')}Error: provide words to parse{c('reset')}", file=sys.stderr)
            sys.exit(1)

    results = [parse_word(w) for w in words]

    if args.json:
        print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
        return

    for r in results:
        word = r.get("word", "")
        decomp = r.get("decomposition", {})
        negated = r.get("vcc_negated", False)

        neg_marker = f" {c('red')}[VCC NEGATED]{c('reset')}" if negated else ""
        print(f"\n  {c('bold')}{word.upper()}{c('reset')}{neg_marker}")

        prefix = decomp.get("prefix", "")
        root = decomp.get("root", "")
        suffix = decomp.get("suffix", "")
        parts = []
        if prefix:
            parts.append(f"{c('red')}{prefix}{c('reset')}({decomp.get('prefix_meaning', '')})")
        if root:
            parts.append(f"{c('green')}{root}{c('reset')}({decomp.get('root_meaning', '')})")
        if suffix:
            parts.append(f"{c('cyan')}{suffix}{c('reset')}({decomp.get('suffix_meaning', '')})")

        if parts:
            print(f"    {' + '.join(parts)}")

        true_m = decomp.get("true_meaning", "")
        apparent_m = decomp.get("apparent_meaning", "")
        if true_m:
            print(f"    {c('gold')}True meaning:{c('reset')} {true_m}")
        if apparent_m:
            print(f"    {c('dim')}Apparent meaning:{c('reset')} {apparent_m}")

        jur = r.get("jurisdiction", {})
        if isinstance(jur, dict) and jur.get("jurisdiction"):
            j = jur["jurisdiction"]
            j_color = c("red") if "Maritime" in j or "Dead" in j else c("green")
            print(f"    {c('dim')}Jurisdiction:{c('reset')} {j_color}{j}{c('reset')}")

        summary = r.get("summary", "")
        if summary:
            print(f"    {c('dim')}{summary}{c('reset')}")


# ---------------------------------------------------------------------------
# Subcommand: sentence
# ---------------------------------------------------------------------------

def cmd_sentence(args):
    """Analyze sentence for C.S.S.C.P.S.G.P. compliance."""
    analyze_sentence = _import_sentence_analyzer()
    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide a sentence to analyze{c('reset')}", file=sys.stderr)
        sys.exit(1)

    result = analyze_sentence(text)

    if args.json:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        return

    grade = result.get("grade", "?")
    score = result.get("score", 0)
    gc = grade_color(grade)
    sc = score_color(score)

    print(f"\n  {c('bold')}SENTENCE ANALYSIS{c('reset')}")
    print(f"  {c('dim')}{result.get('original', text)}{c('reset')}")
    print(f"\n  {c('bold')}Score:{c('reset')} {sc}{score}/100{c('reset')}  "
          f"{c('bold')}Grade:{c('reset')} {gc}{grade}{c('reset')}")
    print(f"  {c('dim')}Nouns: {result.get('noun_count', 0)} | "
          f"Preposition start: {result.get('starts_with_preposition', False)} | "
          f"Gerund verbs: {result.get('has_gerund_verbs', False)}{c('reset')}")

    if result.get("has_null_chain"):
        print(f"  {c('red')}NULL CHAIN detected — sentence conveys zero facts{c('reset')}")

    issues = result.get("issues", [])
    if issues:
        print(f"\n  {c('red')}Issues:{c('reset')}")
        for iss in issues:
            print(f"    {c('red')}{iss}{c('reset')}")

    corrections = result.get("corrections", [])
    if corrections:
        print(f"\n  {c('gold')}Suggestions:{c('reset')}")
        for corr in corrections:
            print(f"    {c('gold')}{corr}{c('reset')}")
    print()


# ---------------------------------------------------------------------------
# Subcommand: scan (full document analysis)
# ---------------------------------------------------------------------------

def cmd_scan(args):
    """Full document evaluation with grade and suggestions."""
    evaluate_document, format_evaluation = _import_document_evaluator()

    # Batch mode
    if args.dir:
        _scan_directory(args, evaluate_document, format_evaluation)
        return

    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide text, --file, or pipe stdin{c('reset')}", file=sys.stderr)
        sys.exit(1)

    title = ""
    if hasattr(args, "file") and args.file:
        title = Path(args.file).name

    result = evaluate_document(text, title)

    if args.json:
        # Strip the raw text from JSON to keep output manageable
        out = {k: v for k, v in result.items() if k != "text"}
        # Simplify sentence analyses for JSON
        out["sentence_analyses"] = [
            {
                "original": sa["original"][:120],
                "score": sa["score"],
                "grade": sa["grade"],
                "noun_count": sa["noun_count"],
                "issues": sa["issues"],
                "corrections": sa.get("corrections", []),
            }
            for sa in result.get("sentence_analyses", [])
        ]
        # AI critique in JSON mode
        if getattr(args, "ai", False):
            from ai_providers import (
                complete, pick_default_model, CRITIQUE_SYSTEM, build_critique_prompt,
            )
            model_id = getattr(args, "model", None) or pick_default_model()
            if model_id:
                prompt = build_critique_prompt(text, result)
                try:
                    critique = complete(model_id, CRITIQUE_SYSTEM, prompt, max_tokens=4096)
                    out["ai_critique"] = {"model": model_id, "response": critique}
                except Exception as e:
                    out["ai_critique"] = {"model": model_id, "error": str(e)}

        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return

    # Human-readable
    if NO_COLOR:
        _format_scan_plain(result)
    else:
        print(format_evaluation(result))

    # Always show suggestions summary at the end
    _print_suggestions(result)

    # AI critique if requested
    if getattr(args, "ai", False):
        model_id = getattr(args, "model", None)
        run_ai_critique(text, result, model_id)


def _scan_directory(args, evaluate_document, format_evaluation):
    """Batch evaluate all text files in a directory."""
    dir_path = Path(args.dir)
    if not dir_path.is_dir():
        print(f"{c('red')}Error: not a directory: {args.dir}{c('reset')}", file=sys.stderr)
        sys.exit(1)

    extensions = {".md", ".txt", ".text", ".pdf"}
    files = sorted(f for f in dir_path.iterdir() if f.suffix.lower() in extensions)

    if not files:
        print(f"{c('yellow')}No .md/.txt/.pdf files found in {args.dir}{c('reset')}")
        return

    results = []
    for fp in files:
        text = read_file(str(fp))
        result = evaluate_document(text, fp.name)
        results.append(result)

    if args.json:
        out = []
        for r in results:
            out.append({
                "title": r["title"],
                "overall_score": r["overall_score"],
                "overall_grade": r["overall_grade"],
                "jurisdiction": r["jurisdiction"],
                "dog_latin_pct": r["dog_latin_pct"],
                "null_chain_count": r["null_chain_count"],
                "findings": r["findings"],
                "recommendations": r["recommendations"],
            })
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return

    # Summary table
    print(f"\n  {c('bold')}BATCH ANALYSIS — {len(files)} documents{c('reset')}\n")
    for r in results:
        gc = grade_color(r["overall_grade"])
        sc = score_color(r["overall_score"])
        title = r["title"][:40]
        print(f"  {gc}{r['overall_grade']}{c('reset')} "
              f"{sc}{r['overall_score']:>3}/100{c('reset')}  "
              f"{r['dog_latin_pct']:>4.0f}% DL  "
              f"{r['null_chain_count']} nulls  "
              f"{c('dim')}{title}{c('reset')}")

    # Aggregate stats
    avg_score = sum(r["overall_score"] for r in results) / len(results)
    avg_dl = sum(r["dog_latin_pct"] for r in results) / len(results)
    total_nulls = sum(r["null_chain_count"] for r in results)
    print(f"\n  {c('dim')}Average score: {avg_score:.0f}/100 | "
          f"Average DOG-LATIN: {avg_dl:.0f}% | "
          f"Total null chains: {total_nulls}{c('reset')}\n")


def _format_scan_plain(result):
    """Plain text output for scan (when NO_COLOR)."""
    print(f"\n{'=' * 70}")
    print(f"  {result.get('title', 'Document Evaluation')}")
    print(f"{'=' * 70}")
    print(f"  Score: {result['overall_score']}/100  Grade: {result['overall_grade']}")
    print(f"  Jurisdiction: {result['jurisdiction']}")
    print(f"  DOG-LATIN: {result['dog_latin_pct']:.0f}%")
    print(f"  Null chains: {result['null_chain_count']}")
    fr = result.get("factual_score", {})
    print(f"  Factual ratio: {fr.get('factual_ratio', 0):.0%} "
          f"({fr.get('noun_count', 0)} nouns, {fr.get('null_word_count', 0)} null words)")
    print(f"{'=' * 70}")


def _print_suggestions(result):
    """Print actionable suggestions for improving the document."""
    recs = result.get("recommendations", [])
    findings = result.get("findings", [])

    if not recs and not findings:
        return

    print(f"\n  {c('bold')}{c('gold')}ACTIONABLE SUGGESTIONS{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")

    # Specific rewrites based on sentence analysis
    worst = sorted(
        result.get("sentence_analyses", []),
        key=lambda x: x.get("score", 100),
    )[:5]

    for i, sa in enumerate(worst, 1):
        if sa.get("score", 100) >= 75:
            continue
        orig = sa.get("original", "")[:80]
        print(f"\n  {c('red')}{i}. [{sa.get('score', '?')}/100]{c('reset')} {c('dim')}{orig}{c('reset')}")
        for corr in sa.get("corrections", []):
            print(f"     {c('gold')}{corr}{c('reset')}")
        for iss in sa.get("issues", []):
            print(f"     {c('dim')}{iss}{c('reset')}")
    print()


# ---------------------------------------------------------------------------
# Subcommand: models
# ---------------------------------------------------------------------------

def cmd_models(args):
    """List all available models across providers."""
    from ai_providers import discover_models, ALL_PROVIDERS

    models = discover_models()

    if args.json:
        print(json.dumps([m.to_dict() for m in models], indent=2))
        return

    print(f"\n  {c('bold')}AVAILABLE MODELS{c('reset')}")
    print(f"  {c('dim')}{'─' * 60}{c('reset')}")

    # Group by provider
    by_provider: dict[str, list] = {}
    for m in models:
        by_provider.setdefault(m.provider, []).append(m)

    for provider in ALL_PROVIDERS:
        pname = provider.name
        pmodels = by_provider.get(pname, [])
        avail = provider.is_available()
        status = f"{c('green')}available{c('reset')}" if avail else f"{c('red')}no API key{c('reset')}"
        if pname == "ollama":
            status = f"{c('green')}running{c('reset')}" if avail else f"{c('red')}offline{c('reset')}"

        print(f"\n  {c('bold')}{pname.upper()}{c('reset')} {c('dim')}({status}){c('reset')}")

        if not pmodels:
            print(f"    {c('dim')}no models found{c('reset')}")
            continue

        for m in pmodels:
            a = f"{c('green')}" if m.available else f"{c('red')}"
            size = f" {m.size_gb:.1f}GB" if m.size_gb > 0 else ""
            ctx = f" {m.context // 1000}K ctx" if m.context > 0 else ""
            local_tag = f" {c('cyan')}[local]{c('reset')}" if m.local else ""
            print(f"    {a}{m.id:<36}{c('reset')} "
                  f"{c('dim')}{m.name}{size}{ctx}{c('reset')}{local_tag}")

    # Show default
    from ai_providers import pick_default_model
    default = pick_default_model()
    if default:
        print(f"\n  {c('gold')}Default model:{c('reset')} {default}")
    print(f"  {c('dim')}Override with: qwparse scan --ai --model <id>{c('reset')}\n")


# ---------------------------------------------------------------------------
# AI critique (used by scan --ai)
# ---------------------------------------------------------------------------

def run_ai_critique(document_text: str, scan_result: dict, model_id: str | None = None):
    """Run AI critique on a scanned document."""
    from ai_providers import (
        complete, pick_default_model, get_provider,
        CRITIQUE_SYSTEM, build_critique_prompt,
    )

    if not model_id:
        model_id = pick_default_model()
    if not model_id:
        print(f"{c('red')}Error: no AI models available. "
              f"Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY, "
              f"or start Ollama.{c('reset')}", file=sys.stderr)
        sys.exit(1)

    provider = get_provider(model_id)
    if not provider:
        print(f"{c('red')}Error: model '{model_id}' not found.{c('reset')}", file=sys.stderr)
        print(f"{c('dim')}Run: qwparse models{c('reset')}", file=sys.stderr)
        sys.exit(1)

    print(f"\n  {c('bold')}{c('cyan')}AI CRITIQUE{c('reset')} "
          f"{c('dim')}via {model_id} ({provider.name}){c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")
    print(f"  {c('dim')}Generating...{c('reset')}", end="", flush=True)

    prompt = build_critique_prompt(document_text, scan_result)

    try:
        response = complete(model_id, CRITIQUE_SYSTEM, prompt, max_tokens=4096)
        # Clear the "Generating..." line
        print(f"\r  {' ' * 30}\r", end="")
        print(f"\n  {c('bold')}{c('cyan')}AI CRITIQUE{c('reset')} "
              f"{c('dim')}via {model_id}{c('reset')}")
        print(f"  {c('dim')}{'─' * 50}{c('reset')}\n")
        # Print response with indentation
        for line in response.split("\n"):
            print(f"  {line}")
        print()
    except Exception as e:
        print(f"\r  {c('red')}Error: {e}{c('reset')}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: revise
# ---------------------------------------------------------------------------

def cmd_revise(args):
    """Context-free judge: scan → critique → produce revised document."""
    from ai_providers import (
        complete, pick_default_model, get_provider,
        REVISE_SYSTEM, build_revise_prompt,
    )
    evaluate_document, format_evaluation = _import_document_evaluator()

    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide text or file to revise{c('reset')}", file=sys.stderr)
        sys.exit(1)

    title = ""
    if hasattr(args, "file") and args.file:
        title = Path(args.file).name

    # Use stderr for progress when JSON mode is active
    out = sys.stderr if args.json else sys.stdout

    # Step 1: structural scan
    print(f"\n  {c('bold')}PHASE 1: STRUCTURAL SCAN{c('reset')}", file=out)
    print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
    result = evaluate_document(text, title)

    gc = grade_color(result["overall_grade"])
    sc = score_color(result["overall_score"])
    print(f"  Score: {sc}{result['overall_score']}/100{c('reset')}  "
          f"Grade: {gc}{result['overall_grade']}{c('reset')}  "
          f"DOG-LATIN: {result['dog_latin_pct']:.0f}%  "
          f"Null chains: {result['null_chain_count']}", file=out)
    if result["findings"]:
        for f in result["findings"][:3]:
            print(f"  {c('dim')}{f[:80]}{c('reset')}", file=out)

    # Step 2: AI revision
    model_id = args.model or pick_default_model()
    if not model_id:
        print(f"{c('red')}Error: no AI models available.{c('reset')}", file=sys.stderr)
        sys.exit(1)

    provider = get_provider(model_id)
    if not provider:
        print(f"{c('red')}Error: model '{model_id}' not found.{c('reset')}", file=sys.stderr)
        sys.exit(1)

    print(f"\n  {c('bold')}PHASE 2: CONTEXT-FREE JUDGE{c('reset')} "
          f"{c('dim')}via {model_id}{c('reset')}", file=out)
    print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
    print(f"  {c('dim')}The AI knows NOTHING about this case except what's on the page.{c('reset')}", file=out)
    print(f"  {c('dim')}Generating revision...{c('reset')}", end="", flush=True, file=out)

    prompt = build_revise_prompt(text, result)

    try:
        response = complete(model_id, REVISE_SYSTEM, prompt, max_tokens=8192)
    except Exception as e:
        print(f"\r  {c('red')}Error: {e}{c('reset')}", file=sys.stderr)
        sys.exit(1)

    print(f"\r{' ' * 60}\r", end="", file=out)

    if args.json:
        print(json.dumps({
            "title": title,
            "original_score": result["overall_score"],
            "original_grade": result["overall_grade"],
            "model": model_id,
            "revision": response,
            "findings": result["findings"],
            "recommendations": result["recommendations"],
        }, indent=2, default=str, ensure_ascii=False))
        return

    # Print revision
    print(f"\n  {c('bold')}{c('cyan')}CONTEXT-FREE REVISION{c('reset')} "
          f"{c('dim')}via {model_id}{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}\n")
    for line in response.split("\n"):
        # Highlight markers
        if "[CITE NEEDED:" in line or "[CITE:" in line:
            print(f"  {c('red')}{line}{c('reset')}")
        elif "[ADDED]" in line:
            print(f"  {c('green')}{line}{c('reset')}")
        elif "[REWRITTEN]" in line:
            print(f"  {c('gold')}{line}{c('reset')}")
        elif line.startswith("###") or line.startswith("##"):
            print(f"  {c('bold')}{line}{c('reset')}")
        else:
            print(f"  {line}")

    # Step 3: if --output, write the revised document
    if args.output:
        out_path = Path(args.output)
        # Extract just the revised document section
        revised = _extract_revised_document(response)
        out_path.write_text(revised, encoding="utf-8")
        print(f"\n  {c('green')}Revised document written to: {out_path}{c('reset')}")

        # Step 4: re-scan the revision
        print(f"\n  {c('bold')}PHASE 3: RE-SCAN REVISED DOCUMENT{c('reset')}")
        print(f"  {c('dim')}{'─' * 50}{c('reset')}")
        result2 = evaluate_document(revised, f"{title} (revised)")
        gc2 = grade_color(result2["overall_grade"])
        sc2 = score_color(result2["overall_score"])
        delta = result2["overall_score"] - result["overall_score"]
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        delta_color = c("green") if delta > 0 else c("red")
        print(f"  Before: {sc}{result['overall_score']}/100{c('reset')} ({gc}{result['overall_grade']}{c('reset')})")
        print(f"  After:  {sc2}{result2['overall_score']}/100{c('reset')} ({gc2}{result2['overall_grade']}{c('reset')})")
        print(f"  Delta:  {delta_color}{delta_str}{c('reset')}")
        if result2["findings"]:
            print(f"\n  {c('dim')}Remaining issues:{c('reset')}")
            for f in result2["findings"]:
                print(f"    {c('dim')}{f[:80]}{c('reset')}")
    print()


def _extract_revised_document(response: str) -> str:
    """Extract the revised document section from AI response.

    Looks for '# REVISED DOCUMENT' or '## REVISED DOCUMENT', captures
    everything after it until a meta-section like NOTES ON REVISION,
    ANALYSIS, or end of text.
    """
    lines = response.split("\n")
    in_revised = False
    revised_lines = []
    for line in lines:
        # Detect start of revised document section
        if not in_revised:
            stripped = line.strip().lstrip("#").strip()
            if stripped.upper().startswith("REVISED DOCUMENT"):
                in_revised = True
                continue
        else:
            # Detect end — meta sections that aren't part of the document
            stripped_upper = line.strip().lstrip("#").strip().upper()
            if stripped_upper and any(
                stripped_upper.startswith(stop) for stop in (
                    "NOTES ON REVISION",
                    "NOTES ON CHANGES",
                    "REVISION NOTES",
                    "ANALYSIS",
                    "SUMMARY OF CHANGES",
                    "CHANGE LOG",
                    "CHANGES MADE",
                )
            ):
                break
            revised_lines.append(line)

    # Strip markers from output file (keep content clean)
    cleaned = []
    for line in revised_lines:
        line = line.replace("[REWRITTEN] ", "").replace("[REWRITTEN]", "")
        line = line.replace("[ADDED] ", "").replace("[ADDED]", "")
        # Keep [CITE NEEDED] markers — those are actionable
        cleaned.append(line)

    text = "\n".join(cleaned).strip()
    return text if text else response


def _extract_factual_queries(original_text: str) -> list[str]:
    """Extract search queries from the ORIGINAL document's factual claims.

    Looks for sentences with specific numbers, names, dates, and legal
    terms — the things that will actually match evidence in the DB.
    Scores each sentence and returns the most fact-dense ones first.
    """
    scored: list[tuple[int, str]] = []
    sentences = re.split(r'[.!?\n]', original_text)
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 25:
            continue
        score = 0
        # Dollar amounts are strong signals
        score += len(re.findall(r'\$[\d,]+', sent)) * 3
        # Dates
        score += len(re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+', sent, re.I)) * 3
        score += len(re.findall(r'\b20\d{2}\b', sent)) * 2
        # Case-specific names
        score += len(re.findall(r'(?:Atagan|Tarara|Fitzpatrick|Conniff|Jannusch|Thorarinson)', sent, re.I)) * 2
        # Legal terms
        score += len(re.findall(r'(?:Financial Affidavit|contempt|arrearage|lien|mortgage|exhibit|order|motion|affidavit)', sent, re.I)) * 2
        # Specific numbers
        score += len(re.findall(r'\b\d{2,}\b', sent))

        if score >= 3:
            q = re.sub(r'[*#_\[\]]', '', sent).strip()[:120]
            if q:
                scored.append((score, q))

    # Sort by score descending, take top queries
    scored.sort(key=lambda x: -x[0])

    seen: set[str] = set()
    unique = []
    for _, q in scored:
        key = q.lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique[:10]


def _gather_with_queries(queries: list[str], max_queries: int = 8,
                         progress_file=None) -> str:
    """Run search_db on a list of queries and format evidence."""
    from ai_providers import search_db

    out = progress_file or sys.stderr
    all_evidence: list[dict] = []
    seen_texts: set[str] = set()

    for i, query in enumerate(queries[:max_queries]):
        print(f"\r  {c('dim')}  [{i+1}/{min(len(queries), max_queries)}] "
              f"{query[:50]}...{c('reset')}{' ' * 20}",
              end="", flush=True, file=out)
        try:
            results = search_db(query, limit=3)
        except Exception as e:
            print(f"\n  {c('red')}  Search error: {e}{c('reset')}", file=out)
            continue
        for r in results:
            text = r.get("text", "")
            if len(text) < 20:
                continue
            key = text[:100]
            if key not in seen_texts:
                seen_texts.add(key)
                r["query"] = query[:100]
                all_evidence.append(r)
        print(f"  {c('dim')}→ {len(results)} results, "
              f"{len(all_evidence)} total evidence{c('reset')}", file=out)
    print(file=out)

    if not all_evidence:
        return ""

    lines = ["## EVIDENCE FROM CASE DATABASE\n"]
    lines.append(f"Found {len(all_evidence)} evidence fragments from "
                 f"{len(queries[:max_queries])} searches across all collections.\n")
    lines.append("Use these to fill [CITE NEEDED] markers. Quote relevant "
                 "portions and cite source/date.\n")

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
# Subcommand: draft (full pipeline: revise×2 + DB fill → final)
# ---------------------------------------------------------------------------

def cmd_draft(args):
    """Full pipeline: context-free revise × 2, then fill citations from DB."""
    from ai_providers import (
        complete, pick_default_model, get_provider,
        REVISE_SYSTEM, build_revise_prompt,
        FILL_SYSTEM, build_fill_prompt,
        gather_evidence, extract_cite_queries,
    )
    evaluate_document, _ = _import_document_evaluator()

    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide text or file{c('reset')}", file=sys.stderr)
        sys.exit(1)

    title = ""
    if hasattr(args, "file") and args.file:
        title = Path(args.file).name

    model_id = args.model or pick_default_model()
    if not model_id:
        print(f"{c('red')}Error: no AI models available.{c('reset')}", file=sys.stderr)
        sys.exit(1)

    provider = get_provider(model_id)
    if not provider:
        print(f"{c('red')}Error: model '{model_id}' not found.{c('reset')}", file=sys.stderr)
        sys.exit(1)

    passes = args.passes or 2
    out = sys.stderr if args.json else sys.stdout

    # ── Phase 1: Structural scan ──────────────────────────────────
    print(f"\n  {c('bold')}PHASE 1: STRUCTURAL SCAN{c('reset')}", file=out)
    print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
    result = evaluate_document(text, title)
    gc = grade_color(result["overall_grade"])
    sc = score_color(result["overall_score"])
    print(f"  Score: {sc}{result['overall_score']}/100{c('reset')}  "
          f"Grade: {gc}{result['overall_grade']}{c('reset')}  "
          f"DOG-LATIN: {result['dog_latin_pct']:.0f}%  "
          f"Null chains: {result['null_chain_count']}", file=out)

    # ── Phase 2: Context-free revise passes ───────────────────────
    current_doc = text
    for i in range(1, passes + 1):
        print(f"\n  {c('bold')}PHASE 2.{i}: CONTEXT-FREE REVISE "
              f"(pass {i}/{passes}){c('reset')} {c('dim')}via {model_id}{c('reset')}", file=out)
        print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
        print(f"  {c('dim')}Generating...{c('reset')}", end="", flush=True, file=out)

        scan = evaluate_document(current_doc, f"{title} (pass {i})")
        prompt = build_revise_prompt(current_doc, scan)

        try:
            response = complete(model_id, REVISE_SYSTEM, prompt, max_tokens=8192)
        except Exception as e:
            print(f"\r  {c('red')}Error on pass {i}: {e}{c('reset')}", file=sys.stderr)
            break

        revised = _extract_revised_document(response)
        cite_count = revised.count("[CITE NEEDED")
        print(f"\r  Pass {i}: {len(revised.split())} words, "
              f"{cite_count} [CITE NEEDED] markers{' ' * 20}", file=out)
        current_doc = revised

    # ── Phase 3: Search DB for evidence ───────────────────────────
    # Search using the ORIGINAL document's factual claims, not the
    # AI-revised template (which has placeholder text).
    # Extract key entities and claims from the original.
    original_queries = _extract_factual_queries(text)
    cite_queries = extract_cite_queries(current_doc)

    search_queries = original_queries or cite_queries
    if search_queries:
        print(f"\n  {c('bold')}PHASE 3: DATABASE EVIDENCE RETRIEVAL{c('reset')}", file=out)
        print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
        print(f"  {c('dim')}Searching {len(search_queries)} evidence queries "
              f"(from original document)...{c('reset')}", file=out)
        for i, q in enumerate(search_queries[:8]):
            print(f"    {c('dim')}{i+1}. {q[:80]}{c('reset')}", file=out)

        evidence = _gather_with_queries(search_queries, max_queries=8,
                                         progress_file=out)
        evidence_count = evidence.count("### Evidence for:") if evidence else 0
        print(f"  Found {evidence_count} evidence fragments", file=out)

        if evidence:
            # Show what was found
            if not args.json:
                for line in evidence.split("\n"):
                    if line.startswith("### Evidence for:"):
                        print(f"    {c('gold')}{line}{c('reset')}", file=out)
                    elif line.startswith("**Full text:**"):
                        # Show first 100 chars of the text
                        pass
                    elif line.startswith("**Source:**"):
                        print(f"    {c('dim')}{line}{c('reset')}", file=out)

            # ── Phase 4: Fill citations (direct DB lookup, no LLM) ─
            print(f"\n  {c('bold')}PHASE 4: FILL CITATIONS (direct DB lookup){c('reset')}", file=out)
            print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)
            print(f"  {c('dim')}Matching [CITE NEEDED] markers to DB evidence...{c('reset')}",
                  file=out)

            from ai_providers import direct_fill_citations
            current_doc, direct_filled = direct_fill_citations(current_doc, max_queries=12)
            remaining_cites = current_doc.count("[CITE NEEDED")
            print(f"  Direct fill: {direct_filled}/{cite_count} citations resolved from DB",
                  file=out)
            print(f"  Remaining:   {remaining_cites} (need manual fill or more DB data)",
                  file=out)

            # If evidence was found and there are still gaps, try LLM fill
            # on the remaining markers using the evidence context
            if remaining_cites > 0 and evidence:
                print(f"  {c('dim')}Attempting LLM fill for {remaining_cites} remaining...{c('reset')}",
                      end="", flush=True, file=out)
                fill_prompt = build_fill_prompt(current_doc, evidence)
                try:
                    final = complete(model_id, FILL_SYSTEM, fill_prompt, max_tokens=8192)
                    if final and len(final) > 100:
                        new_remaining = final.count("[CITE NEEDED")
                        llm_filled = remaining_cites - new_remaining
                        if llm_filled > 0:
                            current_doc = final
                            remaining_cites = new_remaining
                        print(f"\r  LLM fill: +{llm_filled} additional "
                              f"({remaining_cites} still remaining){' ' * 10}", file=out)
                    else:
                        print(f"\r  LLM fill: skipped (insufficient response){' ' * 20}",
                              file=out)
                except Exception as e:
                    print(f"\r  {c('dim')}LLM fill skipped: {e}{c('reset')}{' ' * 20}",
                          file=out)
    else:
        print(f"\n  {c('dim')}No [CITE NEEDED] markers to fill.{c('reset')}", file=out)

    # ── Phase 5: Final score (triple metrics) ────────────────────
    from effectiveness import score_effectiveness, format_effectiveness
    from influence import score_influence, format_influence

    print(f"\n  {c('bold')}PHASE 5: FINAL SCORE{c('reset')}", file=out)
    print(f"  {c('dim')}{'─' * 50}{c('reset')}", file=out)

    # Parse-syntax score (structural purity)
    final_result = evaluate_document(current_doc, f"{title} (final)")
    gc2 = grade_color(final_result["overall_grade"])
    sc2 = score_color(final_result["overall_score"])
    delta = final_result["overall_score"] - result["overall_score"]
    delta_str = f"+{delta}" if delta > 0 else str(delta)
    delta_color = c("green") if delta > 0 else c("red") if delta < 0 else c("dim")

    # Effectiveness scores (practical quality)
    eff_orig = score_effectiveness(text)
    eff_final = score_effectiveness(current_doc, text)
    eff_delta = eff_final.total - eff_orig.total
    eff_delta_str = f"+{eff_delta}" if eff_delta > 0 else str(eff_delta)
    eff_delta_color = c("green") if eff_delta > 0 else c("red") if eff_delta < 0 else c("dim")

    print(f"\n  {c('bold')}Parse-Syntax (CSSCPSGP structural purity){c('reset')}", file=out)
    print(f"    Original:  {sc}{result['overall_score']}/100{c('reset')} "
          f"({gc}{result['overall_grade']}{c('reset')})", file=out)
    print(f"    Final:     {sc2}{final_result['overall_score']}/100{c('reset')} "
          f"({gc2}{final_result['overall_grade']}{c('reset')})", file=out)
    print(f"    Delta:     {delta_color}{delta_str}{c('reset')}", file=out)

    eff_gc = c("green") if eff_final.grade in ("A", "B") else c("yellow") if eff_final.grade == "C" else c("red")
    eff_gc_o = c("green") if eff_orig.grade in ("A", "B") else c("yellow") if eff_orig.grade == "C" else c("red")
    print(f"\n  {c('bold')}Effectiveness (practical document quality){c('reset')}", file=out)
    print(f"    Original:  {eff_gc_o}{eff_orig.total}/100{c('reset')} "
          f"({eff_gc_o}{eff_orig.grade}{c('reset')})", file=out)
    print(f"    Final:     {eff_gc}{eff_final.total}/100{c('reset')} "
          f"({eff_gc}{eff_final.grade}{c('reset')})", file=out)
    print(f"    Delta:     {eff_delta_color}{eff_delta_str}{c('reset')}", file=out)

    # Show dimension breakdown for final
    print(f"\n{format_effectiveness(eff_final)}", file=out)

    # Influence score (behavioral layer targeting)
    from influence import detect_audience
    if getattr(args, "audience", None):
        audience = args.audience
        print(f"\n  {c('dim')}Audience: {audience} (specified){c('reset')}", file=out)
    else:
        audience = detect_audience(text)
        print(f"\n  {c('dim')}Audience: {audience} (auto-detected){c('reset')}", file=out)

    inf_orig = score_influence(text, audience=audience)
    inf_final = score_influence(current_doc, audience=audience)
    inf_delta = inf_final.total - inf_orig.total
    inf_delta_str = f"+{inf_delta}" if inf_delta > 0 else str(inf_delta)
    inf_delta_color = c("green") if inf_delta > 0 else c("red") if inf_delta < 0 else c("dim")

    inf_gc = c("green") if inf_final.grade in ("A", "B") else c("yellow") if inf_final.grade == "C" else c("red")
    inf_gc_o = c("green") if inf_orig.grade in ("A", "B") else c("yellow") if inf_orig.grade == "C" else c("red")
    print(f"\n  {c('bold')}Influence (behavioral layer targeting){c('reset')}", file=out)
    print(f"    Original:  {inf_gc_o}{inf_orig.total}/100{c('reset')} "
          f"({inf_gc_o}{inf_orig.grade}{c('reset')}) "
          f"{c('dim')}audience: {inf_orig.audience}{c('reset')}", file=out)
    print(f"    Final:     {inf_gc}{inf_final.total}/100{c('reset')} "
          f"({inf_gc}{inf_final.grade}{c('reset')}) "
          f"{c('dim')}audience: {inf_final.audience}{c('reset')}", file=out)
    print(f"    Delta:     {inf_delta_color}{inf_delta_str}{c('reset')}", file=out)
    print(f"\n{format_influence(inf_final)}", file=out)

    # Audience-weighted composite
    COMPOSITE_WEIGHTS = {
        "judge":            (0.50, 0.35, 0.15),  # eff, inf, parse
        "opposing_counsel": (0.30, 0.55, 0.15),
        "opposing_party":   (0.25, 0.55, 0.20),
        "mediator":         (0.40, 0.40, 0.20),
        "gal":              (0.45, 0.35, 0.20),
        "ardc":             (0.55, 0.25, 0.20),
        "clerk":            (0.60, 0.10, 0.30),
        "public":           (0.30, 0.50, 0.20),
        "self":             (0.40, 0.30, 0.30),
    }
    w_eff, w_inf, w_parse = COMPOSITE_WEIGHTS.get(audience, (0.40, 0.40, 0.20))
    composite_orig = int(eff_orig.total * w_eff + inf_orig.total * w_inf +
                         result["overall_score"] * w_parse)
    composite_final = int(eff_final.total * w_eff + inf_final.total * w_inf +
                          final_result["overall_score"] * w_parse)
    comp_delta = composite_final - composite_orig
    comp_delta_str = f"+{comp_delta}" if comp_delta > 0 else str(comp_delta)
    comp_gc = c("green") if composite_final >= 70 else c("yellow") if composite_final >= 50 else c("red")
    comp_dc = c("green") if comp_delta > 0 else c("red") if comp_delta < 0 else c("dim")

    print(f"\n  {c('bold')}COMPOSITE ({audience} weights: "
          f"eff={w_eff:.0%} inf={w_inf:.0%} parse={w_parse:.0%}){c('reset')}", file=out)
    print(f"    Original:  {composite_orig}/100", file=out)
    print(f"    Final:     {comp_gc}{composite_final}/100{c('reset')}", file=out)
    print(f"    Delta:     {comp_dc}{comp_delta_str}{c('reset')}", file=out)

    # ── Output ────────────────────────────────────────────────────
    if args.json:
        print(json.dumps({
            "title": title,
            "scores": {
                "parse_syntax": {"original": result["overall_score"],
                                 "final": final_result["overall_score"], "delta": delta},
                "effectiveness": {"original": eff_orig.total, "final": eff_final.total,
                                  "delta": eff_delta},
                "influence": {"original": inf_orig.total, "final": inf_final.total,
                              "delta": inf_delta},
            },
            "effectiveness_detail": eff_final.to_dict(),
            "influence_detail": inf_final.to_dict(),
            "model": model_id,
            "passes": passes,
            "citations_remaining": current_doc.count("[CITE NEEDED"),
            "document": current_doc,
        }, indent=2, default=str, ensure_ascii=False))
    elif args.output:
        out_path = Path(args.output)
        out_path.write_text(current_doc, encoding="utf-8")
        print(f"\n  {c('green')}Final document written to: {out_path}{c('reset')}")
    else:
        # Print final document to stdout
        print(f"\n  {c('bold')}{c('cyan')}FINAL DOCUMENT{c('reset')}")
        print(f"  {c('dim')}{'─' * 50}{c('reset')}\n")
        for line in current_doc.split("\n"):
            if "[CITE NEEDED" in line or "[NO EVIDENCE" in line:
                print(f"  {c('red')}{line}{c('reset')}")
            elif "[WARNING:" in line:
                print(f"  {c('gold')}{line}{c('reset')}")
            elif "(Source:" in line:
                print(f"  {c('green')}{line}{c('reset')}")
            else:
                print(f"  {line}")
    print(file=out)


# ---------------------------------------------------------------------------
# Subcommand: dog-latin
# ---------------------------------------------------------------------------

def cmd_dog_latin(args):
    """Scan text for DOG-LATIN / GLOSSA."""
    scan_document, detect_dog_latin, highlight_dog_latin = _import_dog_latin()
    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide text to scan{c('reset')}", file=sys.stderr)
        sys.exit(1)

    result = scan_document(text)

    if args.json:
        # Exclude token-level detail unless verbose
        out = {k: v for k, v in result.items() if k != "tokens"}
        if args.verbose:
            out["tokens"] = result["tokens"]
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return

    dl_pct = result["dog_latin_pct"]
    dl_color = c("red") if dl_pct > 10 else (c("yellow") if dl_pct > 0 else c("green"))

    print(f"\n  {c('bold')}DOG-LATIN SCAN{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")
    print(f"  DOG-LATIN:     {dl_color}{dl_pct:.0f}%{c('reset')} "
          f"({result['dog_latin_count']}/{result['total_tokens']} tokens)")
    print(f"  English:       {result['english_count']} tokens")
    print(f"  Parse-syntax:  {result['parse_syntax_count']} tokens")
    print(f"  Assessment:    {c('bold')}{result['assessment']}{c('reset')}")

    if result["jurisdiction_mixing"]:
        print(f"  {c('red')}JURISDICTION MIXING — void per Chicago Manual 11:147{c('reset')}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  {c('yellow')}{w}{c('reset')}")

    # Highlighted text
    if not NO_COLOR:
        print(f"\n  {c('dim')}--- Highlighted ---{c('reset')}")
        print(f"  {highlight_dog_latin(text)}")
    print()


# ---------------------------------------------------------------------------
# Subcommand: nullchain
# ---------------------------------------------------------------------------

def cmd_nullchain(args):
    """Detect null adverb-verb chains."""
    detect_null_chains, score_factual_content = _import_adverb_verb()
    text = read_stdin_or_arg(args)
    if not text:
        print(f"{c('red')}Error: provide text to analyze{c('reset')}", file=sys.stderr)
        sys.exit(1)

    chains = detect_null_chains(text)
    factual = score_factual_content(text)

    if args.json:
        print(json.dumps({
            "null_chains": chains,
            "factual_content": factual,
        }, indent=2, default=str, ensure_ascii=False))
        return

    fr = factual["factual_ratio"]
    fr_color = c("green") if fr >= 0.3 else (c("yellow") if fr >= 0.15 else c("red"))

    print(f"\n  {c('bold')}NULL CHAIN ANALYSIS{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")
    print(f"  Null chains found: {c('red') if chains else c('green')}{len(chains)}{c('reset')}")
    print(f"  Factual ratio:     {fr_color}{fr:.0%}{c('reset')}")
    print(f"  Nouns: {factual['noun_count']}  Adverbs: {factual['adverb_count']}  "
          f"Modals: {factual['modal_count']}")
    print(f"  Assessment:        {c('bold')}{factual['assessment']}{c('reset')}")

    for i, ch in enumerate(chains, 1):
        sev_color = c("red") if ch.get("severity") == "critical" else c("yellow")
        print(f"\n  {sev_color}{i}. [{ch.get('severity', 'warning')}]{c('reset')} "
              f"\"{ch.get('text', '')}\"")
    print()


# ---------------------------------------------------------------------------
# Subcommand: case
# ---------------------------------------------------------------------------

def cmd_case(args):
    """Classify case form → jurisdiction."""
    analyze_case_form, compare_forms = _import_case_analyzer()
    names = args.names
    if not names:
        if not sys.stdin.isatty():
            names = sys.stdin.read().strip().split("\n")
        else:
            print(f"{c('red')}Error: provide names/text to classify{c('reset')}", file=sys.stderr)
            sys.exit(1)

    if args.compare and len(names) == 1:
        # Show all forms of one name
        results = compare_forms(names[0])
        if args.json:
            print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
            return
        print(f"\n  {c('bold')}CASE FORM COMPARISON: {names[0]}{c('reset')}")
        print(f"  {c('dim')}{'─' * 50}{c('reset')}")
        for r in results:
            status = r.get("status", "")
            s_color = c("green") if status == "CORRECT" else (
                c("yellow") if status == "VALID" else c("red")
            )
            print(f"  {s_color}{r.get('text', ''):.<30}{c('reset')} "
                  f"{r.get('form_type', ''):<18} "
                  f"{c('dim')}{r.get('jurisdiction', '')}{c('reset')}")
        print()
        return

    results = [analyze_case_form(n) for n in names]
    if args.json:
        print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
        return

    print(f"\n  {c('bold')}CASE FORM ANALYSIS{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")
    for r in results:
        status = r.get("status", "")
        s_color = c("green") if status in ("CORRECT", "VALID") else c("red")
        print(f"  {c('bold')}{r.get('text', '')}{c('reset')}")
        print(f"    Form:         {r.get('form_type', '')}")
        print(f"    Status:       {s_color}{status}{c('reset')}")
        print(f"    Jurisdiction: {r.get('jurisdiction', '')}")
        if r.get("explanation"):
            print(f"    {c('dim')}{r['explanation']}{c('reset')}")
        print()


# ---------------------------------------------------------------------------
# Subcommand: basis
# ---------------------------------------------------------------------------

def cmd_basis(args):
    """Query the 720-word basis set."""
    basis_path = DATA_DIR / "basis_720.json"
    if not basis_path.exists():
        print(f"{c('red')}Error: basis file not found at {basis_path}{c('reset')}", file=sys.stderr)
        print(f"{c('dim')}Generate it: python src/basis_generator.py{c('reset')}", file=sys.stderr)
        sys.exit(1)

    with open(basis_path) as f:
        basis = json.load(f)

    if args.search:
        query = args.search.lower()
        matches = [
            w for w in basis
            if query in w.get("word", "").lower()
            or query in w.get("root", "").lower()
            or query in json.dumps(w.get("decomposition", {})).lower()
        ]
        if args.json:
            print(json.dumps(matches, indent=2, default=str, ensure_ascii=False))
            return
        print(f"\n  {c('bold')}BASIS SEARCH: \"{args.search}\" — {len(matches)} results{c('reset')}\n")
        for w in matches[:30]:
            neg = f" {c('red')}[NEG]{c('reset')}" if w.get("negated") else ""
            jur = w.get("jurisdiction", "")
            j_color = c("red") if "sea" in jur.lower() else c("green")
            print(f"  {c('bold')}{w.get('word', ''):<20}{c('reset')} "
                  f"{w.get('role', ''):<16} "
                  f"{j_color}{jur:<20}{c('reset')}"
                  f"{neg}")
        if len(matches) > 30:
            print(f"\n  {c('dim')}... and {len(matches) - 30} more (use --json for all){c('reset')}")
        print()
        return

    # Summary stats
    if args.json:
        roles = {}
        jurisdictions = {}
        negated_count = 0
        for w in basis:
            role = w.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
            jur = w.get("jurisdiction", "unclassified")
            jurisdictions[jur] = jurisdictions.get(jur, 0) + 1
            if w.get("negated"):
                negated_count += 1

        print(json.dumps({
            "total_words": len(basis),
            "roles": roles,
            "jurisdictions": jurisdictions,
            "negated_count": negated_count,
        }, indent=2))
        return

    roles = {}
    jurisdictions = {}
    negated_count = 0
    for w in basis:
        role = w.get("role", "unknown")
        roles[role] = roles.get(role, 0) + 1
        jur = w.get("jurisdiction", "unclassified")
        jurisdictions[jur] = jurisdictions.get(jur, 0) + 1
        if w.get("negated"):
            negated_count += 1

    print(f"\n  {c('bold')}720-WORD BASIS SET{c('reset')}")
    print(f"  {c('dim')}{'─' * 50}{c('reset')}")
    print(f"  Total words: {c('bold')}{len(basis)}{c('reset')}")
    print(f"  VCC-negated: {c('red')}{negated_count}{c('reset')}")
    print(f"\n  {c('bold')}Roles:{c('reset')}")
    for role, count in sorted(roles.items(), key=lambda x: -x[1]):
        print(f"    {role:<20} {count}")
    print(f"\n  {c('bold')}Jurisdictions:{c('reset')}")
    for jur, count in sorted(jurisdictions.items(), key=lambda x: -x[1]):
        j_color = c("red") if "sea" in jur.lower() else c("green") if "land" in jur.lower() else c("dim")
        print(f"    {j_color}{jur:<25}{c('reset')} {count}")
    print(f"\n  {c('dim')}Use: qwparse basis --search <word> to explore{c('reset')}\n")


# ---------------------------------------------------------------------------
# Subcommand: eval (built-in documents)
# ---------------------------------------------------------------------------

def cmd_eval(args):
    """Evaluate built-in example documents."""
    evaluate_document, format_evaluation = _import_document_evaluator()
    from document_evaluator import BUILTIN_DOCUMENTS

    if args.list:
        print(f"\n  {c('bold')}Built-in Documents{c('reset')}\n")
        for key, doc in BUILTIN_DOCUMENTS.items():
            print(f"  {c('gold')}{key:<22}{c('reset')} {c('dim')}{doc['title']}{c('reset')}")
        print(f"\n  {c('dim')}Usage: qwparse eval <name> or qwparse eval --all{c('reset')}\n")
        return

    if args.all:
        results = []
        for key, doc in BUILTIN_DOCUMENTS.items():
            result = evaluate_document(doc["text"], doc["title"])
            results.append(result)
            if not args.json:
                print(format_evaluation(result))

        if args.json:
            out = [{k: v for k, v in r.items() if k != "text"} for r in results]
            print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return

    if args.name:
        key = args.name.lower().replace("-", "_").replace(" ", "_")
        if key not in BUILTIN_DOCUMENTS:
            print(f"{c('red')}Unknown: '{args.name}'. Use --list to see options.{c('reset')}")
            sys.exit(1)
        doc = BUILTIN_DOCUMENTS[key]
        result = evaluate_document(doc["text"], doc["title"])
        if args.json:
            out = {k: v for k, v in result.items() if k != "text"}
            print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        else:
            print(format_evaluation(result))
        return

    # Default: list
    cmd_eval(argparse.Namespace(list=True, all=False, name=None, json=False))


# ---------------------------------------------------------------------------
# Dashboard (no-args)
# ---------------------------------------------------------------------------

def show_dashboard():
    """Show overview when qwparse is run with no arguments."""
    print(f"\n  {c('bold')}qwparse{c('reset')} {c('dim')}— quantum word parse{c('reset')}\n")

    # Try to load basis stats
    basis_path = DATA_DIR / "basis_720.json"
    if basis_path.exists():
        with open(basis_path) as f:
            basis = json.load(f)
        neg = sum(1 for w in basis if w.get("negated"))
        print(f"  {c('bold')}{len(basis)}{c('reset')} basis words  "
              f"{c('red')}{neg}{c('reset')} VCC-negated  "
              f"{c('dim')}6! permutations{c('reset')}")
    else:
        print(f"  {c('yellow')}basis not generated yet{c('reset')}")

    # Module status
    modules = [
        ("morpheme_negation", "VCC negation engine"),
        ("word_parser", "Word decomposition"),
        ("sentence_analyzer", "C.S.S.C.P.S.G.P. grading"),
        ("dog_latin_detector", "DOG-LATIN / GLOSSA scanner"),
        ("adverb_verb_detector", "Null chain detection"),
        ("case_analyzer", "Case form → jurisdiction"),
        ("document_evaluator", "Full document evaluation"),
    ]
    print(f"\n  {c('bold')}Engines{c('reset')}")
    for mod, desc in modules:
        try:
            __import__(mod)
            print(f"  {c('green')}{c('reset')} {mod:<24} {c('dim')}{desc}{c('reset')}")
        except Exception:
            print(f"  {c('red')}{c('reset')} {mod:<24} {c('dim')}{desc}{c('reset')}")

    print(f"\n  {c('bold')}Commands{c('reset')}")
    cmds = [
        ("word <words...>", "Decompose words (VCC, morphemes, jurisdiction)"),
        ("sentence <text>", "Grade a sentence (C.S.S.C.P.S.G.P.)"),
        ("scan <file>", "Full document analysis with suggestions"),
        ("scan --dir <path>", "Batch evaluate a directory"),
        ("revise <file>", "Context-free judge → revised document"),
        ("draft <file>", "Full pipeline: revise×2 + DB fill → final"),
        ("dog-latin <text>", "DOG-LATIN / GLOSSA detection"),
        ("nullchain <text>", "Null adverb-verb chain detection"),
        ("case <names...>", "Case form jurisdiction classification"),
        ("basis", "720-word basis summary and search"),
        ("models", "List available AI models"),
        ("eval --list", "Built-in example documents"),
    ]
    for cmd, desc in cmds:
        print(f"    {c('gold')}{cmd:<24}{c('reset')} {c('dim')}{desc}{c('reset')}")

    print(f"\n  {c('bold')}Flags{c('reset')}")
    print(f"    {c('gold')}--json{c('reset')}               {c('dim')}Machine-readable JSON output{c('reset')}")
    print(f"    {c('gold')}--ai{c('reset')}                 {c('dim')}Add AI critique (scan command){c('reset')}")
    print(f"    {c('gold')}--model <id>{c('reset')}         {c('dim')}Choose AI model (see: qwparse models){c('reset')}")
    print(f"    {c('gold')}--no-color{c('reset')}           {c('dim')}Strip ANSI colors (or set NO_COLOR=1){c('reset')}")
    print(f"    {c('gold')}--verbose / -v{c('reset')}       {c('dim')}Include token-level detail{c('reset')}")
    print(f"    {c('gold')}--file / -f <path>{c('reset')}   {c('dim')}Read from file (.md, .txt, .pdf){c('reset')}")

    print(f"\n  {c('dim')}All commands accept stdin: echo \"text\" | qwparse sentence{c('reset')}")
    print(f"  {c('dim')}Project: ~/GitHub/words_quantum_legal{c('reset')}\n")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qwparse",
        description="Quantum Word Parse — structural language analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    sub = parser.add_subparsers(dest="command")

    # word
    p_word = sub.add_parser("word", help="Decompose words into morphemes")
    p_word.add_argument("words", nargs="*", help="Words to parse")
    p_word.add_argument("--json", action="store_true", help="JSON output")
    p_word.add_argument("-v", "--verbose", action="store_true")

    # sentence
    p_sent = sub.add_parser("sentence", help="Analyze sentence structure")
    p_sent.add_argument("text", nargs="*", help="Sentence text")
    p_sent.add_argument("-f", "--file", help="Read from file")
    p_sent.add_argument("--json", action="store_true", help="JSON output")
    p_sent.add_argument("-v", "--verbose", action="store_true")

    # scan
    p_scan = sub.add_parser("scan", help="Full document analysis with suggestions")
    p_scan.add_argument("text", nargs="*", help="Text or filename")
    p_scan.add_argument("-f", "--file", help="Read from file (.md, .txt, .pdf)")
    p_scan.add_argument("-d", "--dir", help="Batch evaluate directory")
    p_scan.add_argument("--ai", action="store_true", help="Add AI critique of the analysis")
    p_scan.add_argument("--model", help="Model ID for AI critique (see: qwparse models)")
    p_scan.add_argument("--json", action="store_true", help="JSON output")
    p_scan.add_argument("-v", "--verbose", action="store_true")

    # revise
    p_rev = sub.add_parser("revise", help="Context-free judge: scan → AI revision")
    p_rev.add_argument("text", nargs="*", help="Text or filename")
    p_rev.add_argument("-f", "--file", help="Read from file (.md, .txt, .pdf)")
    p_rev.add_argument("--model", help="Model ID (see: qwparse models)")
    p_rev.add_argument("-o", "--output", help="Write revised document to file")
    p_rev.add_argument("--json", action="store_true", help="JSON output")
    p_rev.add_argument("-v", "--verbose", action="store_true")

    # draft (full pipeline)
    p_draft = sub.add_parser("draft", help="Full pipeline: revise×2 + DB evidence → final")
    p_draft.add_argument("text", nargs="*", help="Text or filename")
    p_draft.add_argument("-f", "--file", help="Read from file (.md, .txt, .pdf)")
    p_draft.add_argument("--model", help="Model ID (see: qwparse models)")
    p_draft.add_argument("--audience", help="Target audience: judge, opposing_counsel, "
                         "opposing_party, mediator, gal, ardc, clerk, public, self "
                         "(auto-detected if not specified)")
    p_draft.add_argument("--passes", type=int, help="Number of revise passes (default: 2)")
    p_draft.add_argument("-o", "--output", help="Write final document to file")
    p_draft.add_argument("--json", action="store_true", help="JSON output")
    p_draft.add_argument("-v", "--verbose", action="store_true")

    # dog-latin
    p_dl = sub.add_parser("dog-latin", help="DOG-LATIN / GLOSSA detection")
    p_dl.add_argument("text", nargs="*", help="Text to scan")
    p_dl.add_argument("-f", "--file", help="Read from file")
    p_dl.add_argument("--json", action="store_true", help="JSON output")
    p_dl.add_argument("-v", "--verbose", action="store_true")

    # nullchain
    p_nc = sub.add_parser("nullchain", help="Detect null adverb-verb chains")
    p_nc.add_argument("text", nargs="*", help="Text to analyze")
    p_nc.add_argument("-f", "--file", help="Read from file")
    p_nc.add_argument("--json", action="store_true", help="JSON output")
    p_nc.add_argument("-v", "--verbose", action="store_true")

    # case
    p_case = sub.add_parser("case", help="Case form jurisdiction classification")
    p_case.add_argument("names", nargs="*", help="Names/text to classify")
    p_case.add_argument("--compare", action="store_true", help="Show all forms of one name")
    p_case.add_argument("--json", action="store_true", help="JSON output")
    p_case.add_argument("-v", "--verbose", action="store_true")

    # basis
    p_basis = sub.add_parser("basis", help="720-word basis set summary and search")
    p_basis.add_argument("--search", "-s", help="Search within basis")
    p_basis.add_argument("--json", action="store_true", help="JSON output")
    p_basis.add_argument("-v", "--verbose", action="store_true")

    # models
    p_models = sub.add_parser("models", help="List available AI models across providers")
    p_models.add_argument("--json", action="store_true", help="JSON output")
    p_models.add_argument("-v", "--verbose", action="store_true")

    # eval
    p_eval = sub.add_parser("eval", help="Evaluate built-in example documents")
    p_eval.add_argument("name", nargs="?", help="Document name")
    p_eval.add_argument("--list", action="store_true", help="List available documents")
    p_eval.add_argument("--all", action="store_true", help="Evaluate all built-in docs")
    p_eval.add_argument("--json", action="store_true", help="JSON output")
    p_eval.add_argument("-v", "--verbose", action="store_true")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DISPATCH = {
    "word": cmd_word,
    "sentence": cmd_sentence,
    "scan": cmd_scan,
    "revise": cmd_revise,
    "draft": cmd_draft,
    "dog-latin": cmd_dog_latin,
    "nullchain": cmd_nullchain,
    "case": cmd_case,
    "basis": cmd_basis,
    "models": cmd_models,
    "eval": cmd_eval,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.no_color:
        global NO_COLOR
        NO_COLOR = True

    if not args.command:
        show_dashboard()
        return

    handler = DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
