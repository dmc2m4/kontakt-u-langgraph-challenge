from typing import Any

from typing_extensions import TypedDict

from ..domain.decisions import Decision
from ..domain.models import Event
from ..domain.orders import Order
from ..persistence.store import StateStore


class GraphState(TypedDict, total=False):
    event: Event
    store: StateStore
    is_valid: bool
    is_duplicate: bool
    is_other_organization: bool
    processed_label: str | None
    classification: dict[str, Any]
    business_rules: dict[str, Any]
    decision: Decision
    orders: list[Order]
    error: str | None
