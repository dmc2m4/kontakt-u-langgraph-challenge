from langgraph.graph import END, START, StateGraph

from .nodes import (
    apply_business_rules,
    classify_call,
    plan_orders,
    validate_event,
)
from .state import GraphState


def route_after_validation(state: GraphState) -> str:
    if state.get("is_other_organization"):
        return "plan_orders"

    if state.get("is_duplicate"):
        return "plan_orders"

    if state["event"].type.value == "message.received":
        return "plan_orders"

    return "classify_call"


def build_workflow():
    graph = StateGraph(GraphState)

    graph.add_node("validate_event", validate_event)
    graph.add_node("classify_call", classify_call)
    graph.add_node("apply_business_rules", apply_business_rules)
    graph.add_node("plan_orders", plan_orders)

    graph.add_edge(START, "validate_event")

    graph.add_conditional_edges(
        "validate_event",
        route_after_validation,
        {
            "classify_call": "classify_call",
            "plan_orders": "plan_orders",
        },
    )

    graph.add_edge("classify_call", "apply_business_rules")
    graph.add_edge("apply_business_rules", "plan_orders")
    graph.add_edge("plan_orders", END)

    return graph.compile()
