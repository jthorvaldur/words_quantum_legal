"""influence.py — Behavioral influence scoring via embedded-commands.

Analyzes documents for cognitive layer targeting, embedded command density,
DARVO patterns, and AI language tells. Provides a third scoring axis
alongside parse-syntax (structural) and effectiveness (practical).

The six cognitive layers (Chase Hughes framework):
  1. Conscious  — logical reasoning, facts (the "boring surface")
  2. Emotional  — feelings, associations
  3. Identity   — self-concept, role, ego
  4. Social     — group belonging, norms
  5. Temporal   — past/future anchoring
  6. Somatic    — pace, tone, rhythm

A well-constructed document targets multiple layers simultaneously while
maintaining a boring, professional surface (Layer 1) that conceals the
deeper targeting.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Try to import from embedded-commands
EMBED_AVAILABLE = False
_detect_patterns = None
_detect_darvo = None
_analyze_layers = None
_detect_ai_tells = None

try:
    embed_src = Path.home() / "GitHub" / "embedded-commands" / "src"
    if str(embed_src) not in sys.path:
        sys.path.insert(0, str(embed_src))
    from embedded_commands.cli import (
        _detect_patterns as dp,
        _detect_darvo as dd,
        _analyze_layers as al,
        _detect_ai_tells as dat,
    )
    _detect_patterns = dp
    _detect_darvo = dd
    _analyze_layers = al
    _detect_ai_tells = dat
    EMBED_AVAILABLE = True
except (ImportError, Exception):
    pass


# ---------------------------------------------------------------------------
# Layer definitions (mirrors embedded-commands)
# ---------------------------------------------------------------------------

LAYERS = ["conscious", "emotional", "identity", "social", "temporal", "somatic"]

LAYER_LABELS = {
    "conscious": "Conscious (facts, logic)",
    "emotional": "Emotional (feelings, associations)",
    "identity": "Identity (role, ego, self-concept)",
    "social": "Social (belonging, norms, pressure)",
    "temporal": "Temporal (past/future framing)",
    "somatic": "Somatic (pace, rhythm, tone)",
}

# ---------------------------------------------------------------------------
# Audience profiles — who reads this document?
# ---------------------------------------------------------------------------
# Each audience has different cognitive receptors. The "ideal" weights
# represent where influence is most effective for that reader.

AUDIENCE_PROFILES = {
    "judge": {
        "label": "Judge / Court",
        "conscious": 0.40,    # Primary — judges want facts/logic/evidence
        "identity": 0.25,     # "I am fair, I protect due process"
        "temporal": 0.15,     # Deadlines, urgency, consequences
        "social": 0.10,       # Norms, what other judges would do
        "emotional": 0.05,    # Minimal — judges resist emotional appeals
        "somatic": 0.05,      # Pacing, structure, readability
    },
    "opposing_counsel": {
        "label": "Opposing Counsel",
        "identity": 0.30,     # "I am a zealous advocate / fiduciary"
        "social": 0.25,       # Bar rules, professional reputation, norms
        "conscious": 0.20,    # Costs, math, practical consequences
        "temporal": 0.15,     # Deadlines, billing clocks, case timeline
        "emotional": 0.05,    # Minimal — professionals resist
        "somatic": 0.05,
    },
    "opposing_party": {
        "label": "Opposing Party (direct)",
        "emotional": 0.30,    # Fear, hope, children, future
        "temporal": 0.25,     # "Your share shrinks every month"
        "conscious": 0.20,    # Hard numbers, net recovery math
        "identity": 0.15,     # "A good mother would..."
        "social": 0.05,       # What friends/family think
        "somatic": 0.05,
    },
    "mediator": {
        "label": "Mediator",
        "social": 0.30,       # Fairness, balance, resolution norms
        "temporal": 0.25,     # "Let's move forward, save time"
        "conscious": 0.20,    # Facts that show reasonableness
        "emotional": 0.15,    # Children's welfare, family stability
        "identity": 0.05,     # Neutral — mediators resist identity plays
        "somatic": 0.05,
    },
    "gal": {
        "label": "Guardian ad Litem",
        "emotional": 0.35,    # Children's wellbeing, safety, stability
        "conscious": 0.25,    # Facts about parenting, environment
        "identity": 0.20,     # "I protect children"
        "social": 0.10,       # Community standards for parenting
        "temporal": 0.05,     # History of care
        "somatic": 0.05,
    },
    "ardc": {
        "label": "ARDC / Disciplinary Body",
        "conscious": 0.35,    # Evidence of rule violations, specifics
        "social": 0.30,       # Professional standards, Rules of Conduct
        "identity": 0.15,     # "We uphold the profession"
        "temporal": 0.10,     # Pattern over time, deadlines missed
        "emotional": 0.05,    # Minimal — bureaucratic body
        "somatic": 0.05,
    },
    "clerk": {
        "label": "Court Clerk / E-filing",
        "conscious": 0.50,    # Procedural compliance, format, rules
        "temporal": 0.25,     # Filing deadlines, timely service
        "social": 0.15,       # Local rules, standard practice
        "identity": 0.05,
        "emotional": 0.00,
        "somatic": 0.05,
    },
    "public": {
        "label": "Public / Media",
        "emotional": 0.35,    # Outrage, sympathy, narrative
        "social": 0.25,       # Community values, "anyone could be next"
        "identity": 0.15,     # Reader identifies with the victim
        "conscious": 0.10,    # Just enough facts for credibility
        "temporal": 0.10,     # Urgency, "happening now"
        "somatic": 0.05,
    },
    "self": {
        "label": "Internal / Strategy Document",
        "conscious": 0.30,    # Clarity of thinking
        "temporal": 0.25,     # Timeline, next steps, deadlines
        "identity": 0.15,     # Role definition
        "social": 0.15,       # Who else is involved
        "emotional": 0.10,    # Motivation
        "somatic": 0.05,
    },
}

ALL_AUDIENCES = list(AUDIENCE_PROFILES.keys())


# ---------------------------------------------------------------------------
# Audience auto-detection
# ---------------------------------------------------------------------------

def detect_audience(text: str) -> str:
    """Detect the most likely intended audience from document content.

    Returns the audience key (e.g., "judge", "opposing_counsel").
    """
    text_lower = text.lower()
    first_500 = text_lower[:500]

    scores: dict[str, int] = {a: 0 for a in ALL_AUDIENCES}

    # Judge signals
    if any(s in first_500 for s in ['your honor', 'this court', 'respectfully',
                                     'motion', 'petition', 'prayer for relief']):
        scores["judge"] += 5
    if re.search(r'(?:IT IS|HEREBY)\s+(?:ORDERED|ADJUDGED)', text):
        scores["judge"] += 3
    if re.search(r'(?:VERIFIED|PETITION|MOTION|MEMORANDUM|BRIEF)', text[:200]):
        scores["judge"] += 4

    # Opposing counsel signals
    if any(s in first_500 for s in ['counsel,', 'dear counsel', 'your firm',
                                     'your client', 'opposing counsel']):
        scores["opposing_counsel"] += 5
    if re.search(r'(?:fiduciary|billable|hourly rate|your fees)', text_lower):
        scores["opposing_counsel"] += 3
    if 'pro se' in text_lower and 'your firm' in text_lower:
        scores["opposing_counsel"] += 2

    # Opposing party signals
    if re.search(r'(?:dear\s+(?:heather|joel))', first_500):
        scores["opposing_party"] += 5
    if 'ourfamilywizard' in text_lower and 'counsel' not in first_500:
        scores["opposing_party"] += 3

    # Mediator signals
    if any(s in first_500 for s in ['mediator', 'mediation', 'neutral']):
        scores["mediator"] += 5
    if 'resolution' in text_lower and 'settlement' in text_lower:
        scores["mediator"] += 2

    # GAL signals
    if any(s in first_500 for s in ['guardian ad litem', 'gal ', 'best interest of the child']):
        scores["gal"] += 5
    if re.search(r'(?:children|parenting|custody|visitation)', text_lower[:300]):
        scores["gal"] += 2

    # ARDC signals
    if any(s in text_lower for s in ['ardc', 'attorney registration',
                                      'disciplinary', 'rule 137', 'rule 219',
                                      'professional conduct']):
        scores["ardc"] += 5
    if 'complaint' in text_lower and any(s in text_lower for s in ['attorney', 'counsel', 'rule']):
        scores["ardc"] += 3

    # Clerk signals
    if any(s in first_500 for s in ['e-filing', 'clerk', 'certificate of service']):
        scores["clerk"] += 5

    # Public signals
    if any(s in first_500 for s in ['dear editor', 'press', 'public statement']):
        scores["public"] += 5

    # Self / strategy signals
    if any(s in first_500 for s in ['strategy', 'next steps', 'todo', 'plan',
                                     'ready to send', 'draft']):
        scores["self"] += 4

    # Return highest-scoring audience, default to judge
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "judge"  # Safe default
    return best


@dataclass
class InfluenceScore:
    """Multi-layer influence assessment."""
    total: int = 0          # 0-100 composite
    grade: str = "?"

    # Layer scores (0-100 each, based on signal density)
    layers: dict = field(default_factory=dict)
    layers_targeted: int = 0    # How many of the 6 layers are active

    # Pattern metrics
    pattern_count: int = 0      # Embedded command patterns found
    ai_tell_count: int = 0      # AI-generated language signals
    darvo_score: int = 0        # 0-3 DARVO severity

    # Audience alignment (optional)
    audience: str = ""          # Target audience if specified
    audience_alignment: int = 0  # 0-100 how well it matches ideal profile

    # Warnings
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def score_influence(text: str, audience: str = "judge") -> InfluenceScore:
    """Score a document's behavioral influence effectiveness.

    Uses embedded-commands framework if available, falls back to
    heuristic analysis.
    """
    s = InfluenceScore()
    s.audience = audience

    if EMBED_AVAILABLE:
        s = _score_with_embed(text, audience)
    else:
        s = _score_heuristic(text, audience)

    return s


def _score_with_embed(text: str, audience: str) -> InfluenceScore:
    """Score using the full embedded-commands library."""
    s = InfluenceScore()
    s.audience = audience

    # Analyze layers
    layer_hits = _analyze_layers(text)
    for layer in LAYERS:
        hits = layer_hits.get(layer, [])
        # Score each layer 0-100 based on signal count
        s.layers[layer] = min(100, len(hits) * 15)

    s.layers_targeted = sum(1 for l in LAYERS if s.layers.get(l, 0) > 0)

    # Patterns
    patterns = _detect_patterns(text)
    s.pattern_count = len(patterns)

    # AI tells
    ai_tells = _detect_ai_tells(text)
    s.ai_tell_count = len(ai_tells)
    if s.ai_tell_count > 3:
        s.warnings.append(f"{s.ai_tell_count} AI language tells detected — "
                         "may undermine credibility")

    # DARVO
    darvo = _detect_darvo(text)
    s.darvo_score = darvo.get("score", 0)
    if s.darvo_score >= 2:
        s.warnings.append(f"DARVO score {s.darvo_score}/3 — review for "
                         "inadvertent manipulation patterns")

    # Audience alignment
    profile = AUDIENCE_PROFILES.get(audience, AUDIENCE_PROFILES["judge"])
    alignment = 0.0
    total_weight = 0.0
    for layer, ideal_weight in profile.items():
        if layer == "label":
            continue
        layer_score = s.layers.get(layer, 0) / 100.0
        alignment += layer_score * ideal_weight
        total_weight += ideal_weight
    s.audience_alignment = min(100, int((alignment / max(total_weight, 0.01)) * 100))

    # Composite score
    # Layers targeted (breadth) + pattern density + audience alignment - AI tells
    breadth = min(100, s.layers_targeted * 17)  # 6 layers = 100
    density = min(100, s.pattern_count * 10)    # 10+ patterns = 100
    ai_penalty = min(30, s.ai_tell_count * 10)  # Heavy penalty for AI tells

    s.total = int(
        breadth * 0.25 +
        density * 0.20 +
        s.audience_alignment * 0.40 +
        max(0, 100 - ai_penalty) * 0.15
    )
    # DARVO penalty for outgoing docs (you don't want to accidentally DARVO)
    if s.darvo_score >= 2:
        s.total = max(0, s.total - 15)

    # Grade
    if s.total >= 80:
        s.grade = "A"
    elif s.total >= 65:
        s.grade = "B"
    elif s.total >= 50:
        s.grade = "C"
    elif s.total >= 35:
        s.grade = "D"
    else:
        s.grade = "F"

    return s


def _score_heuristic(text: str, audience: str) -> InfluenceScore:
    """Fallback scoring when embedded-commands library is not available.

    Uses regex-based heuristics for basic layer detection.
    """
    s = InfluenceScore()
    s.audience = audience

    # Heuristic layer detection
    layer_signals = {
        "conscious": [
            r'\$[\d,]+', r'\d+%', r'(?:evidence|fact|record|document|exhibit)',
            r'(?:pursuant|therefore|accordingly|specifically)',
        ],
        "emotional": [
            r'(?:children|family|welfare|harm|suffer|devastating)',
            r'(?:fear|hope|concern|worry|relief|anger)',
        ],
        "identity": [
            r'(?:fiduciary|duty|obligation|professional|ethical)',
            r'(?:your role|as counsel|your client)',
        ],
        "social": [
            r'(?:Rule \d+|Supreme Court|ARDC|professional conduct)',
            r'(?:reasonable|standard|expected|normal practice)',
        ],
        "temporal": [
            r'(?:deadline|by \w+ \d+|before|after|within \d+)',
            r'(?:every \w+ (?:month|day|hour)|continued|ongoing)',
        ],
        "somatic": [
            r'(?:---|\*\*\*|#{2,})',  # structural breaks = pacing
            r'(?:pause|consider|stop|look at)',
        ],
    }

    for layer, patterns in layer_signals.items():
        count = sum(len(re.findall(p, text, re.I)) for p in patterns)
        s.layers[layer] = min(100, count * 10)

    s.layers_targeted = sum(1 for l in LAYERS if s.layers.get(l, 0) > 0)

    # Simple AI tell detection
    ai_tells = ['delve', 'tapestry', 'landscape', 'unlock', 'journey',
                'navigating', 'it\'s worth noting', 'furthermore',
                'robust', 'seamless']
    s.ai_tell_count = sum(1 for t in ai_tells if t in text.lower())

    # Audience alignment
    profile = AUDIENCE_PROFILES.get(audience, AUDIENCE_PROFILES["judge"])
    alignment = 0.0
    for layer, ideal_weight in profile.items():
        if layer == "label":
            continue
        layer_score = s.layers.get(layer, 0) / 100.0
        alignment += layer_score * ideal_weight
    s.audience_alignment = min(100, int(alignment * 100))

    # Composite
    breadth = min(100, s.layers_targeted * 17)
    s.total = int(breadth * 0.30 + s.audience_alignment * 0.50 +
                  max(0, 100 - s.ai_tell_count * 10) * 0.20)

    if s.total >= 80:
        s.grade = "A"
    elif s.total >= 65:
        s.grade = "B"
    elif s.total >= 50:
        s.grade = "C"
    elif s.total >= 35:
        s.grade = "D"
    else:
        s.grade = "F"

    return s


def format_influence(score: InfluenceScore) -> str:
    """Format influence score for terminal display."""
    lines = []
    gc = "\033[32m" if score.grade in ("A", "B") else "\033[33m" if score.grade == "C" else "\033[31m"
    lines.append(f"  {gc}INFLUENCE: {score.total}/100 ({score.grade})\033[0m"
                 f"  \033[90maudience: {score.audience}\033[0m")
    lines.append("")

    # Layer bars
    for layer in LAYERS:
        val = score.layers.get(layer, 0)
        bar = _bar(val)
        vc = "\033[32m" if val >= 50 else "\033[33m" if val >= 20 else "\033[90m"
        label = LAYER_LABELS.get(layer, layer)
        lines.append(f"    {label:<38} {vc}{bar} {val:>3}\033[0m")

    lines.append("")
    lines.append(f"    Layers active:     {score.layers_targeted}/6")
    lines.append(f"    Patterns found:    {score.pattern_count}")
    lines.append(f"    Audience fit:      {score.audience_alignment}/100 "
                 f"({score.audience})")

    if score.ai_tell_count > 0:
        lines.append(f"    \033[33mAI tells:          {score.ai_tell_count} "
                     f"(credibility risk)\033[0m")
    if score.darvo_score > 0:
        dc = "\033[31m" if score.darvo_score >= 2 else "\033[33m"
        lines.append(f"    {dc}DARVO:             {score.darvo_score}/3\033[0m")

    if score.warnings:
        lines.append("")
        for w in score.warnings:
            lines.append(f"    \033[33m⚠ {w}\033[0m")

    return "\n".join(lines)


def _bar(val: int, width: int = 15) -> str:
    filled = int(val / 100 * width)
    return "█" * filled + "░" * (width - filled)
