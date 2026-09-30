import json
from pathlib import Path
from typing import Iterator

from ..domain.models import Event


def load_events(events_dir: Path) -> Iterator[Event]:
    for event_file in sorted(events_dir.glob("*.json")):
        with event_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        yield Event.model_validate(data)