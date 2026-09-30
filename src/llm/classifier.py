from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ..domain.models import DecisionLabel


PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "call_classification.md"
)


class CallClassification(BaseModel):
    label: DecisionLabel
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    callback_requested_at: str | None = None
    context_note: str | None = None


class CallClassifier:
    def __init__(self, model: str, api_key: str) -> None:
        prompt = PROMPT_PATH.read_text(encoding="utf-8")

        self.classifier = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0,
        ).with_structured_output(CallClassification)

        self.prompt = prompt

    def classify(self, event: dict[str, Any]) -> CallClassification:
        return self.classifier.invoke(
            [
                {
                    "role": "system",
                    "content": self.prompt,
                },
                {
                    "role": "user",
                    "content": self._build_event_context(event),
                },
            ]
        )

    @staticmethod
    def _build_event_context(event: dict[str, Any]) -> str:
        return (
            "Classify the following call event.\n\n"
            "Event data:\n"
            f"{event}"
        )