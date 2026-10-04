from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProcessNode(BaseModel):
    id: str
    name: str
    role: str
    sla_days: int = 1
    description: str = ""


class ProcessGateway(BaseModel):
    id: str
    when: str = Field(description="Python-like condition, e.g. amount >= 10000")
    then: str = Field(description="Node id to insert / route to")
    else_to: str | None = None


class ProcessEdge(BaseModel):
    source: str
    target: str
    condition: str | None = None


class ProcessTemplate(BaseModel):
    id: str
    name: str
    category: str
    version: str = "1"
    policy_refs: list[str] = Field(default_factory=list)
    nodes: list[ProcessNode]
    edges: list[ProcessEdge]
    gateways: list[ProcessGateway] = Field(default_factory=list)
    approved: bool = False
    source: str = "manual"


class CaseEvent(BaseModel):
    at: datetime
    node_id: str
    node_name: str
    role: str
    action: Literal["submit", "approve", "reject", "pending"] = "pending"
    note: str = ""


class ApprovalCase(BaseModel):
    case_id: str
    title: str
    template_id: str
    category: str
    amount: float = 0
    level: str = ""
    dept: str
    applicant: str
    submit_at: datetime
    current_node: str
    status: Literal["running", "completed", "rejected"] = "running"
    fields: dict[str, Any] = Field(default_factory=dict)
    history: list[CaseEvent] = Field(default_factory=list)
    stall_code: str = ""
    stall_note: str = ""


class TimelineStep(BaseModel):
    date: date
    node_id: str
    node_name: str
    role: str
    status: Literal["done", "current", "planned"]
    summary: str


class PortfolioItem(BaseModel):
    case_id: str
    title: str
    category: str
    level: str
    dept: str
    applicant: str
    current_role: str
    current_node_name: str
    next_summary: str
    planned_start: date
    planned_end: date
    actual_start: date
    actual_end: date | None
    duration_days: int
    status: str
    template_id: str
    stall_code: str = ""
    stall_reason: str = ""
    delay_days: int = 0
    load_level: str = ""


class PortfolioResponse(BaseModel):
    items: list[PortfolioItem]
    total: int


class CaseDetail(BaseModel):
    case: ApprovalCase
    timeline: list[TimelineStep]
    next_summary: str
    bpmn_xml: str
    report: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    stall_reason: str = ""
    delay_days: int = 0
    department_load: dict[str, Any] = Field(default_factory=dict)


class Department(BaseModel):
    id: str
    name: str
    parallel_limit: int = 2


class DepartmentDayLoad(BaseModel):
    id: str
    name: str
    parallel_limit: int
    load: int
    level: Literal["idle", "busy", "saturated"]
    delay_days: int = 0
    cases: list[dict[str, Any]] = Field(default_factory=list)


class CalendarDay(BaseModel):
    date: date
    overall: Literal["idle", "busy", "saturated"]
    departments: list[DepartmentDayLoad]


class LearnedFunction(BaseModel):
    id: str
    name: str
    category: str
    action: Literal["created", "updated", "unchanged"]
    template_id: str
    version: str = "1"
    policy: str = ""
    summary: str = ""


class LearningReport(BaseModel):
    filename: str
    chunks: int = 0
    agents: list[str] = Field(default_factory=list)
    functions: list[LearnedFunction] = Field(default_factory=list)
    template: dict[str, Any] | None = None
    notes: str = ""


class SubmitCaseRequest(BaseModel):
    title: str
    template_id: str
    amount: float = 0
    dept: str
    applicant: str
    level: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)


class DeleteCasesRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)


class ExtractTemplateRequest(BaseModel):
    policy_filename: str
    template_id: str | None = None
    approve: bool = True


class PolicyAskRequest(BaseModel):
    question: str
    top_k: int = 5


class EvalResult(BaseModel):
    total: int
    correct: int
    accuracy: float
    details: list[dict[str, Any]]
