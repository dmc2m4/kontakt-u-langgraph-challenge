from langgraph.graph import END, START, StateGraph

from .nodes import (
    apply_business_rules,
    classify_call,
    plan_orders,
    validate_event,
)
from .state import GraphState


def build_workflow():
    graph = StateGraph(GraphState)

    graph.add_node("validate_event", validate_event)
    graph.add_node("classify_call", classify_call)
    graph.add_node("apply_business_rules", apply_business_rules)
    graph.add_node("plan_orders", plan_orders)

    graph.add_edge(START, "validate_event")
    graph.add_edge("validate_event", "classify_call")
    graph.add_edge("classify_call", "apply_business_rules")
    graph.add_edge("apply_business_rules", "plan_orders")
    graph.add_edge("plan_orders", END)

    return graph.compile()