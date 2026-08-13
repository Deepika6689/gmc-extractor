# GMC Policy Extraction & QMS Integration

Technical Assessment — AI/LLM Engineering Intern (Document Intelligence), PlanCover.

Extracts structured policy data from Group Medical Cover (GMC) insurance policy
PDFs — issued by different insurers, in different layouts — and maps it into a
single normalized JSON schema matching the QMS field list in the assignment
brief.

## What it does

```
PDF (any insurer, any layout)
   │
   ▼
1. pdf_extractor.py   — text + table extraction per page (pdfplumber),
                         OCR fallback per-page for scanned pages (PyMuPDF + tesseract)
   │
   ▼
2. llm_extractor.py   — Claude (tool-use, forced structured output) reads the
                         full page-tagged text and maps every QMS field, with
                         a source clause + page number attached to each value
   │  (falls back to↓ if no API key is configured)
   ▼
3. rules_extractor.py — regex-based extraction of the handful of fields that
                         are reliably labeled across insurers (insurer name,
                         TPA, policy number, dates, premium) — guarantees the
                         pipeline still produces output with zero API cost/key
   │
   ▼
4. schema.py           — pydantic model enforced on every output, so the JSON
                          shape never varies file-to-file regardless of source
                          insurer or which engine produced it
   │
   ▼
output/<filename>.json
```

## Why this approach (methodology)

**The core problem stated in the brief is layout variance, not text extraction.**
All five sample PDFs are digitally generated (not scans), so raw text extraction
itself is not the hard part — pdfplumber handles that reliably, with a per-page
OCR fallback (PyMuPDF rasterization → tesseract) wired in for the scanned pages
that *will* show up in a real 50-80 page renewal pack (signed endorsements,
stamped annexures, etc.), even though none of the provided samples needed it.

**The hard part is that "Room Rent" in one insurer's schedule is a table row,
in another it's a paragraph, and in a third it's an abbreviation in a benefits
grid.** A hand-rolled regex/rules library would need a branch per insurer per
field, and breaks the moment a sixth insurer's template shows up — exactly the
"rigid, single-insurer template" problem the assignment explicitly says to
avoid. An LLM reading the full extracted text (including flattened tables)
generalizes across phrasing the way a human policy analyst would, which is why
the extraction core is Claude with **forced tool-use** against the same
pydantic schema (`schema.py`) that defines the JSON output — this guarantees
every response is valid, schema-conformant JSON rather than free-text that
needs a second parsing pass.

**Every extracted benefit field carries its source clause and page number**
(`raw_text`, `source_page` on every `CoverageField`). This directly targets the
"Data Structuring... requiring minimal to no human intervention" evaluation
criterion: a QMS reviewer doesn't have to re-open the 80-page PDF to sanity-check
a value — they can see exactly which sentence produced it.

**Nulls over guesses.** If a benefit isn't mentioned in a given policy, the field
stays `null` rather than being inferred from a default or a similar-sounding
clause elsewhere in the document. A wrong high-confidence-looking value is worse
than an honest "not found" in an insurance compliance context.

**Rules-based fallback (`rules_extractor.py`)** exists so the pipeline degrades
gracefully with zero API key/cost — useful for a first-pass sanity check on a
new insurer template, or if the LLM call fails/times out mid-batch. It only
attempts the fields that are consistently labeled across insurers (insurer
name, TPA, policy number, dates, premium); it deliberately does **not** attempt
benefit-level fields, since that's precisely the brittle-template trap this
whole approach is designed to avoid.

## Setup

```bash
# System dependency (OCR fallback path only)
sudo apt-get install tesseract-ocr poppler-utils

# Python dependencies
pip install -r requirements.txt

# Enable full LLM extraction (recommended — see "Running without an API key" below)
export ANTHROPIC_API_KEY=sk-ant-...
```

## Running (CLI)

```bash
cd src
python main.py --input ../samples --output ../output
```

- `--input` accepts either a single PDF or a directory of PDFs.
- One JSON file is written per input PDF, plus a `_run_summary.json` listing
  which engine ran on each file and whether it succeeded.

### Running without an API key

If `ANTHROPIC_API_KEY` isn't set, the pipeline automatically runs in
rules-only mode (`--no-llm` also forces this explicitly) — every file still
produces valid schema-shaped JSON, with `policy_metadata` populated
(insurer, TPA, policy number, dates, premium where present) and benefit
fields left `null`, clearly flagged via `extraction_meta.engine_used`.

## Running (Web UI)

A small Flask console lets you drag-drop a PDF and browse the result as an
audit-friendly document — every extracted value shown with its status, its
limit, and (click "view source clause") the exact sentence and page number
it came from — instead of raw JSON.

```bash
pip install flask
cd webapp
python app.py
```

Then open **http://localhost:5000**.

- If `ANTHROPIC_API_KEY` is already set in your environment, uploads run
  full LLM extraction automatically.
- Otherwise, paste a key into the "Anthropic API key" field in the top
  bar and click **Use key** — it's held in server memory for that run only
  and is never written to disk.
- Previously processed files (including ones run via the CLI into
  `output/`) show up automatically in the left-hand file list.

## Known scaling points (not implemented in this v1, called out intentionally)

- **Chunking for very long documents.** The LLM call currently sends the
  full document text in a single request. This comfortably fits an 80-page
  policy in Claude's context window, so it wasn't built for v1 — but a
  production version processing hundreds of policies per batch would want a
  page-window chunking + merge strategy to control per-call token cost.
- **Cross-check scoring.** `rules_extractor.py`'s output is currently a
  standalone fallback path rather than being diffed against the LLM pass
  automatically; wiring the two together into an agreement/confidence score
  per field would strengthen the "Accuracy" evaluation story further.
- **Multi-document policies.** Some GMC packs bundle a personal-accident
  rider PDF alongside the base GMC schedule (as in the sample set). This
  version processes each PDF independently; a production version would
  likely want an explicit "which PDF is the base GMC vs. a rider" classification
  step before merging results per employer.

## Project structure

```
gmc-extractor/
├── src/
│   ├── schema.py           # pydantic output schema (QMS field mapping)
│   ├── pdf_extractor.py    # text/table extraction + OCR fallback
│   ├── llm_extractor.py    # Claude tool-use structured extraction
│   ├── rules_extractor.py  # zero-API-key regex fallback
│   └── main.py             # CLI entrypoint
├── webapp/
│   ├── app.py               # Flask backend (wraps src/ pipeline)
│   ├── templates/index.html
│   ├── static/style.css
│   ├── static/app.js
│   └── uploads/             # PDFs uploaded via the UI land here
├── samples/                # provided sample GMC policy PDFs
├── output/                 # generated JSON per PDF (+ run summary) — read by both CLI and UI
├── requirements.txt
└── README.md
```
