"""
Typed contracts for the agent team.

``AdaptationPlan``  the plan an agent produces.  It is schema-validated, it
                   must cite the provenance ids of the evidence it used, and
                   it carries the self-assessed confidence that drives the
                   escalation gate.
``AgentState``      the shared state threaded through the LangGraph nodes.
``SCVVerdict``      the outcome of the symbolic constraint verification.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field


class PlannedActivity(BaseModel):
    """A single activity in an adaptation plan."""
    activity_name: str
    role: str = 'system'
    data_payload: dict = Field(default_factory=dict)
    temporal_guard: Optional[str] = None
    is_write: bool = False


class AdaptationPlan(BaseModel):
    """The adaptation proposed for one case."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    activities: list[PlannedActivity] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ''
    goal_reachable: bool = True
    all_intents: list[dict] = Field(default_factory=list)


class ViolationDetail(BaseModel):
    """One constraint violation detected by the SCV."""
    constraint_id: str
    constraint_type: str
    offending_step: int = -1
    severity: str = 'hard'
    violation_cost: float = 0.0
    min_cost_repair: Optional[dict] = None


class ViolationReport(BaseModel):
    """All violations detected for one plan."""
    violations: list[ViolationDetail] = Field(default_factory=list)
    total_cost: float = 0.0


class SCVVerdict(BaseModel):
    """Result of a symbolic constraint verification."""
    passed: bool
    token: Optional[str] = None
    violation_report: Optional[dict] = None


class AgentState(TypedDict, total=False):
    """Shared LangGraph state."""
    perturbation: dict
    prefix_trace: list
    process_state: dict
    evidence: list
    constraint_graph_data: dict
    plan: Optional[dict]
    violation_report: Optional[dict]
    scv_passed: bool
    repair_round: int
    escalate: bool
    escalation_reason: str
    messages: list
    token_counts: dict
    llm_calls: int
    agent_intents: list
    result: dict
    extras: dict
