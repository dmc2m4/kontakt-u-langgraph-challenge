from ..domain.models import Event
from .state import GraphState


def validate_event(state: GraphState) -> GraphState:
    return state


def classify_call(state: GraphState) -> GraphState:
    return state


def apply_business_rules(state: GraphState) -> GraphState:
    return state


def plan_orders(state: GraphState) -> GraphState:
    return state