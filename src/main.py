#!/usr/bin/env python3
"""
GMC Policy Extraction Pipeline — CLI entrypoint.

Usage:
    python main.py --input samples/ --output output/
    python main.py --input samples/some_policy.pdf --output output/some_policy.json

Behaviour:
    - --provider auto (default) picks Gemini if GEMINI_API_KEY/GOOGLE_API_KEY is set,
      else Anthropic if ANTHROPIC_API_KEY is set, else falls back to rules-only.
    - Force a specific engine with --provider gemini / anthropic / rules.
    - Always records which engine actually ran in `extraction_meta`, and how
      many pages needed OCR, so output is self-documenting.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

from pdf_extractor import extract_document
from llm_extractor import extract_with_llm
from gemini_extractor import extract_with_gemini
from rules_extractor import extract_with_rules


def pick_provider() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "rules"


def process_one(pdf_path: Path, output_dir: Path, provider: str) -> dict:
    print(f"[+] Processing {pdf_path.name} ...")
    t0 = time.time()

    doc = extract_document(str(pdf_path))
    full_text = doc.full_text
    print(f"    extracted {len(doc.pages)} pages "
          f"({doc.ocr_page_count} needed OCR), {len(full_text):,} chars")

    engine_used = "rules"
    result = None

    if provider == "anthropic":
        try:
            result = extract_with_llm(full_text, pdf_path.name)
            engine_used = "anthropic"
        except Exception as e:
            print(f"    [!] Anthropic extraction failed ({e}); falling back to rules engine.", file=sys.stderr)
            traceback.print_exc()
    elif provider == "gemini":
        try:
            result = extract_with_gemini(full_text, pdf_path.name)
            engine_used = "gemini"
        except Exception as e:
            print(f"    [!] Gemini extraction failed ({e}); falling back to rules engine.", file=sys.stderr)
            traceback.print_exc()

    if result is None:
        result = extract_with_rules(full_text, pdf_path.name)

    result["extraction_meta"]["engine_used"] = engine_used
    result["extraction_meta"]["page_count"] = len(doc.pages)
    result["extraction_meta"]["ocr_pages"] = doc.ocr_page_count
    result["extraction_meta"]["elapsed_seconds"] = round(time.time() - t0, 2)

    out_path = output_dir / (pdf_path.stem + ".json")
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"    -> wrote {out_path} (engine={engine_used}, {result['extraction_meta']['elapsed_seconds']}s)")
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract structured data from GMC policy PDFs.")
    parser.add_argument("--input", required=True, help="PDF file or directory of PDFs")
    parser.add_argument("--output", required=True, help="Directory to write JSON output into")
    parser.add_argument("--provider", choices=["auto", "anthropic", "gemini", "rules"], default="auto",
                         help="Which extraction engine to use. 'auto' picks based on which API key is set "
                              "(GEMINI_API_KEY / GOOGLE_API_KEY preferred — it's free-tier — then ANTHROPIC_API_KEY, "
                              "else falls back to rules-only).")
    parser.add_argument("--no-llm", action="store_true", help="Alias for --provider rules")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = args.provider
    if args.no_llm:
        provider = "rules"

    if provider == "auto":
        provider = pick_provider()

    if provider == "rules":
        print("[i] Running in rules-only mode (no LLM key found, or --provider rules passed).\n"
              "    To enable full benefit-level extraction, set one of:\n"
              "      export GEMINI_API_KEY=AIza...        (free tier, no card — get one at aistudio.google.com)\n"
              "      export ANTHROPIC_API_KEY=sk-ant-...\n")
    else:
        print(f"[i] Using provider: {provider}\n")

    pdf_files = [input_path] if input_path.is_file() else sorted(input_path.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found at {input_path}", file=sys.stderr)
        sys.exit(1)

    summary = []
    for pdf in pdf_files:
        try:
            result = process_one(pdf, output_dir, provider)
            summary.append({"file": pdf.name, "status": "ok",
                             "insurer": result["policy_metadata"].get("insurer_name")})
        except Exception as e:
            print(f"[!] FAILED on {pdf.name}: {e}", file=sys.stderr)
            traceback.print_exc()
            summary.append({"file": pdf.name, "status": "error", "error": str(e)})

    print("\n===== SUMMARY =====")
    for row in summary:
        print(f"  {row['file']:60s} {row['status']:6s} {row.get('insurer') or ''}")

    (output_dir / "_run_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()