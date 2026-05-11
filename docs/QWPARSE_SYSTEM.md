# QWPARSE — Document Structural Analysis & AI Revision System

## What This Is

`qwparse` is a CLI tool that implements a multi-phase document analysis and revision pipeline. It combines rule-based structural analysis (morpheme decomposition, DOG-LATIN detection, null-chain identification) with context-free AI critique and evidence-backed citation filling from a 2M+ vector database.

The core insight: **a document that can't stand alone in front of a reader with zero context is a weak document.** The pipeline systematically finds and fills those gaps.

---

## The Pipeline

```
qwparse draft document.md --model claude-haiku-4-5-20251001 -o final.md
```

### Phase 1: Structural Scan (rule-based, instant)
Scores the document on parse-syntax purity using the Quantum Verbal Meaning framework:
- VCC negation detection (vowel-consonant prefix = meaning inversion)
- C.S.S.C.P.S.G.P. sentence structure grading
- DOG-LATIN / GLOSSA detection (all-caps without hyphens)
- Null adverb-verb chain detection (commands that state zero facts)
- Jurisdiction classification (land/soil vs sea/water)

### Phase 2: Context-Free Revision (2 passes, AI)
An LLM reads the document with **zero case knowledge** — acting as a judge who only sees what's on the page. Each pass:
1. Identifies deficiencies (unsourced claims, assumed context, emotional framing)
2. Produces a revised document with `[CITE NEEDED: ...]` markers for every gap
3. The second pass deepens the first — expanding citation requirements into specific sub-requirements (what document type, what page, what docket entry)

**Why context-free matters:** When you write with full context (the vector DB, the case history, your lived experience), you bias toward agreement. The context-free judge can't agree — it can only assess whether the document communicates to a stranger. This is the "judge aspect."

### Phase 3: Database Evidence Retrieval
Searches the vector DB for evidence matching the document's factual claims:
- Uses devctl search (BGE + SPLADE + cross-encoder reranking) for ranking
- Enriches results with full source text from `sdata/md/` (up to 3000 chars per result vs 200 chars from CLI)
- Searches across all collections: case_docs (1.7M), legal_docs_v2 (362K), case_facts (16K), claude_code_sessions (68K), whatsapp_chats (19K)

### Phase 4: Citation Fill (AI with evidence)
Passes the revised document + retrieved evidence to the AI with instructions to:
- Fill each `[CITE NEEDED]` with a real citation from the evidence
- Mark `[NO EVIDENCE FOUND]` where the DB has no match
- Insert `[WARNING: evidence contradicts]` if evidence conflicts with a claim

### Phase 5: Dual Scoring
Reports two independent metrics:

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Parse-Syntax** (0-100) | CSSCPSGP structural purity | Fraud detection — does the document use deceptive grammar? |
| **Effectiveness** (0-100) | Practical document quality | Will it survive scrutiny from a judge or opposing counsel? |

Effectiveness dimensions:
- **Citation** — % of claims with verifiable sources
- **Specificity** — dates, dollar amounts, named parties present
- **Completeness** — case number, parties, date, relief requested
- **Stand-alone** — can a stranger follow without context
- **Clarity** — sections, headings, logical organization
- **Factual density** — content words vs filler

---

## The Dual Score Problem

Standard legal English always scores D on parse-syntax because it uses past tense, modal verbs, and pronouns. The parse-syntax score measures structural fraud detection potential — not quality. The effectiveness score measures quality.

| Document type | Parse-Syntax | Effectiveness | Interpretation |
|---------------|-------------|---------------|----------------|
| Court order (received) | F (37) | Low | Structurally deceptive AND poorly constructed |
| Pro se email (original) | D (44) | D (48) | Normal English, no citations |
| Pro se email (after draft) | D (43) | C (65) | Same English, but cited and complete |
| Parse-syntax claim | A (91) | Low | Structurally pure but impractical |

The goal is to maximize effectiveness while being aware of structural patterns. An effectiveness A means: a judge reading cold can verify every claim, follow the logic, and locate every referenced document.

---

## What We Learned Building This

### 1. Context-free iteration converges on real gaps
Each pass finds genuine deficiencies because the AI has no way to fill gaps with assumed knowledge. Pass 1 finds ~15-20 `[CITE NEEDED]` markers. Pass 2 expands those to 40-50 with specific sub-requirements. The gaps are real — they represent places where the document fails the "stranger test."

### 2. The evidence retrieval bottleneck is text length, not ranking
devctl search finds the right documents (BGE + SPLADE + reranking is excellent). The bottleneck was that CLI output truncates to 200 chars. Solution: use the sdata/index.json to map titles → source files and read full text (3000 chars). This 15x increase in context dramatically improves citation fill quality.

### 3. Query source matters for evidence retrieval
Searching with queries from the AI-revised template (which has placeholder text like "lender name" and "specific date") produces garbage results. Searching with the ORIGINAL document's factual claims (which have real names, real numbers, real dates) produces useful evidence. The pipeline uses original-document factual extraction for evidence search.

### 4. The scoring formula needs two dimensions
A single score conflates structural purity with practical quality. The parse-syntax score is valuable for detecting deceptive grammar patterns but useless for measuring whether a revision improved a document. The effectiveness score shows the actual improvement path: Citation 0→70, Stand-alone 50→80, etc.

### 5. DOG-LATIN detection needs markdown awareness
When processing `.md` files, markdown formatting (`**bold**`, `## HEADING`) triggers the DOG-LATIN scanner because it sees all-caps tokens. For files that will be rendered before filing, markdown should be stripped before DOG-LATIN analysis. For files that will be printed as-is, the formatting IS the document and should be scanned.

---

## Architecture

