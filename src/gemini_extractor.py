"""
Gemini Extraction Layer (free-tier alternative to llm_extractor.py)
======================================================================
Identical job to llm_extractor.py — read the full policy text and map it
into schema.GMCExtraction — but calls Google's Gemini API instead of
Anthropic's.

IMPORTANT implementation note: this deliberately does NOT use Gemini's
`response_schema` constrained-decoding mode. schema.GMCExtraction has ~40
repeated nested CoverageField objects, and Gemini's schema compiler rejects
schemas that large with:

    400 INVALID_ARGUMENT: The specified schema produces a constraint that
    has too many states for serving.

This is a hard platform limit on Gemini's structured-output feature, not
something fixable by trimming token limits or field descriptions. Instead,
we ask for free-form JSON (`response_mime_type="application/json"` without
`response_schema`) and show the model an exact empty-shape example of the
target JSON in the prompt. The response is then validated with the same
pydantic model used everywhere else in the pipeline.

Because Gemini's JSON isn't schema-constrained, it sometimes represents
"not applicable" as a bare `null` instead of an empty CoverageField object
(`{}`) for a given benefit slot, or hallucinates content into
`extraction_meta`. `_normalize_parsed_json` fixes both before validation.
"""
from __future__ import annotations
import json
import os
from typing import Optional

from google import genai
from google.genai import types

from schema import GMCExtraction
from llm_extractor import SYSTEM_PROMPT

MODEL = os.environ.get("GMC_EXTRACTOR_GEMINI_MODEL", "gemini-2.5-flash")

_SHAPE_EXAMPLE = json.dumps(
    GMCExtraction(source_file="<same as Source file above>").model_dump(),
    indent=2,
)

_SHAPE_INSTRUCTIONS = f"""
Return ONLY a single JSON object — no markdown fences, no commentary — matching \
EXACTLY this shape (same keys, same nesting). This is an empty template showing \
every field you must consider; fill in real values where the document states them \
and leave the rest as null, but do not add, rename, or remove any keys. \
IMPORTANT: fields like room_rent, icu_charges, opd_benefit, etc. must ALWAYS be a \
JSON object (e.g. {{"status": null, "limit": null, "raw_text": null, "source_page": null}}) \
even when nothing was found for them — never output `null` in place of the object itself, \
only the individual status/limit/raw_text/source_page values inside it may be null. Do NOT \
include an "extraction_meta" key at all — that field is filled in separately by the caller.

{_SHAPE_EXAMPLE}
"""

_COVERAGE_FIELD_SECTIONS = (
    "room_rent_hospitalization", "maternity_details", "waiting_periods",
    "specific_benefits", "infertility_and_ambulance", "buffer_and_waiver",
)


def _normalize_parsed_json(data: dict) -> dict:
    """
    Fixes the two shape mismatches Gemini's free-form JSON tends to produce:
    1. A benefit slot returned as bare `null` instead of `{}`.
    2. An entire section returned as `null` instead of `{}`.
    Also drops any `extraction_meta` the model may have hallucinated, since
    that field is fully owned/overwritten by this pipeline after validation.
    """
    data = dict(data)
    data.pop("extraction_meta", None)

    for section_key in _COVERAGE_FIELD_SECTIONS:
        section = data.get(section_key)
        if section is None:
            data[section_key] = {}
            continue
        if isinstance(section, dict):
            for field_key, field_value in list(section.items()):
                if field_value is None:
                    section[field_key] = {}
    return data


def extract_with_gemini(document_text: str, source_file: str, api_key: Optional[str] = None) -> dict:
    """
    Calls Gemini in free-form JSON mode and validates the result against
    schema.GMCExtraction. Returns a plain dict.
    Raises RuntimeError if no API key is available.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY configured — cannot run Gemini extraction.")

    client = genai.Client(api_key=api_key)

    prompt = (
        f"Source file: {source_file}\n\n"
        f"Document text follows:\n{document_text}\n\n"
        f"{_SHAPE_INSTRUCTIONS}"
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=16000,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    raw_text = (response.text or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini did not return valid JSON: {e}. Raw response (first 500 chars): {raw_text[:500]}")

    data = _normalize_parsed_json(data)
    data["source_file"] = source_file
    validated = GMCExtraction.model_validate(data)
    result = validated.model_dump()

    result["extraction_meta"]["engine"] = "llm"
    result["extraction_meta"]["provider"] = "gemini"
    result["extraction_meta"]["model"] = MODEL

    filled = 0
    total = 0
    for section_key in _COVERAGE_FIELD_SECTIONS:
        section = result.get(section_key, {}) or {}
        for field in section.values():
            total += 1
            if isinstance(field, dict) and field.get("status"):
                filled += 1
    result["extraction_meta"]["benefit_fields_filled"] = f"{filled}/{total}"
    if total and filled == 0:
        result["extraction_meta"]["warning"] = (
            "0 benefit fields were filled by the model. If the source document clearly "
            "states benefits (check samples manually), this likely indicates a prompting "
            "or truncation issue rather than a genuinely empty policy — worth a re-run."
        )

    return result