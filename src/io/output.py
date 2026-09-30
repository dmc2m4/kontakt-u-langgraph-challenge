import json
from pathlib import Path

from ..domain.decisions import Decision
from ..domain.orders import Order


def write_decision(output_path: Path, decision: Decision) -> None:
    data = {
        "event_id": decision.event_id,
        "call_id": decision.call_id,
        "etiqueta": decision.label.value,
        "motivo": decision.reason,
        "confianza": decision.confidence,
        "ordenes": decision.order_ids,
    }

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False) + "\n")


def write_order(output_path: Path, order: Order) -> None:
    data = {
        "orden_id": order.order_id,
        "event_id": order.event_id,
        "operacion": order.operation,
        "idempotency_key": order.idempotency_key,
        "cuerpo": order.body,
    }

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False) + "\n")