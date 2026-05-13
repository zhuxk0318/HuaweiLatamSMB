from __future__ import annotations

from io import BytesIO
from typing import Literal

from pydantic import BaseModel, Field


ActionType = Literal["quote", "exclude_powered_off", "manual_review"]
RegionKey = Literal["mexico", "chile", "brazil"]
EvsTypeKey = Literal["gpssd", "sas"]
LangKey = Literal["es", "en", "zh"]


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
