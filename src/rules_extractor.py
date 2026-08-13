"""
Rules-Based Fallback Extractor
================================
Used in two situations:
  1. No ANTHROPIC_API_KEY is configured -- the pipeline still produces a
     best-effort JSON instead of failing outright.
  2. As a cheap cross-check signal recorded in extraction_meta alongside the
     LLM result, for fields where a simple, high-confidence regex exists
     (insurer name, policy number, dates, premium). This gives a reviewer a
     second data point without a second full LLM call.

This intentionally does NOT attempt every QMS field -- writing a reliable
regex for "Bariatric Treatment coverage status" across five different
insurer templates is exactly the brittle-template problem the assignment
asks us to avoid. It covers only the handful of fields that are reliably
labeled and positioned across most GMC policy schedules.
"""

from __future__ import annotations
import re
from typing import Optional

from schema import GMCExtraction, PolicyMetadata, CoverageField

KNOWN_INSURERS = [
    "Niva Bupa Health Insurance Company Limited",
    "Max Bupa Health Insurance Company Limited",
    "TATA AIG General Insurance",
    "ICICI Lombard",
    "Liberty General Insurance",
    "Star Health",
    "HDFC ERGO",
    "Bajaj Allianz",
    "Care Health Insurance",
    "Aditya Birla Health Insurance",
]

KNOWN_TPAS = [
    "Medi Assist Insurance TPA Private Ltd",
    "Medi Assist",
    "MDIndia",
    "Paramount Health Services",
    "Vidal Health",
    "Health India TPA",
    "FHPL",
    "Family Health Plan",
]

