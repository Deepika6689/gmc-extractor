# GMC Policy Extraction & QMS Integration
Extracts structured policy data from Group Medical Cover (GMC) insurance policy
PDFs — issued by different insurers, in different layouts — and maps it into a
single normalized JSON schema matching the QMS field list in the assignment
brief.

## What it does
```
PDF (any insurer, any layout)
│
▼

pdf_extractor.py — text + table extraction per page (pdfplumber),
OCR fallback per-page for scanned pages (PyMuPDF + tesseract)
│
▼
gemini_extractor.py — Gemini (free tier) reads the full page-tagged text
or llm_extractor.py and maps every QMS field, with a source clause + page
(Anthropic, paid) number attached to each value. Auto-selects whichever
API key is available (Gemini preferred, it's free).
│ (falls back to↓ if no API key is configured)
▼
rules_extractor.py — regex-based extraction of the handful of fields that
are reliably labeled across insurers (insurer name,
TPA, policy number, dates, premium) — guarantees the
pipeline still produces output with zero API cost/key
│
▼
schema.py — pydantic model enforced on every output, so the JSON
shape never varies file-to-file regardless of source
insurer or which engine produced it
│
▼
enrichment.py — post-processing pass that fills in derivable fields
(e.g. policy_tenure computed from start/end dates)
when the document doesn't state them explicitly
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
the extraction core forces structured output against the same pydantic schema
(`schema.py`) that defines the JSON output — this guarantees every response is
valid, schema-conformant JSON rather than free-text that needs a second parsing
pass.

**Two LLM providers are supported, with automatic selection.** Anthropic's
Claude uses forced tool-use for provider-side constrained decoding. Google's
Gemini is used as the default/preferred engine specifically because it's
available on a **free tier with no credit card required** — see
`gemini_extractor.py`'s docstring for a real platform limitation this project
ran into and worked around: Gemini's `response_schema` constrained-decoding
mode rejects this schema outright (`400 INVALID_ARGUMENT: ... too many states
for serving`, a hard limit given schema.GMCExtraction's ~40 repeated nested
objects). The fix was to request free-form JSON instead, show the model an
exact empty-shape example in the prompt, and validate the response against
the same pydantic model client-side — enforcing the schema guarantee outside
the API rather than relying on Gemini's built-in constraint.

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

# Enable full LLM extraction — pick ONE:

# Option A (free, no credit card) — Google AI Studio
#   Get a key at https://aistudio.google.com -> "Get API key"
export GEMINI_API_KEY=AIza...

# Option B (paid) — Anthropic
#   Get a key at https://console.anthropic.com -> API Keys
export ANTHROPIC_API_KEY=sk-ant-...
```

If both are set, the pipeline prefers Gemini by default (`--provider auto`, the
default) since it's free-tier; pass `--provider anthropic` to force Claude instead.

## Running (CLI)

```bash
cd src
python main.py --input ../samples --output ../output
```

- `--provider auto` (default) picks Gemini if `GEMINI_API_KEY`/`GOOGLE_API_KEY`
  is set, else Anthropic if `ANTHROPIC_API_KEY` is set, else falls back to
  rules-only.
- Force a specific engine with `--provider gemini`, `--provider anthropic`, or
  `--provider rules`.
- `--input` accepts either a single PDF or a directory of PDFs.
- One JSON file is written per input PDF, plus a `_run_summary.json` listing
  which engine ran on each file and whether it succeeded.

### Running without an API key

If no key is set, the pipeline automatically runs in rules-only mode
(`--provider rules` also forces this explicitly) — every file still produces
valid schema-shaped JSON, with `policy_metadata` populated (insurer, TPA,
policy number, dates, premium where present) and benefit fields left `null`,
clearly flagged via `extraction_meta.engine_used`.

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

- If `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` is already set in your environment,
  uploads run full LLM extraction automatically (Gemini preferred if both are set).
- Otherwise, paste a key into the **Gemini** field (free, no card) or the
  **Anthropic** field (paid) in the top bar and click **Use** — it's held in
  server memory for that run only and is never written to disk.
- Previously processed files (including ones run via the CLI into
  `output/`) show up automatically in the left-hand file list.

## Post-extraction enrichment

