from __future__ import annotations

from io import BytesIO
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


SheetSelectionMode = Literal["first", "all", "selected"]


class SheetSelection(BaseModel):
    mode: SheetSelectionMode = "first"
    selected_input: str | None = None


class SheetSelectionError(ValueError):
    pass


def resolve_sheet_selection(
    sheet_names: list[str],
    selection: SheetSelection,
) -> list[str]:
    if not sheet_names:
        return []
    if selection.mode == "first":
        return [sheet_names[0]]
    if selection.mode == "all":
        return list(sheet_names)
    # mode == "selected"
    raw = (selection.selected_input or "").strip()
    if not raw:
        raise SheetSelectionError("selected_input is required when mode is 'selected'.")
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        raise SheetSelectionError("selected_input contains no valid tokens.")
    result: list[str] = []
    seen: set[str] = set()
    errors: list[str] = []
    for token in tokens:
        if token.isdigit():
            index = int(token)
            if index < 1 or index > len(sheet_names):
                errors.append(f"Sheet index {index} is out of range (1–{len(sheet_names)}).")
                continue
            name = sheet_names[index - 1]
        else:
            if token not in sheet_names:
                errors.append(f"Sheet name '{token}' does not exist. Available: {', '.join(sheet_names)}")
                continue
            name = token
        if name not in seen:
            seen.add(name)
            result.append(name)
    if errors:
        raise SheetSelectionError(" ".join(errors))
    if not result:
        raise SheetSelectionError("No valid sheets selected.")
    return result


ActionType = Literal["quote", "exclude_powered_off", "manual_review"]
RegionKey = Literal["mexico", "chile", "brazil"]
EvsTypeKey = Literal["gpssd", "sas", "high-io", "ultra-high-io"]
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
    "LTS",
    "DLI",
    "DCS",
    "GeminiDB",
    "DMS",
    "DataArts Studio",
    "Cloud Connect",
    "DEW",
    "Anti-DDoS",
    "CFW",
    "CES",
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
    "excluded_by_manual_review",
]
FlexiblePriceStatus = Literal["confirmed", "capture_error", "pending_confirmation"]
FlexibleQuotePurpose = Literal["purchase_quote", "unit_price_comparison", "migration_estimate", "unknown"]
FlexibleQuantityPolicy = Literal["required", "default_to_one_for_unit_price", "derive_from_rows"]
FlexibleQuantitySource = Literal["source_file", "human_feedback", "inferred_unit_price", "billing_standardized"]


class ParsedVM(BaseModel):
    vm_name: str
    power_state: str = ""
    os: str = ""
    vcpu: int = 0
    memory_gib: float = 0
    disk_gib: float = 0
    # Non-standard inventory fields (Phase 1)
    customer: str | None = None
    workload_type: str | None = None
    source_sheet: str | None = None
    source_dc: str | None = None
    raw_memory_mb: float | None = None
    raw_storage_mib: float | None = None
    # LLM / local classification hints (Phase 1 reserved, later phases fill)
    workload_category: str | None = None
    storage_class_hint: str | None = None
    license_hint: str | None = None
    ecs_family_hint: str | None = None
    classification_confidence: float | None = None
    classification_rationale: str | None = None
    review_flags: list[str] = Field(default_factory=list)


class NormalizedVM(ParsedVM):
    action: ActionType
    review_reason: str | None = None


class QuoteLine(NormalizedVM):
    region: RegionKey
    evs_type: EvsTypeKey
    ecs_category: str | None = None
    ecs_family_label: str | None = None
    ecs_spec: str | None = None
    ecs_vcpu: int | None = None
    ecs_mem: float | None = None
    ecs_ondemand_monthly_usd: float = 0
    ecs_ri_1y_monthly_usd: float = 0
    evs_monthly_usd: float = 0
    total_ondemand_monthly_usd: float = 0
    total_ri_1y_monthly_usd: float = 0
    # Phase 8C: per-VM ECS/EVS selection fields
    evs_selected_type: str | None = None
    evs_selected_label: str | None = None
    ecs_family_policy: str | None = None


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
    task_id: str | None = None


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
    quote_mode: Literal["cloud_billing", "others"] | None = None


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


