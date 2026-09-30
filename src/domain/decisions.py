from pydantic import BaseModel, Field

from .models import DecisionLabel


class Decision(BaseModel):
    event_id: str
    call_id: str | None = None
    label: DecisionLabel
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    order_ids: list[str] = Field(default_factory=list)