"""
合规审查工作流 — LangGraph StateGraph。

Agent 链:
Listing 内容 → [1.政策检查] → [2.声明验证] → [3.风险报告] → Compliance Report
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.compliance.policy_checker import PolicyCheckerAgent, PolicyCheckerInput
from backend.app.agents.compliance.claim_verifier import ClaimVerifierAgent, ClaimVerifierInput
from backend.app.agents.compliance.risk_reporter import RiskReporterAgent, RiskReporterInput


class ComplianceState(TypedDict):
    task_id: str
    title: str
    bullet_points: list[str]
    description: str
    category: str
    product_features: list[str]
    platform: str

    policy_issues: list[dict]
    claim_issues: list[dict]
    overall_verdict: str
    risk_level: str
    total_issues: int
    critical_items: list[str]
    action_items: list[str]
    summary: str

    status: str
    error: str
    current_step: str


policy_agent = PolicyCheckerAgent()
claim_agent = ClaimVerifierAgent()
risk_agent = RiskReporterAgent()


async def policy_node(state: ComplianceState) -> ComplianceState:
    try:
        result = await policy_agent.run(
            PolicyCheckerInput(
                title=state["title"], bullet_points=state["bullet_points"],
                description=state["description"], category=state["category"],
                platform=state["platform"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["policy_issues"] = [i.model_dump() for i in result.issues]
        state["current_step"] = "policy_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def claim_node(state: ComplianceState) -> ComplianceState:
    if state["status"] == "failed":
        return state
    try:
        result = await claim_agent.run(
            ClaimVerifierInput(
                title=state["title"], bullet_points=state["bullet_points"],
                description=state["description"], product_features=state["product_features"],
                category=state["category"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["claim_issues"] = [c.model_dump() for c in result.claims_found]
        state["current_step"] = "claim_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def report_node(state: ComplianceState) -> ComplianceState:
    if state["status"] == "failed":
        return state
    try:
        result = await risk_agent.run(
            RiskReporterInput(
                policy_issues=state["policy_issues"],
                claim_issues=state["claim_issues"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["overall_verdict"] = result.overall_verdict
        state["risk_level"] = result.risk_level
        state["total_issues"] = result.total_issues
        state["critical_items"] = result.critical_items
        state["action_items"] = result.action_items
        state["summary"] = result.summary
        state["current_step"] = "report_done"
        state["status"] = "awaiting_review"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def build_compliance_workflow() -> StateGraph:
    workflow = StateGraph(ComplianceState)
    workflow.add_node("policy_check", policy_node)
    workflow.add_node("claim_verify", claim_node)
    workflow.add_node("risk_report", report_node)
    workflow.set_entry_point("policy_check")
    workflow.add_edge("policy_check", "claim_verify")
    workflow.add_edge("claim_verify", "risk_report")
    workflow.add_edge("risk_report", END)
    return workflow


compliance_workflow = build_compliance_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["risk_report"],
)