# --- Cloud Billing Final Quotation models (Phase 8A) ---

FinalQuoteItemStatus = Literal["quoted", "partial", "manual_review", "unquoted"]

CloudBillingResourceKind = Literal[
    "compute_vm",
    "block_storage",
    "shared_file_storage",
    "object_storage",
    "managed_database",
    "load_balancing_and_waf",
    "vpn_connectivity",
    "public_ip_or_bandwidth",
    "backup_security_ops",
    "platform_paas_misc",
]


class CloudBillingFinalQuoteItem(BaseModel):
    """A single customer-readable final quotation line item.

    This is the third layer in the Cloud Billing Quote pipeline:
      1. Raw billing lines
      2. Aggregated billing items (llm_aggregated_billing_items / quote_lines)
      3. Final quotation items  ← this model

    Each final item may compose multiple internal items into one
    business-level quotation entry (e.g. 6 × same-spec VMs → 1 line).
    """

    item_id: str
    vendor: str
    resource_kind: CloudBillingResourceKind
    # ── Source cloud fields ──
    source_service_family: str | None = None
    source_service_name: str
    source_config_summary: str | None = None
    source_quantity: float | None = None
    source_pricing_basis: str | None = None
    source_monthly_total_usd: float | None = None
    # ── Huawei Cloud target fields ──
    huawei_product: str | None = None
    huawei_spec_summary: str | None = None
    huawei_quantity: float | None = None
    huawei_unit_price_usd: float | None = None
    huawei_billing_basis: str | None = None
    huawei_monthly_total_usd: float | None = None
    # ── Status & traceability ──
    status: FinalQuoteItemStatus = "unquoted"
    composition_notes: list[str] = Field(default_factory=list)
    source_item_ids: list[str] = Field(default_factory=list)
    manual_review_reason: str | None = None


# --- LLM Final Composition Candidate (Phase 10A) ---

class CloudBillingFinalCompositionCandidate(BaseModel):
    """An LLM-proposed final quotation item — NOT yet validated or priced.

    This is the output of the LLM-driven final composition step.
    It must be validated and enriched by deterministic logic before
    becoming a CloudBillingFinalQuoteItem.

    Key invariants:
    - Prices are NOT trusted from the LLM; they are backfilled from quote_lines.
    - huawei_product is a hint, not authoritative; must be validated against catalog.
    - component_refs must point to real aggregated billing item IDs.
    """
    candidate_id: str
    vendor: str
    resource_kind: CloudBillingResourceKind | str
    # ── Source cloud fields (LLM-composed) ──
    source_service_name: str
    source_config_summary: str | None = None
    source_quantity: float | None = None
    source_billing_basis: str | None = None
    source_monthly_total_usd: float | None = None
    # ── Huawei Cloud target hints (LLM-suggested, not authoritative) ──
    huawei_product: str | None = None
    huawei_spec_hint: str | None = None
    huawei_quantity: float | None = None
    huawei_billing_basis: str | None = None
    # ── Status & traceability ──
    status: FinalQuoteItemStatus = "unquoted"
    manual_review_reason: str | None = None
    composition_notes: list[str] = Field(default_factory=list)
    component_refs: list[str] = Field(default_factory=list)
    # ── LLM confidence ──
    confidence: float | None = None


class CloudBillingTargetComponent(BaseModel):
    """A Huawei Cloud target component proposed from a complete source document."""

    component_id: str
    huawei_product: str | None = None
    quantity: float | None = None
    unit: str | None = None
    spec_hint: str | None = None
    vcpu: int | None = None
    memory_gib: float | None = None
    capacity_gib: float | None = None
    tier: str | None = None
    billing_basis: str | None = None
    rationale: str | None = None
    confidence: float | None = None
    requirement_item_id: str | None = None
    manual_review_reason: str | None = None