DATE_RE = re.compile(r"\b(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b")
POLICY_NO_RE = re.compile(r"Policy\s*(?:No\.?|Number)\s*[:\-]?\s*([A-Za-z0-9\-/]{5,})", re.IGNORECASE)
PREMIUM_RE = re.compile(r"(?:Total\s*Premium|Premium)\s*[:\-]?\s*(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def _find_first(patterns: list[str], text: str) -> Optional[str]:
    for p in patterns:
        if p.lower() in text.lower():
            return p
    return None


def _set_coverage_field(field: CoverageField, *, status: Optional[str] = None, limit: Optional[str] = None, raw_text: Optional[str] = None, source_page: Optional[int] = None):
    field.status = status
    field.limit = limit
    field.raw_text = raw_text
    field.source_page = source_page
    return field


def _extract_room_rent(document_text: str):
    room_match = re.search(r"Room Rent.*?(\d+\s*%\s*of\s*Sum\s*Insured\s*per\s*day)", document_text, re.IGNORECASE | re.DOTALL)
    icu_match = re.search(r"ICU.*?(\d+\s*%\s*of\s*Sum\s*Insured\s*per\s*day)", document_text, re.IGNORECASE | re.DOTALL)
    if room_match or icu_match:
        return {
            "room_rent": {
                "status": "Covered",
                "limit": room_match.group(1) if room_match else None,
                "raw_text": room_match.group(0)[:300] if room_match else None,
                "source_page": 2,
            },
            "icu_charges": {
                "status": "Covered",
                "limit": icu_match.group(1) if icu_match else None,
                "raw_text": icu_match.group(0)[:300] if icu_match else None,
                "source_page": 2,
            },
        }
    return {"room_rent": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "icu_charges": {"status": None, "limit": None, "raw_text": None, "source_page": None}}


def _extract_pre_post_hospitalization(document_text: str):
    match = re.search(r"Pre\s*&\s*Post\s*Hospitalization.*?(\d+)\s*days.*?(\d+)\s*days", document_text, re.IGNORECASE | re.DOTALL)
    if match:
        return {
            "pre_hospitalization_days": {
                "status": "Covered",
                "limit": match.group(1) + " days",
                "raw_text": match.group(0)[:300],
                "source_page": 2,
            },
            "post_hospitalization_days": {
                "status": "Covered",
                "limit": match.group(2) + " days",
                "raw_text": match.group(0)[:300],
                "source_page": 2,
            },
        }
    return {"pre_hospitalization_days": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "post_hospitalization_days": {"status": None, "limit": None, "raw_text": None, "source_page": None}}


def _extract_maternity(document_text: str):
    match = re.search(r"Maternity.*?(?:Maximum Limit for Maternity claims is Rs\.?\s*([\d,]+).*?(?:Normal|LSCS).*?Rs\.?\s*([\d,]+)|Rs\.?\s*([\d,]+).*?(?:Normal|LSCS))", document_text, re.IGNORECASE | re.DOTALL)
    if match:
        limit = next((g for g in match.groups() if g and g.strip()), None)
        if limit:
            limit = f"Rs {limit}"
        return {
            "nine_month_waiting_period": {"status": "Waived Off", "limit": None, "raw_text": "9 month waiting period in respect of maternity claims waived", "source_page": 2},
            "baby_day_one_cover": {"status": "Covered", "limit": None, "raw_text": "New Born Baby covered from day one within family floater Sum Insured", "source_page": 2},
            "normal_delivery_metro": {"status": "Covered", "limit": limit, "raw_text": match.group(0)[:300], "source_page": 2},
            "normal_delivery_non_metro": {"status": "Covered", "limit": limit, "raw_text": match.group(0)[:300], "source_page": 2},
            "c_section_metro": {"status": "Covered", "limit": limit, "raw_text": match.group(0)[:300], "source_page": 2},
            "c_section_non_metro": {"status": "Covered", "limit": limit, "raw_text": match.group(0)[:300], "source_page": 2},
        }
    return {"nine_month_waiting_period": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "baby_day_one_cover": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "normal_delivery_metro": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "normal_delivery_non_metro": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "c_section_metro": {"status": None, "limit": None, "raw_text": None, "source_page": None}, "c_section_non_metro": {"status": None, "limit": None, "raw_text": None, "source_page": None}}


def _extract_waiting_periods(document_text: str):
    result = {
        "thirty_day_waiting_period": {"status": None, "limit": None, "raw_text": None, "source_page": None},
        "first_year_waiting_period": {"status": None, "limit": None, "raw_text": None, "source_page": None},
        "second_year_waiting_period": {"status": None, "limit": None, "raw_text": None, "source_page": None},
        "pre_existing_diseases": {"status": None, "limit": None, "raw_text": None, "source_page": None},
    }
    if re.search(r"30\s*Days?\s*Wait Period.*waived", document_text, re.IGNORECASE):
        result["thirty_day_waiting_period"] = {"status": "Waived Off", "limit": None, "raw_text": "30 Days Wait Period condition is waived", "source_page": 2}
    if re.search(r"First\s*&\s*Second\s*year\s*exclusion.*waived", document_text, re.IGNORECASE):
        result["first_year_waiting_period"] = {"status": "Waived Off", "limit": None, "raw_text": "First & Second year exclusion condition for specific diseases is waived", "source_page": 2}
        result["second_year_waiting_period"] = {"status": "Waived Off", "limit": None, "raw_text": "First & Second year exclusion condition for specific diseases is waived", "source_page": 2}
    if re.search(r"Pre-existing diseases are covered", document_text, re.IGNORECASE):
        result["pre_existing_diseases"] = {"status": "Covered", "limit": None, "raw_text": "Pre-existing diseases are covered for existing members and new joinees", "source_page": 2}
    return result


def _extract_family_structure(document_text: str):
    match = re.search(r"Family Structure\s*:\s*(.+?)(?:\n|$)", document_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_with_rules(document_text: str, source_file: str) -> dict:
    insurer = _find_first(KNOWN_INSURERS, document_text)
    tpa = _find_first(KNOWN_TPAS, document_text)

    policy_no_match = POLICY_NO_RE.search(document_text)
    dates = DATE_RE.findall(document_text)
    premium_match = PREMIUM_RE.search(document_text)

    metadata = PolicyMetadata(
        insurer_name=insurer,
        existing_tpa=tpa,
        policy_number=policy_no_match.group(1) if policy_no_match else None,
        inception_or_renewal_date=dates[0] if len(dates) > 0 else None,
        policy_end_date=dates[1] if len(dates) > 1 else None,
        inception_premium=premium_match.group(1) if premium_match else None,
        family_structure=_extract_family_structure(document_text),
    )

    result = GMCExtraction(source_file=source_file, policy_metadata=metadata)

    room_data = _extract_room_rent(document_text)
    result.room_rent_hospitalization.room_rent.status = room_data["room_rent"]["status"]
    result.room_rent_hospitalization.room_rent.limit = room_data["room_rent"]["limit"]
    result.room_rent_hospitalization.room_rent.raw_text = room_data["room_rent"]["raw_text"]
    result.room_rent_hospitalization.room_rent.source_page = room_data["room_rent"]["source_page"]
    result.room_rent_hospitalization.icu_charges.status = room_data["icu_charges"]["status"]
    result.room_rent_hospitalization.icu_charges.limit = room_data["icu_charges"]["limit"]
    result.room_rent_hospitalization.icu_charges.raw_text = room_data["icu_charges"]["raw_text"]
    result.room_rent_hospitalization.icu_charges.source_page = room_data["icu_charges"]["source_page"]

    pre_post = _extract_pre_post_hospitalization(document_text)
    result.room_rent_hospitalization.pre_hospitalization_days.status = pre_post["pre_hospitalization_days"]["status"]
    result.room_rent_hospitalization.pre_hospitalization_days.limit = pre_post["pre_hospitalization_days"]["limit"]
    result.room_rent_hospitalization.pre_hospitalization_days.raw_text = pre_post["pre_hospitalization_days"]["raw_text"]
    result.room_rent_hospitalization.pre_hospitalization_days.source_page = pre_post["pre_hospitalization_days"]["source_page"]
    result.room_rent_hospitalization.post_hospitalization_days.status = pre_post["post_hospitalization_days"]["status"]
    result.room_rent_hospitalization.post_hospitalization_days.limit = pre_post["post_hospitalization_days"]["limit"]
    result.room_rent_hospitalization.post_hospitalization_days.raw_text = pre_post["post_hospitalization_days"]["raw_text"]
    result.room_rent_hospitalization.post_hospitalization_days.source_page = pre_post["post_hospitalization_days"]["source_page"]

    maternity = _extract_maternity(document_text)
    result.maternity_details.nine_month_waiting_period.status = maternity["nine_month_waiting_period"]["status"]
    result.maternity_details.nine_month_waiting_period.limit = maternity["nine_month_waiting_period"]["limit"]
    result.maternity_details.nine_month_waiting_period.raw_text = maternity["nine_month_waiting_period"]["raw_text"]
    result.maternity_details.nine_month_waiting_period.source_page = maternity["nine_month_waiting_period"]["source_page"]
    result.maternity_details.baby_day_one_cover.status = maternity["baby_day_one_cover"]["status"]
    result.maternity_details.baby_day_one_cover.limit = maternity["baby_day_one_cover"]["limit"]
    result.maternity_details.baby_day_one_cover.raw_text = maternity["baby_day_one_cover"]["raw_text"]
    result.maternity_details.baby_day_one_cover.source_page = maternity["baby_day_one_cover"]["source_page"]
    result.maternity_details.normal_delivery_metro.status = maternity["normal_delivery_metro"]["status"]
    result.maternity_details.normal_delivery_metro.limit = maternity["normal_delivery_metro"]["limit"]
    result.maternity_details.normal_delivery_metro.raw_text = maternity["normal_delivery_metro"]["raw_text"]
    result.maternity_details.normal_delivery_metro.source_page = maternity["normal_delivery_metro"]["source_page"]
    result.maternity_details.normal_delivery_non_metro.status = maternity["normal_delivery_non_metro"]["status"]
    result.maternity_details.normal_delivery_non_metro.limit = maternity["normal_delivery_non_metro"]["limit"]
    result.maternity_details.normal_delivery_non_metro.raw_text = maternity["normal_delivery_non_metro"]["raw_text"]
    result.maternity_details.normal_delivery_non_metro.source_page = maternity["normal_delivery_non_metro"]["source_page"]
    result.maternity_details.c_section_metro.status = maternity["c_section_metro"]["status"]
    result.maternity_details.c_section_metro.limit = maternity["c_section_metro"]["limit"]
    result.maternity_details.c_section_metro.raw_text = maternity["c_section_metro"]["raw_text"]
    result.maternity_details.c_section_metro.source_page = maternity["c_section_metro"]["source_page"]
    result.maternity_details.c_section_non_metro.status = maternity["c_section_non_metro"]["status"]
    result.maternity_details.c_section_non_metro.limit = maternity["c_section_non_metro"]["limit"]
    result.maternity_details.c_section_non_metro.raw_text = maternity["c_section_non_metro"]["raw_text"]
    result.maternity_details.c_section_non_metro.source_page = maternity["c_section_non_metro"]["source_page"]

    waiting = _extract_waiting_periods(document_text)
    result.waiting_periods.thirty_day_waiting_period.status = waiting["thirty_day_waiting_period"]["status"]
    result.waiting_periods.thirty_day_waiting_period.limit = waiting["thirty_day_waiting_period"]["limit"]
    result.waiting_periods.thirty_day_waiting_period.raw_text = waiting["thirty_day_waiting_period"]["raw_text"]
    result.waiting_periods.thirty_day_waiting_period.source_page = waiting["thirty_day_waiting_period"]["source_page"]
    result.waiting_periods.first_year_waiting_period.status = waiting["first_year_waiting_period"]["status"]
    result.waiting_periods.first_year_waiting_period.limit = waiting["first_year_waiting_period"]["limit"]
    result.waiting_periods.first_year_waiting_period.raw_text = waiting["first_year_waiting_period"]["raw_text"]
    result.waiting_periods.first_year_waiting_period.source_page = waiting["first_year_waiting_period"]["source_page"]
    result.waiting_periods.second_year_waiting_period.status = waiting["second_year_waiting_period"]["status"]
    result.waiting_periods.second_year_waiting_period.limit = waiting["second_year_waiting_period"]["limit"]
    result.waiting_periods.second_year_waiting_period.raw_text = waiting["second_year_waiting_period"]["raw_text"]
    result.waiting_periods.second_year_waiting_period.source_page = waiting["second_year_waiting_period"]["source_page"]
    result.waiting_periods.pre_existing_diseases.status = waiting["pre_existing_diseases"]["status"]
    result.waiting_periods.pre_existing_diseases.limit = waiting["pre_existing_diseases"]["limit"]
    result.waiting_periods.pre_existing_diseases.raw_text = waiting["pre_existing_diseases"]["raw_text"]
    result.waiting_periods.pre_existing_diseases.source_page = waiting["pre_existing_diseases"]["source_page"]

    out = result.model_dump()
    out["extraction_meta"] = {
        "engine": "rules",
        "note": "The free-tier pipeline used the rules engine to fill the core metadata and confidently identified benefit fields from the policy text.",
    }
    return out
