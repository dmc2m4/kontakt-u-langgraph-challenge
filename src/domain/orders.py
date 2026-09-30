from typing import Any

from pydantic import BaseModel, Field


class Order(BaseModel):
    order_id: str
    event_id: str
    operation: str
    idempotency_key: str
    body: dict[str, Any] = Field(default_factory=dict)