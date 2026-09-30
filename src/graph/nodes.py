from ..config.loader import load_campaign_config, load_openai_config
from ..domain.models import EventType
from ..llm.classifier import CallClassifier
from .state import GraphState
from ..domain.rules import normalize_classification
from ..domain.models import DecisionLabel
from ..domain.rules import determine_retry
from ..domain.scheduling import (
    schedule_busy_retry,
    schedule_general_retry,
)


def validate_event(state: GraphState) -> GraphState:
    event = state["event"]

    campaign_config = load_campaign_config()
    expected_organization = campaign_config["campana"]["organization_id"]

    if event.organization_id != expected_organization:
        return {
            **state,
            "is_valid": True,
            "is_duplicate": False,
            "is_other_organization": True,
        }

    store = state["store"]

    if store.get_processed_event(event.idempotency_key) is not None:
        return {
            **state,
            "is_valid": True,
            "is_duplicate": True,
            "is_other_organization": False,
        }

    if event.type not in {
        EventType.CALL_ENDED,
        EventType.MESSAGE_RECEIVED,
    }:
        return {
            **state,
            "is_valid": False,
            "is_duplicate": False,
            "is_other_organization": False,
            "error": f"Unsupported event type: {event.type}",
        }

    return {
        **state,
        "is_valid": True,
        "is_duplicate": False,
        "is_other_organization": False,
    }


def classify_call(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    if state.get("is_duplicate"):
        return state

    if state.get("is_other_organization"):
        return state

    event = state["event"]

    if event.type != EventType.CALL_ENDED:
        return state

    openai_config = load_openai_config()

    classifier = CallClassifier(
        model=openai_config["model"],
        api_key=openai_config["api_key"],
    )

    classification = classifier.classify(
        event.model_dump(mode="json")
    )

    normalized_classification = normalize_classification(
        event,
        classification.model_dump(mode="json"),
    )

    return {
        **state,
        "classification": normalized_classification,
    }


def apply_business_rules(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    if state.get("is_duplicate"):
        return state

    if state.get("is_other_organization"):
        return state

    event = state["event"]

    if event.type != EventType.CALL_ENDED:
        return state

    classification = state["classification"]
    label = DecisionLabel(classification["label"])

    attempt_number = state["store"].register_call_attempt(
        event.lead.contact_id
    )

    campaign_config = load_campaign_config()
    retry_config = campaign_config["reintentos"]

    max_attempts = int(retry_config["max_intentos"])

    action = determine_retry(
        label=label,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )

    decision_data = {
        "attempt_number": attempt_number,
        "action": action,
    }

    if action == "retry":
        if label == DecisionLabel.OCUPADO:
            decision_data["scheduled_at"] = schedule_busy_retry(
                event.occurred_at
            ).isoformat()
        else:
            decision_data["scheduled_at"] = schedule_general_retry(
                event.occurred_at
            ).isoformat()

    if action == "fallback":
        decision_data["fallback_channel"] = campaign_config[
            "canal_respaldo"
        ]

    return {
        **state,
        "classification": {
            **classification,
            "business_rules": decision_data,
        },
    }


def plan_orders(state: GraphState) -> GraphState:
    return state