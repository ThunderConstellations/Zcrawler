from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CrawlerDefinitionBase(BaseModel):
    name: str
    description: Optional[str] = None
    template_key: str
    recipe_type: Optional[str] = None
    ai_prompt: Optional[str] = None
    config_json: str


class CrawlerDefinitionCreate(CrawlerDefinitionBase):
    pass


class CrawlerDefinitionResponse(CrawlerDefinitionBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateRunRequest(BaseModel):
    definition_id: Optional[str] = Field(
        None, description="The ID of the crawler definition to run."
    )
    # Fields for ad-hoc or backward compatibility
    reference_address: str = Field(
        ..., description="Address used as distance anchor."
    )
    city_query: str = Field(
        ..., description="City query for Nominatim area lookup."
    )
    enable_reverse_geocode: bool = Field(
        default=True, description="Enrich nearest missing street addresses."
    )
    max_reverse_geocode_lookups: int = Field(
        default=10, description="Cap reverse-geocode lookups per run."
    )


class CrawlRunResponse(BaseModel):
    id: str
    definition_id: Optional[str] = None
    template_key: str
    status: str
    reference_address: str
    city_query: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    findings_count: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class CrawlFindingResponse(BaseModel):
    id: int
    run_id: str
    name: str
    business_type: str
    phone: str
    website: str
    email: str
    opening_hours: str
    location: str
    latitude: float
    longitude: float
    distance_miles: float
    quality_score: int
    source: Optional[str] = None

    # Enrichment
    description: Optional[str] = None
    social_links: Optional[str] = None
    ai_summary: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True


class RunResultsResponse(BaseModel):
    run: CrawlRunResponse
    findings: List[CrawlFindingResponse]

class CrawlerScheduleBase(BaseModel):
    definition_id: str
    name: str
    cron_expr: str
    is_active: bool = True

class CrawlerScheduleCreate(CrawlerScheduleBase):
    pass

class CrawlerScheduleResponse(CrawlerScheduleBase):
    id: str
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