`src/enrichment.py` runs after every extraction (regardless of which engine
produced it) and fills in `policy_tenure` from `inception_or_renewal_date` /
`policy_end_date` when the document states a start/end date but never spells
out the tenure explicitly — common across the sample set, where policies
give exact dates and leave the reader to work out it's "1 Year(s)". It only
fills the field when it's genuinely empty; a tenure the model actually found
stated in the text is never overwritten. The computed value is labeled
`"1 Year(s) (computed from 02-Apr-2022 → 01-Apr-2023)"` rather than a bare
`"1 Year(s)"`, so a reviewer can immediately tell it was derived, not
extracted verbatim — keeping with the "trace every value back to its
source" principle used throughout this schema.

## Known scaling points (not implemented in this v1, called out intentionally)

- **Gemini's `response_schema` constrained-decoding mode cannot be used directly
  with this schema.** `schema.GMCExtraction` has ~40 repeated nested
  `CoverageField` objects; passing it as Gemini's `response_schema` throws
  `400 INVALID_ARGUMENT: ... too many states for serving` — a hard limit in
  Gemini's schema compiler, not something tunable via token limits or field
  descriptions. `gemini_extractor.py` works around this by requesting
  free-form JSON (`response_mime_type="application/json"` with no
  `response_schema`) and showing the model an exact empty-shape example of
  the target JSON in the prompt instead — the response is then validated
  against the same pydantic model used everywhere else, so the guarantee of
  schema-conformant output is enforced on the client side rather than by the
  API. Anthropic's tool-use path doesn't hit this limit and still uses
  provider-side constrained decoding.
- **Chunking for very long documents.** The LLM call currently sends the
  full document text in a single request. This comfortably fits an 80-page
  policy in context, so it wasn't built for v1 — but a production version
  processing hundreds of policies per batch would want a page-window
  chunking + merge strategy to control per-call token cost.
- **Cross-check scoring.** `rules_extractor.py`'s output is currently a
  standalone fallback path rather than being diffed against the LLM pass
  automatically; wiring the two together into an agreement/confidence score
  per field would strengthen the "Accuracy" evaluation story further.
- **Metro / Non-Metro delivery labeling is sometimes an assumption, not a
  fact.** Several sample policies state a single flat maternity limit for
  "Normal Delivery" and "C-Section" with no metro/non-metro distinction in
  the source text at all. When that happens, the model has to place the
  value into one of the two schema slots (metro or non-metro) since the
  document doesn't say — and it has been observed to pick differently across
  documents (e.g. non-metro in one Care Health policy, metro in a Niva Bupa
  policy) purely because the source gives no signal either way. The rupee
  values extracted in these cases are accurate; only the metro/non-metro
  bucket assignment is an unavoidable guess when the source doesn't
  distinguish. A production version might instead leave both slots populated
  with the same value plus a flag noting "source does not distinguish
  metro/non-metro," rather than picking one.
- **Multi-document policies / non-GMC products in the same batch.** The
  provided sample set includes `Net Catalyst - GPA - Policy Copy - 2022-23.pdf`,
  which is a **Group Personal Accident (GPA)** policy, not GMC — verified by
  reading the document itself ("LIBERTY GROUP PERSONAL ACCIDENT POLICY"). GPA
  covers accidental death/disability payouts and has no room rent, ICU,
  maternity, or waiting-period clauses at all, so the pipeline correctly
  extracts the metadata it can (insurer, premium, employee count, capital sum
  insured) and leaves every GMC-specific benefit field null rather than
  fabricating values for a product category that doesn't have them — this is
  intended behavior, not a missed extraction. A production version processing
  a full employer's insurance pack (which often bundles a GPA rider alongside
  the base GMC policy) would likely want an explicit document-type
  classification step up front, so GPA-specific fields (accidental death
  benefit, permanent disability %, etc.) get their own schema instead of
  being force-fit into the GMC one.



## Project structure

```
gmc-extractor/
├── src/
│ ├── schema.py # pydantic output schema (QMS field mapping)
│ ├── pdf_extractor.py # text/table extraction + OCR fallback
│ ├── llm_extractor.py # Claude tool-use structured extraction
│ ├── gemini_extractor.py # Gemini structured extraction (free-tier default)
│ ├── rules_extractor.py # zero-API-key regex fallback
│ ├── enrichment.py # post-extraction derived-field fill-ins (e.g. policy tenure)
│ └── main.py # CLI entrypoint
├── webapp/
│ ├── app.py # Flask backend (wraps src/ pipeline)
│ ├── templates/index.html
│ ├── static/style.css
│ ├── static/app.js
│ └── uploads/ # PDFs uploaded via the UI land here
├── samples/ # provided sample GMC policy PDFs
├── output/ # generated JSON per PDF (+ run summary) — read by both CLI and UI
├── requirements.txt
└── README.md
```