```
~/bin/qwparse → cli/qwparse.py (symlink)
                cli/ai_providers.py (LLM abstraction + DB search)
                cli/effectiveness.py (practical quality scoring)
                src/ (7 analysis engines)
                data/basis_720.json (word basis set)
```

### Available Models (qwparse models)
- **Ollama** (local): gemma4, llama3.1, qwen3.5
- **Anthropic**: Claude Opus 4.6, Sonnet 4.6, Haiku 4.5
- **OpenAI**: GPT-4.1, GPT-4.1 Mini, GPT-4.1 Nano, o3, o4-mini
- **Gemini**: 2.5 Flash, 2.5 Pro

Default model selection prefers cheapest available (Gemini Flash → Haiku → local).

### Commands
```
qwparse                          # dashboard
qwparse word <words>             # morpheme decomposition
qwparse sentence <text>          # CSSCPSGP grading
qwparse scan <file> [--ai]      # structural scan [+ AI critique]
qwparse revise <file>            # context-free judge → revised doc
qwparse draft <file>             # FULL PIPELINE: revise×2 + DB + final
qwparse models                   # list available AI models
qwparse dog-latin <text>         # DOG-LATIN detection
qwparse nullchain <text>         # null chain detection
qwparse case <names>             # case form → jurisdiction
qwparse basis [--search]         # 720-word basis
```

All commands support `--json` for machine-readable output and `--model <id>` for model selection.

---

## Integration Points

### div_legal
- Source documents for analysis (EMAIL_CHAIN_MAY6, CONTEMPT_HEATHER, ARDC_COMPLAINT, etc.)
- sdata/md/ provides full source text for evidence enrichment
- sdata/index.json maps titles to filenames for lookup

### caseledger
- case_docs collection (1.7M vectors, port 7333) is the primary evidence source
- case_facts collection (16K verified facts) provides high-confidence citations
- Pipeline could feed into caseledger's document intelligence engine

### embedded-commands
- The effectiveness score could incorporate embedded command metrics
- A "directive density" or "behavioral influence" layer could be added
- The six cognitive layers framework maps to structural patterns in the document
- Potential metric: how effectively does the document layer directives beneath the "boring surface"

### policy-orchestrator
- devctl search provides the federated vector search infrastructure
- All collections are managed by policy-orchestrator's registry

---

## Challenges & Open Questions

### 1. Citation fill rate
Currently ~30-40% of citations get filled from the DB. The unfilled ones need:
- Specific exhibit numbers (not in any collection)
- Opposing counsel's billing records (not in our possession)
- Lien filing details (in county records, not in DB)

**Path forward:** Ingest more source documents (court filings, exhibits filed) into case_docs. Each new document class added to the corpus improves fill rate.

### 2. The "final execution" gap
The pipeline produces a well-structured, partially-cited document. Getting to a filing-ready version requires:
- Manual fill of remaining `[CITE NEEDED]` from actual case files
- Conversion to court-required format (Cook County e-filing specs)
- Final attorney/pro-se review of legal claims

### 3. Embedded command integration
The `embedded-commands` framework analyzes and constructs influence at six cognitive layers. Currently qwparse treats this as external. A unified scoring that includes:
- **Surface plausibility** (does it look boring/normal?)
- **Directive density** (how many behavioral nudges per paragraph?)
- **Audience projection** (is it calibrated to the reader?)
- **DARVO detection** (does it inadvertently use manipulative patterns?)

...would produce a third scoring dimension: structural × effectiveness × influence.

### 4. Score calibration
The effectiveness weights (citation 25%, specificity 20%, completeness 20%, standalone 15%, clarity 10%, factual 10%) are initial estimates. Need corpus-level validation: score 50+ real documents, compare scores to actual filing outcomes, adjust weights.

### 5. Model selection for cost/quality tradeoff
- Haiku ($0.004/query) produces good critiques but less precise citation filling
- Sonnet ($0.018/query) produces better structured revisions
- Local models (free) are fast but less capable at legal nuance
- Optimal: Haiku for passes 1-2 (critique), Sonnet for pass 4 (citation fill)

---

## Objectives

### Immediate (this sprint)
- [x] CLI deployed to ~/bin/qwparse
- [x] Structural scan working on all document types
- [x] AI critique with multi-model support
- [x] Context-free revision pipeline (2 passes)
- [x] Evidence retrieval from vector DB with full-text enrichment
- [x] Citation filling from DB evidence
- [x] Dual scoring (parse-syntax + effectiveness)
- [ ] Strip markdown before DOG-LATIN scan (optional flag)
- [ ] Embedded-commands influence metric integration

### Next (caseledger integration)
- [ ] Feed qwparse output into caseledger pipeline as a pre-filing stage
- [ ] Use caseledger's fact extraction to validate citations
- [ ] Generate court-format output (PDF, e-filing format)
- [ ] Batch draft across all div_legal filings for consistency audit

### Future (full system)
- [ ] Three-axis scoring: structural × effectiveness × influence
- [ ] Auto-iterate until effectiveness reaches target threshold
- [ ] Multi-document coherence check (do all filings tell consistent story?)
- [ ] Rust port of structural engines for WASM browser deployment
- [ ] Public-facing web tool (Cloudflare Workers + Pages)

---

## Process Notes

The development process itself demonstrates the methodology:
1. Start with structural analysis (rules, no AI)
2. Layer AI as a context-free judge (finds gaps humans miss)
3. Use DB for evidence (grounds the critique in real data)
4. Iterate (each pass deepens, never assumes, always verifies)
5. Score on multiple axes (no single number captures quality)

This mirrors how a filing should be constructed: structure first, then facts, then citations, then review by someone who wasn't involved in drafting.
