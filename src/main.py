import json
import sys
from pathlib import Path

from .graph.workflow import build_workflow
from .io.events import load_events
from .io.output import write_decision, write_order
from .persistence.store import StateStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "salida"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / ".state.sqlite"


def process_event(
    event_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> None:
    with event_path.open("r", encoding="utf-8") as file:
        raw_event = json.load(file)

    events = list(load_events(event_path.parent))
    event = next(
        candidate
        for candidate in events
        if candidate.event_id == raw_event["event_id"]
    )

    store = StateStore(database_path)

    try:
        workflow = build_workflow()
        state = workflow.invoke(
            {
                "event": event,
                "store": store,
            }
        )

        decision = state.get("decision")
        if decision is None:
            raise RuntimeError("The workflow did not produce a decision.")

        orders = state.get("orders", [])

        decisions_path = output_dir / "decisiones.jsonl"
        orders_path = output_dir / "ordenes.jsonl"

        write_decision(decisions_path, decision)

        for order in orders:
            write_order(orders_path, order)
            store.save_order(
                order_id=order.order_id,
                event_id=order.event_id,
                idempotency_key=order.idempotency_key,
                operation=order.operation,
                body=order.body,
                created_at=event.occurred_at.isoformat(),
            )

        if not state.get("is_duplicate"):
            store.save_processed_event(
                idempotency_key=event.idempotency_key,
                event_id=event.event_id,
                processed_at=event.occurred_at.isoformat(),
                label=decision.label.value,
            )
    finally:
        store.close()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python run.py <event_file>", file=sys.stderr)
        return 2

    event_path = Path(sys.argv[1])

    if not event_path.is_file():
        print(f"Event file not found: {event_path}", file=sys.stderr)
        return 2

    try:
        process_event(event_path)
    except Exception as exc:
        print(f"Error processing event: {exc}", file=sys.stderr)
        return 1

    return 0
