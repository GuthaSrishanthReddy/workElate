from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Intent(str, Enum):
    CRAWL_SITE = "crawl_site"
    NEED_INPUT = "need_input"
    UNSUPPORTED = "unsupported"


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    url: str | None = None
    max_pages: int = Field(default=10, ge=1, le=25)
    max_depth: int = Field(default=2, ge=0, le=3)
    want_summary: bool = True
    want_json: bool = True
    focus: list[str] = Field(default_factory=list, max_length=12)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    job_id: str | None = None
    reply: str | None = None
    planner: Literal["llm", "regex"]


class CrawlEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str


class PageResult(BaseModel):
    url: HttpUrl
    title: str
    status_code: int
    headings: list[str] = Field(default_factory=list)
    word_count: int = 0
    excerpt: str = ""
    meta_description: str = ""
    language: str = ""
    h1_to_h3: list[str] = Field(default_factory=list)
    main_text: str = ""
    internal_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    start_url: HttpUrl
    domain: str
    crawled_at: datetime


class ExecutionInfo(BaseModel):
    tool: Literal["sitecrawl"] = "sitecrawl"
    tool_version: str = "0.1.0"
    exit_code: int
    duration_ms: int
    pages_ok: int = 0
    pages_failed: int = 0
    robots_respected: bool = True


class KeyPoint(BaseModel):
    point: str
    source_url: HttpUrl


class SummaryInfo(BaseModel):
    text: str
    key_points: list[KeyPoint] = Field(default_factory=list)
    generated_by: Literal["llm", "extractive"]


class Contacts(BaseModel):
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)


class ExtractedInfo(BaseModel):
    site_title: str = ""
    description: str = ""
    language: str = ""
    pages: list[PageResult] = Field(default_factory=list)
    contacts: Contacts = Field(default_factory=Contacts)
    social_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    requested_fields: dict[str, list[dict[str, str]]] = Field(default_factory=dict)


class CrawlError(BaseModel):
    url: str
    type: str
    message: str


class Result(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["success", "partial", "failed"]
    source: SourceInfo
    execution: ExecutionInfo
    summary: SummaryInfo | None = None
    extracted: ExtractedInfo
    errors: list[CrawlError] = Field(default_factory=list)


class JobState:
    def __init__(self, job_id: str):
        self.id = job_id
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.cancelled = False
        self.process: Any = None
        self.result: Result | None = None
        self.reply: str | None = None
        self.temp_dir: str | None = None
        self.stderr_tail: list[str] = []
        self.started_at = datetime.now(timezone.utc)
        self.exit_code: int | None = None
        self.duration_ms: int = 0
        self.killed: str | None = None
        self.argv: list[str] = []