class CloudBillingAnalyzedItem(BaseModel):
    """A business-level source item extracted by the first full-document LLM."""

    item_id: str
    vendor: str
    source_refs: list[str] = Field(default_factory=list)
    source_service_name: str
    description: str | None = None
    source_region: str | None = None
    environment: str | None = None
    source_config_summary: str | None = None
    source_quantity: float | None = None
    source_billing_basis: str | None = None
    source_monthly_total_usd: float | None = None
    currency: str = "USD"
    target_components: list[CloudBillingTargetComponent] = Field(default_factory=list)
    manual_review_reason: str | None = None
    confidence: float | None = None


class CloudBillingMappingCorrection(BaseModel):
    """A safe, price-free correction proposed by the second LLM."""

    component_id: str
    action: Literal[
        "keep",
        "replace_product",
        "replace_spec",
        "replace_quantity",
        "manual_review",
    ] = "keep"
    huawei_product: str | None = None
    quantity: float | None = None
    unit: str | None = None
    spec_hint: str | None = None
    vcpu: int | None = None
    memory_gib: float | None = None
    capacity_gib: float | None = None
    tier: str | None = None
    reason: str | None = None


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


class ManualReviewCandidate(BaseModel):
    """A single manual review candidate exposed in preview responses."""
    candidate_id: str
    source_label: str
    source_product_type: str = ""
    source_product_sku: str = ""
    source_amount: float = 0
    source_quantity: float = 1
    source_unit: str = "1"
    blocker_category: str = ""
    manual_review_need: str = ""
    minimal_fields_required: list[str] = Field(default_factory=list)
    suggested_huawei_target_family: str | None = None
    reason: str = ""
    source_line_numbers: list[int] = Field(default_factory=list)


class ManualReviewDecisionInput(BaseModel):
    """A single manual review decision submitted by the caller."""
    candidate_id: str
    decision_type: str
    fields: dict[str, Any] = Field(default_factory=dict)


class ManualReviewApplyRequest(BaseModel):
    """Request body for the manual-review apply endpoint."""
    task_id: str | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[ManualReviewDecisionInput] = Field(default_factory=list)
    reprice: bool = False


ManualReviewApplyErrorCode = Literal[
    "unknown_candidate_id",
    "wrong_decision_type",
    "missing_required_field",
    "invalid_field_type",
    "invalid_field_value",
    "unexpected_field",
]


class ManualReviewApplyError(BaseModel):
    """A structured error from manual review apply validation."""
    candidate_id: str | None = None
    code: ManualReviewApplyErrorCode
    message: str


