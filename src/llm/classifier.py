from typing import Any


class CallClassifier:
    def __init__(self, model: str) -> None:
        self.model = model

    def classify(self, event: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError