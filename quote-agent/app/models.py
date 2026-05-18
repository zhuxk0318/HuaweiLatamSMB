from __future__ import annotations

from io import BytesIO
from typing import Any, Literal

from pydantic import BaseModel, Field


ActionType = Literal["quote", "exclude_powered_off", "manual_review"]
RegionKey = Literal["mexico", "chile", "brazil"]
EvsTypeKey = Literal["gpssd", "sas"]
LangKey = Literal["es", "en", "zh"]
FlexibleProductKey = Literal[
    "ECS",
    "EVS",
    "CBR",
    "EIP",
    "CCE",
    "CCI",
    "SFS Turbo",
    "NAT Gateway",
    "VPN",
    "Direct Connect as a Service",
    "RDS",
    "DDS",
    "DWS",
    "OBS",
    "ELB",
    "WAF",
    "HSS",
    "VPC",
    "Workspace",
    "DRS",
    "CSS",
    "DLI",
    "ModelArts",
    "FunctionGraph",
    "GaussDB",
]
FlexibleMatchMethod = Literal["rule_match", "local_catalog_retrieval", "llm_fallback", "unmatched"]
FlexibleRequirementStatus = Literal[
    "ready",
    "needs_quantity",
    "needs_spec",
    "needs_region",
    "needs_manual_review",
    "needs_price_confirmation",
]
FlexiblePriceStatus = Literal["confirmed", "capture_error", "pending_confirmation"]
FlexibleQuotePurpose = Literal["purchase_quote", "unit_price_comparison", "migration_estimate", "unknown"]
FlexibleQuantityPolicy = Literal["required", "default_to_one_for_unit_price", "derive_from_rows"]
FlexibleQuantitySource = Literal["source_file", "human_feedback", "inferred_unit_price"]


class ParsedVM(BaseModel):
    vm_name: str
    power_state: str = ""
    os: str = ""
    vcpu: int = 0
    memory_gib: float = 0
    disk_gib: float = 0


class NormalizedVM(ParsedVM):
    action: ActionType
    review_reason: str | None = None


class QuoteLine(NormalizedVM):
    region: RegionKey
    evs_type: EvsTypeKey
    ecs_category: str | None = None
    ecs_family_label: str | None = None
    ecs_spec: str | None = None
    ecs_ondemand_monthly_usd: float = 0
    ecs_ri_1y_monthly_usd: float = 0
    evs_monthly_usd: float = 0
    total_ondemand_monthly_usd: float = 0
    total_ri_1y_monthly_usd: float = 0


class QuoteSummary(BaseModel):
    total_vms: int
    excluded_vms: int
    manual_review_vms: int
    quoted_vms: int
    total_disk_gib: float
    total_ondemand_monthly_usd: float
    total_ri_1y_monthly_usd: float
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class QuotePreviewResponse(BaseModel):
    source_filename: str
    region: RegionKey
    evs_type: EvsTypeKey
    lang: LangKey
    summary: QuoteSummary
    quote_lines: list[QuoteLine] = Field(default_factory=list)
    manual_review_lines: list[QuoteLine] = Field(default_factory=list)
    excluded_lines: list[QuoteLine] = Field(default_factory=list)


class QuoteRequest(BaseModel):
    region: RegionKey
    evs_type: EvsTypeKey
    lang: LangKey = "en"
    source_filename: str


class QuoteWorkbook(BaseModel):
    filename: str
    content: bytes

    def as_stream(self) -> BytesIO:
        return BytesIO(self.content)


class FlexibleQuoteContext(BaseModel):
    region: RegionKey | None = None
    language: LangKey = "en"
    customer_notes: str = ""


class ComputeSpec(BaseModel):
    spec_type: Literal["compute"] = "compute"
    vcpu: int | None = None
    memory_gib: float | None = None
    sku: str | None = None


class StorageSpec(BaseModel):
    spec_type: Literal["storage"] = "storage"
    capacity_gib: float | None = None
    tier: str | None = None
    sku: str | None = None


class NetworkSpec(BaseModel):
    spec_type: Literal["network"] = "network"
    bandwidth_mbps: float | None = None
    tier: str | None = None
    sku: str | None = None


class GenericSpec(BaseModel):
    spec_type: Literal["generic"] = "generic"
    tier: str | None = None
    sku: str | None = None
    description: str | None = None


FlexibleSpec = ComputeSpec | StorageSpec | NetworkSpec | GenericSpec


class RequirementItem(BaseModel):
    item_id: str
    source_file: str
    source_sheet: str | None = None
    row_number: int | None = None
    raw_product_name: str
    normalized_product: FlexibleProductKey | None = None
    quantity: float | None = None
    quantity_source: FlexibleQuantitySource | None = None
    unit: str | None = None
    region: RegionKey | None = None
    spec: FlexibleSpec | None = None
    notes: str | None = None
    status: FlexibleRequirementStatus = "needs_manual_review"
    status_reason: str | None = None


class MatchedProduct(BaseModel):
    item_id: str
    product: FlexibleProductKey | None = None
    match_method: FlexibleMatchMethod
    confidence: float = 0
    rationale: str | None = None


class PriceComponent(BaseModel):
    product: FlexibleProductKey
    region: RegionKey
    sku: str | None = None
    family: str | None = None
    tier: str | None = None
    billing_mode: str
    unit: str
    price: float | None = None
    currency: str = "USD"
    source_url: str
    captured_at: str
    raw_attributes: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    status: FlexiblePriceStatus = "pending_confirmation"
    capture_error: str | None = None


class FlexibleQuoteLine(BaseModel):
    line_id: str
    requirement_item_id: str
    product: FlexibleProductKey
    region: RegionKey
    quantity: float
    unit: str
    billing_mode: str
    matched_sku: str | None = None
    matched_tier: str | None = None
    unit_price: float
    monthly_price: float
    currency: str = "USD"
    assumption: str | None = None


class FlexibleQuoteSummary(BaseModel):
    total_input_items: int = 0
    quote_ready_items: int = 0
    quoted_items: int = 0
    blocker_count: int = 0
    unquoted_count: int = 0
    total_monthly_price: float = 0
    currency: str = "USD"
    summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class HumanFeedback(BaseModel):
    item_id: str
    quantity: float | None = None
    region: RegionKey | None = None
    spec_text: str | None = None
    notes: str | None = None


class AuditEntry(BaseModel):
    timestamp: str
    stage: str
    message: str
    item_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FlexibleQuoteBlocker(BaseModel):
    item_id: str
    product: str
    status: FlexibleRequirementStatus
    message: str
    source_file: str
    source_sheet: str | None = None
    row_number: int | None = None


class FlexibleCatalogResponse(BaseModel):
    items: list[PriceComponent] = Field(default_factory=list)


class FlexibleSchemaMapping(BaseModel):
    product: str | list[str] | None = None
    quantity: str | list[str] | None = None
    region: str | list[str] | None = None
    spec: str | list[str] | None = None
    notes: str | list[str] | None = None


class FlexibleInputProfile(BaseModel):
    quote_purpose: FlexibleQuotePurpose = "unknown"
    quantity_policy: FlexibleQuantityPolicy = "required"
    confidence: float = 0
    rationale: str | None = None


class FlexibleDocumentDiagnostic(BaseModel):
    filename: str
    sheet: str
    columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    selected_columns: dict[str, str | None] = Field(default_factory=dict)
    candidate_rows: int = 0
    extracted_rows: int = 0
    reason: str | None = None


class FlexibleQuoteDiagnostics(BaseModel):
    llm_used: bool = False
    llm_model: str | None = None
    llm_attempts: int = 0
    llm_error: str | None = None
    documents: list[FlexibleDocumentDiagnostic] = Field(default_factory=list)
    input_profile: FlexibleInputProfile | None = None
    message: str | None = None


class FlexibleQuotePreviewResponse(BaseModel):
    requirements: list[RequirementItem] = Field(default_factory=list)
    quote_ready_items: list[RequirementItem] = Field(default_factory=list)
    quote_blockers: list[FlexibleQuoteBlocker] = Field(default_factory=list)
    quote_lines: list[FlexibleQuoteLine] = Field(default_factory=list)
    unquoted_items: list[RequirementItem] = Field(default_factory=list)
    matched_products: list[MatchedProduct] = Field(default_factory=list)
    summary: FlexibleQuoteSummary = Field(default_factory=FlexibleQuoteSummary)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    quote_context: FlexibleQuoteContext = Field(default_factory=FlexibleQuoteContext)
    diagnostics: FlexibleQuoteDiagnostics = Field(default_factory=FlexibleQuoteDiagnostics)


class FlexibleReviewRequest(BaseModel):
    requirements: list[RequirementItem] = Field(default_factory=list)
    quote_context: FlexibleQuoteContext = Field(default_factory=FlexibleQuoteContext)
    feedback: list[HumanFeedback] = Field(default_factory=list)
    matched_products: list[MatchedProduct] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)


FlexiblePreviewTaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
FlexiblePreviewStageStatus = Literal["pending", "running", "completed", "skipped", "failed"]


class FlexiblePreviewStageEvent(BaseModel):
    stage: str
    status: FlexiblePreviewStageStatus
    message: str
    timestamp: str


class FlexiblePreviewTaskError(BaseModel):
    message: str
    detail: str | None = None
    last_stage: str | None = None
    diagnostics: FlexibleQuoteDiagnostics | None = None


class FlexiblePreviewTaskCreatedResponse(BaseModel):
    task_id: str
    status: FlexiblePreviewTaskStatus


class FlexiblePreviewTaskResponse(BaseModel):
    task_id: str
    status: FlexiblePreviewTaskStatus
    current_stage: str | None = None
    stage_events: list[FlexiblePreviewStageEvent] = Field(default_factory=list)
    error: FlexiblePreviewTaskError | None = None
    result: FlexibleQuotePreviewResponse | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None


class RowQuoteSummary(BaseModel):
    total_rows: int = 0
    quoted_rows: int = 0
    unmatched_rows: int = 0
    manual_review_rows: int = 0
    missing_price_rows: int = 0
    non_quote_rows: int = 0
    total_ondemand_monthly: float = 0
    total_monthly: float = 0
    total_ri_1y_monthly: float = 0
    currency: str = "USD"


class RowQuoteTaskCreatedResponse(BaseModel):
    task_id: str
    status: FlexiblePreviewTaskStatus


class RowQuoteTaskError(BaseModel):
    message: str
    detail: str | None = None
    last_stage: str | None = None


class RowQuoteProgress(BaseModel):
    total_rows: int = 0
    processed_rows: int = 0
    quoted_rows: int = 0
    manual_review_rows: int = 0
    missing_price_rows: int = 0
    unmatched_rows: int = 0
    non_quote_rows: int = 0
    mapped_rows: int = 0
    priced_rows: int = 0
    stage_processed_rows: int = 0
    stage_total_rows: int = 0


class RowQuoteTaskResponse(BaseModel):
    task_id: str
    status: FlexiblePreviewTaskStatus
    current_stage: str | None = None
    summary: RowQuoteSummary | None = None
    progress: RowQuoteProgress | None = None
    error: RowQuoteTaskError | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None