class ManualReviewApplyResult(BaseModel):
    """Result of applying a single manual review decision."""
    candidate_id: str
    outcome: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class ManualReviewApplyResponse(BaseModel):
    """Response body for the manual-review apply endpoint."""
    applied_count: int = 0
    errors: list[ManualReviewApplyError] = Field(default_factory=list)
    results: list[ManualReviewApplyResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


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
    manual_review_candidates: list[ManualReviewCandidate] = Field(default_factory=list)
    billing_lines: list[dict[str, Any]] = Field(default_factory=list)
    llm_aggregated_billing_items: list[dict[str, Any]] = Field(default_factory=list)
    mapped_billing_resources: list[dict[str, Any]] = Field(default_factory=list)
    billing_gap_analysis: dict[str, Any] = Field(default_factory=dict)
    billing_reconciliation: dict[str, Any] = Field(default_factory=dict)
    final_billing_quote_items: list[CloudBillingFinalQuoteItem] = Field(default_factory=list)


class FlexibleReviewRequest(BaseModel):
    requirements: list[RequirementItem] = Field(default_factory=list)
    quote_context: FlexibleQuoteContext = Field(default_factory=FlexibleQuoteContext)
    feedback: list[HumanFeedback] = Field(default_factory=list)
    matched_products: list[MatchedProduct] = Field(default_factory=list)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    billing_lines: list[dict[str, Any]] = Field(default_factory=list)
    llm_aggregated_billing_items: list[dict[str, Any]] = Field(default_factory=list)
    mapped_billing_resources: list[dict[str, Any]] = Field(default_factory=list)
    billing_gap_analysis: dict[str, Any] = Field(default_factory=dict)
    billing_reconciliation: dict[str, Any] = Field(default_factory=dict)
    final_billing_quote_items: list[CloudBillingFinalQuoteItem] = Field(default_factory=list)


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


ChatRole = Literal["user", "assistant"]
ChatBlockType = Literal["text", "solution_card", "pricing_card", "source_link"]
ChatSessionStatus = Literal["active"]
ChatStreamEventType = Literal["message_start", "message_delta", "message_block", "message_end", "error"]


class ChatUploadedFile(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    media_type: str | None = None
    created_at: str


class ChatUploadResponse(BaseModel):
    files: list[ChatUploadedFile] = Field(default_factory=list)


class ChatCardAction(BaseModel):
    label: str
    action_type: Literal["open_route", "open_upload", "suggest_prompt"]
    target: str


class ChatMessageBlock(BaseModel):
    block_type: ChatBlockType
    title: str | None = None
    body: str | None = None
    route: str | None = None
    image_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    action: ChatCardAction | None = None


class ChatMessage(BaseModel):
    message_id: str
    role: ChatRole
    text: str = ""
    blocks: list[ChatMessageBlock] = Field(default_factory=list)
    created_at: str


class ChatSessionResponse(BaseModel):
    session_id: str
    status: ChatSessionStatus = "active"
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ChatSessionCreatedResponse(BaseModel):
    session_id: str
    status: ChatSessionStatus = "active"
    created_at: str


class ChatMessageRequest(BaseModel):
    message: str
    language: LangKey = "en"
    file_ids: list[str] = Field(default_factory=list)
    web_search_enabled: bool = False


class ChatStreamEvent(BaseModel):
    event: ChatStreamEventType
    session_id: str
    message_id: str | None = None
    delta: str | None = None
    block: ChatMessageBlock | None = None
    error: str | None = None


# --- HLD Design models ---

HldDesignTaskStatus = Literal["queued", "running", "succeeded", "failed"]

HldDeploymentMode = Literal["on-prem", "cloud", "hybrid"]

HldDesignBias = Literal["huawei"]


class HldRequirements(BaseModel):
    project_name: str
    business_goal: str
    architecture_boundary: str
    deployment_mode: HldDeploymentMode
    user_access_entry: str
    core_components: str
    external_integrations: str
    data_stores_flow: str
    network_security_boundary: str
    preferred_filename: str | None = None
    language: LangKey = "en"
    design_bias: HldDesignBias = "huawei"

    @field_validator("deployment_mode", mode="before")
    @classmethod
    def normalize_deployment_mode(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        aliases = {
            "cloud": "cloud",
            "nube": "cloud",
            "云": "cloud",
            "hybrid": "hybrid",
            "híbrido": "hybrid",
            "hibrido": "hybrid",
            "混合": "hybrid",
            "on-prem": "on-prem",
            "on prem": "on-prem",
            "on-premises": "on-prem",
            "on premises": "on-prem",
            "本地": "on-prem",
        }
        return aliases.get(normalized, value)


class HldDesignTaskCreatedResponse(BaseModel):
    design_id: str
    status: HldDesignTaskStatus


class HldDesignTaskError(BaseModel):
    message: str
    detail: str | None = None
    last_stage: str | None = None


class HldDesignTaskResponse(BaseModel):
    design_id: str
    status: HldDesignTaskStatus
    current_stage: str | None = None
    error: HldDesignTaskError | None = None
    output_basename: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None


# --- HLD Recommendation models ---

HldWizardStep = Literal[
    "project_name",
    "business_goal",
    "architecture_boundary",
    "deployment_mode",
    "user_access_entry",
    "core_components",
    "external_integrations",
    "data_stores_flow",
    "network_security_boundary",
    "preferred_filename",
]

HldRecommendationSource = Literal["static", "rule", "llm", "fallback_default"]


class HldRecommendationRequest(BaseModel):
    step: HldWizardStep
    answers: dict[str, str] = Field(default_factory=dict)
    language: LangKey = "en"


class HldRecommendationResponse(BaseModel):
    recommended_answer: str
    source: HldRecommendationSource = "fallback_default"
    reasoning_summary: str | None = None
    answer_options: list[str] = Field(default_factory=list)


# --- Proposal models ---

ProposalTaskStatus = Literal["queued", "running", "succeeded", "failed"]
ProposalQuoteMode = Literal["skip", "rvtools", "flexible"]
ProposalQuoteStatus = Literal["skipped", "succeeded", "failed", "not_implemented", "pending_external_workflow"]
ProposalHldStatus = Literal["skipped", "succeeded", "failed", "pending_external_workflow"]


class ProposalQuoteInput(BaseModel):
    requirements: list[RequirementItem] = Field(default_factory=list)
    customer_notes: str = ""
    region: RegionKey | None = None


class ProposalQuoteSummary(BaseModel):
    total_monthly_price: float = 0
    currency: str = "USD"
    quoted_items: int = 0
    blocker_count: int = 0
    summary: str = ""


class ProposalQuoteResult(BaseModel):
    status: ProposalQuoteStatus
    mode: ProposalQuoteMode = "skip"
    summary: ProposalQuoteSummary = Field(default_factory=ProposalQuoteSummary)


ProposalContentStatus = Literal["generated", "fallback"]


class ProposalGeneratedSections(BaseModel):
    executive_summary: str = ""
    current_challenges: str = ""
    target_solution: str = ""
    pricing_summary: str = ""
    next_steps: str = ""
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ProposalContentResult(BaseModel):
    status: ProposalContentStatus
    model: str | None = None
    sections: ProposalGeneratedSections = Field(default_factory=ProposalGeneratedSections)
    error: str | None = None


ProposalHldMode = Literal["skip", "create_new"]
ProposalPriceMode = Literal["skip", "create_new"]


class ProposalRequest(BaseModel):
    project_name: str
    customer_name: str | None = None
    country: str | None = None
    language: LangKey = "en"
    customer_brief: str | None = None
    business_background: str = ""
    current_pain_points: str = ""
    target_outcomes: str = ""
    quote_mode: ProposalQuoteMode = "skip"
    quote_input: ProposalQuoteInput | None = None
    preferred_filename: str | None = None
    hld_requirements: HldRequirements | None = None
    # Content selection fields
    proposal_title: str | None = None
    proposal_subtitle: str | None = None
    include_hld: bool = False
    include_price: bool = False
    include_migration: bool = False
    include_support_training: bool = False
    include_huawei_capability: bool = True
    hld_mode: ProposalHldMode = "skip"
    price_mode: ProposalPriceMode = "skip"
    migration_scope: str | None = None
    migration_constraints: str | None = None
    migration_notes: str | None = None


class ProposalTaskCreatedResponse(BaseModel):
    task_id: str
    status: ProposalTaskStatus


class ProposalTaskError(BaseModel):
    message: str
    detail: str | None = None
    last_stage: str | None = None


class ProposalArtifactInfo(BaseModel):
    artifact_type: str
    filename: str
    size_bytes: int


class ProposalArtifacts(BaseModel):
    json_info: ProposalArtifactInfo | None = None
    pptx_info: ProposalArtifactInfo | None = None
    hld_png: ProposalArtifactInfo | None = None
    hld_drawio: ProposalArtifactInfo | None = None


class ProposalTaskResponse(BaseModel):
    task_id: str
    status: ProposalTaskStatus
    current_stage: str | None = None
    error: ProposalTaskError | None = None
    artifacts: ProposalArtifacts | None = None
    hld_design_id: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None
