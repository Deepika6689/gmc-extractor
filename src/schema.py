"""
QMS Extraction Schema
======================
Defines the structured output schema that every extracted GMC policy
must be mapped into, per the Technical Assessment requirements.

Design notes:
- Every "coverage" style field uses the CoverageField model so the value can
  either be a status (Covered / Not Covered / Waived Off) OR a concrete
  limit (amount / percentage / day count) OR both, plus a raw_text field
  that preserves the source clause for human audit — this satisfies the
  "Data Structuring... requiring minimal to no human intervention" criterion
  because a reviewer can always see WHY a value was chosen.
- Fields the source document does not mention are left as null rather than
  guessed — silently inventing a value is worse than admitting "not found".
"""

from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


class CoverageField(BaseModel):
    """Generic slot for any benefit/feature in the QMS schema."""
    status: Optional[str] = Field(
        default=None,
        description="One of: Covered, Not Covered, Waived Off, Applied, or null if undetermined."
    )
    limit: Optional[str] = Field(
        default=None,
        description="Concrete monetary limit, percentage, or day count as stated in the policy "
                    "(e.g. '1% of SI / Max Rs 5,000 per day', '60 days', '25%')."
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Verbatim (or near-verbatim, trimmed) source sentence/clause the value was derived from, "
                    "for human audit."
    )
    source_page: Optional[int] = Field(default=None, description="Page number the clause was found on, if known.")


class SumInsuredTier(BaseModel):
    sum_insured: Optional[str] = None
    applicable_to: Optional[str] = Field(default=None, description="e.g. grade/category this SI tier applies to")


class PolicyMetadata(BaseModel):
    insurer_name: Optional[str] = None
    existing_tpa: Optional[str] = None
    policyholder_name: Optional[str] = None
    policy_number: Optional[str] = None
    inception_or_renewal_date: Optional[str] = None
    policy_end_date: Optional[str] = None
    policy_tenure: Optional[str] = None
    inception_premium: Optional[str] = None
    family_structure: Optional[str] = Field(
        default=None, description="e.g. 'Employee + Spouse + Children' / 'Employee + Spouse + 2 Children + Parents'"
    )
    sum_insured_tiers: List[SumInsuredTier] = Field(default_factory=list)


class Demographics(BaseModel):
    total_employees: Optional[int] = None
    total_spouses: Optional[int] = None
    total_children: Optional[int] = None
    total_parents_or_parents_in_law: Optional[int] = None
    total_lives_covered: Optional[int] = None


class RoomRentHospitalization(BaseModel):
    room_rent: CoverageField = Field(default_factory=CoverageField)
    icu_charges: CoverageField = Field(default_factory=CoverageField)
    pre_hospitalization_days: CoverageField = Field(default_factory=CoverageField)
    post_hospitalization_days: CoverageField = Field(default_factory=CoverageField)


class MaternityDetails(BaseModel):
    nine_month_waiting_period: CoverageField = Field(default_factory=CoverageField)
    baby_day_one_cover: CoverageField = Field(default_factory=CoverageField)
    vaccination_coverage: CoverageField = Field(default_factory=CoverageField)
    normal_delivery_metro: CoverageField = Field(default_factory=CoverageField)
    normal_delivery_non_metro: CoverageField = Field(default_factory=CoverageField)
    c_section_metro: CoverageField = Field(default_factory=CoverageField)
    c_section_non_metro: CoverageField = Field(default_factory=CoverageField)


class WaitingPeriods(BaseModel):
    thirty_day_waiting_period: CoverageField = Field(default_factory=CoverageField)
    first_year_waiting_period: CoverageField = Field(default_factory=CoverageField)
    second_year_waiting_period: CoverageField = Field(default_factory=CoverageField)
    pre_existing_diseases: CoverageField = Field(default_factory=CoverageField)


class SpecificBenefits(BaseModel):
    day_care_expenses: CoverageField = Field(default_factory=CoverageField)
    opd_benefit: CoverageField = Field(default_factory=CoverageField)
    teleconsultation: CoverageField = Field(default_factory=CoverageField)
    pharmacy_discount: CoverageField = Field(default_factory=CoverageField)
    domiciliary_hospitalization: CoverageField = Field(default_factory=CoverageField)
    annual_health_checkup: CoverageField = Field(default_factory=CoverageField)
    modern_treatment: CoverageField = Field(default_factory=CoverageField)
    bariatric_treatment: CoverageField = Field(default_factory=CoverageField)
    psychiatric_treatment: CoverageField = Field(default_factory=CoverageField)
    ayush_treatment: CoverageField = Field(default_factory=CoverageField)
    lgbtq_coverage: CoverageField = Field(default_factory=CoverageField)
    live_in_partners: CoverageField = Field(default_factory=CoverageField)
    organ_donor_expenses: CoverageField = Field(default_factory=CoverageField)


class InfertilityAmbulance(BaseModel):
    infertility_treatment_surrogacy: CoverageField = Field(default_factory=CoverageField)
    ambulance_charges: CoverageField = Field(default_factory=CoverageField)
    air_ambulance_charges: CoverageField = Field(default_factory=CoverageField)


class BufferWaiver(BaseModel):
    corporate_buffer_disease_wise_capping: CoverageField = Field(default_factory=CoverageField)


class ExtractionMeta(BaseModel):
    """Pipeline diagnostics attached to every extraction result.

    Defined as a fixed-shape model (not a bare `dict`) because a bare dict
    forces Pydantic to emit `additionalProperties: true` in the generated
    JSON schema, which Gemini's Developer API (free-tier API key mode)
    rejects outright -- that field alone was enough to fail the whole
    response_schema and silently fall back to the rules engine.
    """
    engine: Optional[str] = Field(default=None, description="'llm' or 'rules'.")
    provider: Optional[str] = Field(default=None, description="'anthropic' or 'gemini', when engine == 'llm'.")
    model: Optional[str] = Field(default=None, description="Model name/id actually used.")
    engine_used: Optional[str] = Field(default=None, description="Set by the caller after any fallback logic.")
    page_count: Optional[int] = Field(default=None)
    ocr_pages: Optional[int] = Field(default=None)
    elapsed_seconds: Optional[float] = Field(default=None)
    llm_error: Optional[str] = Field(default=None, description="Set when the LLM pass failed and rules was used instead.")
    note: Optional[str] = Field(default=None, description="Free-text explanation, e.g. from the rules engine.")


class GMCExtraction(BaseModel):
    """Top-level output object — one instance produced per source PDF."""
    source_file: str
    policy_metadata: PolicyMetadata = Field(default_factory=PolicyMetadata)
    demographics: Demographics = Field(default_factory=Demographics)
    room_rent_hospitalization: RoomRentHospitalization = Field(default_factory=RoomRentHospitalization)
    maternity_details: MaternityDetails = Field(default_factory=MaternityDetails)
    waiting_periods: WaitingPeriods = Field(default_factory=WaitingPeriods)
    specific_benefits: SpecificBenefits = Field(default_factory=SpecificBenefits)
    infertility_and_ambulance: InfertilityAmbulance = Field(default_factory=InfertilityAmbulance)
    buffer_and_waiver: BufferWaiver = Field(default_factory=BufferWaiver)
    extraction_meta: "ExtractionMeta" = Field(
        default_factory=lambda: ExtractionMeta(),
        description="Pipeline diagnostics: engine used, page count, OCR fallback flag, model used, warnings."
    )