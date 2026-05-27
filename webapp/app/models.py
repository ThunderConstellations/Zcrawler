from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    """Generate a unique id suitable for URLs and DB keys."""

    return str(uuid.uuid4())


class CrawlerDefinition(Base):
    __tablename__ = "crawler_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    template_key: Mapped[str] = mapped_column(String(100), index=True)
    config_json: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    runs: Mapped[list["CrawlRun"]] = relationship(
        back_populates="definition", cascade="all, delete-orphan"
    )


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("crawler_definitions.id", ondelete="SET NULL"), nullable=True
    )
    template_key: Mapped[str] = mapped_column(String(100), index=True)

    status: Mapped[str] = mapped_column(String(30), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    reference_address: Mapped[str] = mapped_column(Text)
    city_query: Mapped[str] = mapped_column(Text)
    params_json: Mapped[str] = mapped_column(Text)

    output_dir: Mapped[str] = mapped_column(Text)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    definition: Mapped[CrawlerDefinition | None] = relationship(back_populates="runs")
    findings: Mapped[list["CrawlFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CrawlFinding(Base):
    __tablename__ = "crawl_findings"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(Text, index=True)
    business_type: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    website: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    opening_hours: Mapped[str] = mapped_column(Text)

    location: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    distance_miles: Mapped[float] = mapped_column(Float, index=True)
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    run: Mapped[CrawlRun] = relationship(back_populates="findings")
