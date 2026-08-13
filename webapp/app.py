#!/usr/bin/env python3
"""
GMC Extraction — Web UI backend.

A thin Flask wrapper around the existing extraction pipeline (src/).
Lets you drag-drop a policy PDF, watch it get processed, and browse the
result as an audit-friendly document instead of raw JSON.

Run:
    cd webapp
    python app.py
Then open http://localhost:5000
"""
from __future__ import annotations
import json
import sys
import time
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

# Make the pipeline modules importable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from pdf_extractor import extract_document          # noqa: E402
from llm_extractor import extract_with_llm          # noqa: E402
from gemini_extractor import extract_with_gemini    # noqa: E402
from rules_extractor import extract_with_rules      # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR.parent / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60MB — real GMC packs run 50-80 pages

# Session-only overrides, never persisted to disk
_runtime_keys = {"gemini": None, "anthropic": None}


@app.get("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


@app.get("/api/results")
def list_results():
    """List every JSON result currently on disk (from CLI runs or prior UI runs)."""
    items = []
    for f in sorted(OUTPUT_DIR.glob("*.json")):
        if f.name == "_run_summary.json":
            continue
        try:
            data = json.loads(f.read_text())
            items.append({
                "file": f.stem,
                "insurer": data.get("policy_metadata", {}).get("insurer_name"),
                "engine": data.get("extraction_meta", {}).get("engine_used") or data.get("extraction_meta", {}).get("engine"),
                "page_count": data.get("extraction_meta", {}).get("page_count"),
            })
        except Exception:
            continue
    return jsonify(items)


@app.get("/api/results/<name>")
def get_result(name):
    path = OUTPUT_DIR / f"{name}.json"
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    return jsonify(json.loads(path.read_text()))


@app.post("/api/set-key")
def set_key():
    body = request.json or {}
    provider = body.get("provider", "gemini")
    key = (body.get("api_key") or "").strip()
    if provider not in _runtime_keys:
        return jsonify({"error": "unknown provider"}), 400
    _runtime_keys[provider] = key or None
    return jsonify({"ok": True, "provider": provider, "has_key": bool(_runtime_keys[provider])})


@app.get("/api/key-status")
def key_status():
    import os
    gemini_ok = bool(_runtime_keys["gemini"] or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    anthropic_ok = bool(_runtime_keys["anthropic"] or os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({
        "gemini": gemini_ok,
        "anthropic": anthropic_ok,
        "has_key": gemini_ok or anthropic_ok,
    })


@app.post("/api/upload")
def upload():
    import os

    if "file" not in request.files:
        return jsonify({"error": "no file part"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "only PDF files are supported"}), 400

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / safe_name
    file.save(dest)

    t0 = time.time()
    try:
        doc = extract_document(str(dest))
        full_text = doc.full_text
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"PDF extraction failed: {e}"}), 500

    gemini_key = _runtime_keys["gemini"] or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    anthropic_key = _runtime_keys["anthropic"] or os.environ.get("ANTHROPIC_API_KEY")

    engine_used = "rules"
    result = None
    llm_error = None

    if anthropic_key:
        try:
            result = extract_with_llm(full_text, safe_name, api_key=anthropic_key)
            engine_used = "anthropic"
        except Exception as e:
            llm_error = f"Anthropic: {e}"
            traceback.print_exc()

    if result is None and gemini_key:
        try:
            result = extract_with_gemini(full_text, safe_name, api_key=gemini_key)
            engine_used = "gemini"
        except Exception as e:
            llm_error = f"{llm_error + ' | ' if llm_error else ''}Gemini: {e}"
            traceback.print_exc()

    if result is None:
        result = extract_with_rules(full_text, safe_name)

    result["extraction_meta"]["engine_used"] = engine_used
    result["extraction_meta"]["page_count"] = len(doc.pages)
    result["extraction_meta"]["ocr_pages"] = doc.ocr_page_count
    result["extraction_meta"]["elapsed_seconds"] = round(time.time() - t0, 2)
    if llm_error:
        result["extraction_meta"]["llm_error"] = llm_error

    out_path = OUTPUT_DIR / (Path(safe_name).stem + ".json")
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)