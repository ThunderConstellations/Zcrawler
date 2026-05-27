from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
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
    template_key: str
    status: str
    reference_address: str
    city_query: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    findings_count: int
    error_message: Optional[str] = None


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
    created_at: datetime


class RunResultsResponse(BaseModel):
    run: CrawlRunResponse
    findings: List[CrawlFindingResponse]
