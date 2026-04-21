# words_quantum_legal

Computational framework for analyzing English words, sentences, and legal documents
through the lens of **Correct-Sentence-Structure-Communication-Parse-Syntax-Grammar-Performance**
(C.-S.-S.-C.-P.-S.-G.-P.) as formalized by :David-Wynn: Miller and :Russell-Jay: Gould.

## What This Does

Every word is a contract. Every sentence is a vessel. This repo provides tools to:

1. **Decompose words** into prefix/root/suffix with etymological and jurisdictional analysis
2. **Detect DOG-LATIN** (GLOSSA) — the fraudulent all-caps text on birth certificates, court orders, driver licenses
3. **Analyze sentence structure** against C.S.S.C.P.S.G.P. rules
4. **Find null constructions** — adverb-verb chains that say nothing
5. **Evaluate legal documents** — Declaration of Independence, court orders, mortgages, etc.
6. **Map the 720-word basis** — the foundational vocabulary of quantum verbal meaning

## The 720-Word Basis

720 = 6! (6 factorial) = permutations of the 6 fundamental sentence positions:

`[Preposition] [Article] [Adjective] [Noun] [Verb-gerund] [Adverb]`

These 720 words form a **basis set** from which all legal and contractual meaning
can be constructed or deconstructed.

---

## Runnables

All executables are in `src/`. Run from the repo root.

### 1. Generate the 720-Word Basis

```bash
python src/basis_generator.py
# Output: data/basis_720.json
# Shows summary stats: words by role, jurisdiction, now-time validity
```

### 2. Parse Any Word

```bash
# Interactive mode
python src/word_parser.py

# Single word
python src/word_parser.py "mortgage"
# → mort (death) + gage (pledge) = DEATH GRIP

python src/word_parser.py "government"
# → govern (steer a SHIP) + ment (mind) = MIND CONTROL

python src/word_parser.py "understand"
# → under (below) + stand = STAND BENEATH = submit to authority
```

### 3. Analyze Sentence Structure (C.S.S.C.P.S.G.P.)

```bash
# Interactive mode
python src/sentence_analyzer.py

# Analyze a sentence
python src/sentence_analyzer.py "The court hereby orders that you shall pay"

# Run built-in examples (correct vs fraudulent)
python src/sentence_analyzer.py --examples

# Analyze a file
python src/sentence_analyzer.py --file document.txt
```

### 4. Detect Adverb-Verb Null Chains

```bash
# Does the sentence say anything?
python src/adverb_verb_detector.py "The court hereby orders that you shall forthwith pay"
# → NULL CHAIN detected. Adverb-verb soup. Zero facts conveyed.

# Run example comparisons
python src/adverb_verb_detector.py --examples

# Scan a file
python src/adverb_verb_detector.py --file document.txt
```

### 5. Detect DOG-LATIN / GLOSSA

```bash
# Interactive mode
python src/dog_latin_detector.py

# Scan text
python src/dog_latin_detector.py "JOHN DOE appeared before THE COURT"

# Scan a file
python src/dog_latin_detector.py --file document.txt
```

### 6. Evaluate Legal Documents

```bash
# List built-in documents
python src/document_evaluator.py --list

# Evaluate specific documents
python src/document_evaluator.py --builtin declaration        # Declaration of Independence
python src/document_evaluator.py --builtin constitution_preamble  # US Constitution
python src/document_evaluator.py --builtin first_amendment    # First Amendment
python src/document_evaluator.py --builtin court_order        # Sample court order
python src/document_evaluator.py --builtin mortgage           # Sample mortgage contract
python src/document_evaluator.py --builtin birth_certificate  # Birth certificate language
python src/document_evaluator.py --builtin traffic_ticket     # Traffic citation
python src/document_evaluator.py --builtin correct_parse_syntax  # Correct form example

# Evaluate ALL built-in documents
python src/document_evaluator.py --all

# Evaluate a custom file
python src/document_evaluator.py --file path/to/document.txt
```

### 7. Case/Hyphen Jurisdiction Analyzer

```bash
# Interactive mode
python src/case_analyzer.py --interactive

# Analyze specific forms
python src/case_analyzer.py "JOHN DOE" ":John-Doe:" "John Doe" "john doe"

# Run built-in comparisons
python src/case_analyzer.py --compare
```

### 8. Generate Basis Map (HTML Visualization)

```bash
python src/basis_map_viz.py
# Output: data/basis_map.html
# Open in browser for interactive word map
```

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| **DOG-LATIN** | Unhyphenated all-caps text = dead jurisdiction = fraud |
| **GLOSSA** | The all-uppercase overlay on legal documents |
| **Parse-Syntax** | Breaking words into prefix/root/suffix to expose true meaning |
| **Now-Time** | Only present tense is factual; past/future = fiction |
| **Null Chain** | Adverb-verb sequences that convey zero facts |
| **Maritime Box** | Birth(berth) → dock(tor) → current(cy) → bank → mort(gage) |
| **Lawful vs Legal** | Land/common law vs sea/admiralty/statute |
| **Justinian Deception** | 530-565 AD codification that merged maritime law with governance |

## Sources

- :David-Wynn: Miller — Quantum-Language-Parse-Syntax-Grammar
- :Russell-Jay: Gould — [LastFlagStanding.com](https://lastflagstanding.com)
- Romley Stewart — [Justinian Deception](https://justiniandeception.wordpress.com)
- TASA — [American States Assembly](https://tasa.americanstatenationals.org)
- Black's Law Dictionary, 4th Edition
- Chicago Manual of Styles, 16th Ed., Art. 11:147

---

## Project Structure

```
words_quantum_legal/
├── CLAUDE.md                    # Project specification
├── README.md                    # This file
├── data/
│   ├── basis_720.json           # Generated 720-word basis (run basis_generator.py)
│   ├── basis_map.html           # Generated HTML visualization (run basis_map_viz.py)
│   └── parse_rules.json         # C.S.S.C.P.S.G.P. rules
├── docs/
│   ├── justinian_timeline.md    # Justinian hijack of time
│   ├── maritime_box.md          # Birth-to-court metaphor
│   ├── lawful_vs_legal.md       # Jurisdiction taxonomy
│   └── word_decomposition.md    # Case/hyphen mechanics
└── src/
    ├── basis_generator.py       # Generate 720-word basis
    ├── word_parser.py           # Parse any word
    ├── sentence_analyzer.py     # C.S.S.C.P.S.G.P. sentence analysis
    ├── adverb_verb_detector.py  # Null chain detection
    ├── dog_latin_detector.py    # DOG-LATIN / GLOSSA scanner
    ├── document_evaluator.py    # Full document evaluation
    ├── case_analyzer.py         # Case/hyphen jurisdiction
    └── basis_map_viz.py         # HTML basis map generator
```
