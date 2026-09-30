from datetime import datetime, timezone

from ..config.loader import load_campaign_config, load_openai_config
from ..domain.decisions import Decision
from ..domain.models import DecisionLabel, EventType
from ..domain.order_planner import plan_event_orders
from ..domain.rules import deterministic_classification, normalize_classification
from ..llm.classifier import CallClassifier
from .state import GraphState


def validate_event(state: GraphState) -> GraphState:
    event = state["event"]
    config = load_campaign_config()
    expected_organization = config["campana"]["organization_id"]

    if event.organization_id != expected_organization:
        return {
            **state,
            "is_valid": True,
            "is_duplicate": False,
            "is_other_organization": True,
        }

    store = state["store"]
    processed = store.get_processed_event(event.idempotency_key)

    if processed is not None:
        return {
            **state,
            "is_valid": True,
            "is_duplicate": True,
            "is_other_organization": False,
            "processed_label": processed["label"],
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

    if state.get("is_duplicate") or state.get("is_other_organization"):
        return state

    event = state["event"]

    if event.type != EventType.CALL_ENDED:
        return state

    deterministic = deterministic_classification(event)

    if deterministic is not None:
        return {
            **state,
            "classification": deterministic,
        }

    openai_config = load_openai_config()
    classifier = CallClassifier(
        model=openai_config["model"],
        api_key=openai_config["api_key"],
    )

    classification = classifier.classify(event.model_dump(mode="json"))
    normalized = normalize_classification(
        event,
        classification.model_dump(mode="json"),
    )

    return {
        **state,
        "classification": normalized,
    }


def apply_business_rules(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    if state.get("is_duplicate") or state.get("is_other_organization"):
        return state

    event = state["event"]

    if event.type != EventType.CALL_ENDED:
        return state

    classification = state["classification"]
    label = DecisionLabel(classification["label"])
    store = state["store"]

    if label in {
        DecisionLabel.CORTADA,
        DecisionLabel.VISITA_SIN_CONFIRMAR,
    }:
        previous_cut_calls = store.count_cut_calls(event.lead.contact_id)
        call_id = event.telephony.call_id if event.telephony else event.event_id
        store.save_cut_call(
            event.lead.contact_id,
            call_id,
            event.occurred_at.isoformat(),
        )
    else:
        previous_cut_calls = 0

    attempt_number = store.register_call_attempt(event.lead.contact_id)

    config = load_campaign_config()
    retry_config = config["reintentos"]
    max_attempts = int(retry_config["max_intentos"])

    business_rules = {
        "attempt_number": attempt_number,
        "action": "none",
    }

    if label in {
        DecisionLabel.OCUPADO,
        DecisionLabel.SIN_RESPUESTA,
        DecisionLabel.BUZON,
    }:
        action = "retry" if attempt_number < max_attempts else "fallback"
        business_rules["action"] = action

    if label in {
        DecisionLabel.CORTADA,
        DecisionLabel.VISITA_SIN_CONFIRMAR,
    }:
        business_rules["action"] = "retry"
        business_rules["second_cut"] = previous_cut_calls >= 1

    if label == DecisionLabel.RECHAZADA:
        business_rules["action"] = "fallback"

    if label == DecisionLabel.OTRO:
        business_rules["action"] = "review"

    if label == DecisionLabel.NO_CONTACTAR:
        business_rules["action"] = "dnc"

    return {
        **state,
        "business_rules": business_rules,
    }


def plan_orders(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    event = state["event"]

    if state.get("is_other_organization"):
        return _set_decision(
            state,
            DecisionLabel.NO_APLICA,
            "El evento pertenece a otra organización.",
            1.0,
            [],
        )

    if state.get("is_duplicate"):
        label_value = state.get("processed_label") or DecisionLabel.NO_APLICA.value
        label = DecisionLabel(label_value)
        reason = "Reentrega del mismo evento; se reutiliza la decisión original sin emitir nuevas órdenes."
        return _set_decision(
            state,
            label,
            reason,
            1.0,
            [],
        )

    if event.type == EventType.MESSAGE_RECEIVED:
        orders = plan_event_orders(event, None, state)
        return _set_decision(
            state,
            DecisionLabel.NO_APLICA,
            "Mensaje recibido del lead; se gestionan los recordatorios pendientes.",
            1.0,
            orders,
        )

    classification = state["classification"]
    label = DecisionLabel(classification["label"])
    orders = plan_event_orders(event, label, state)

    return _set_decision(
        state,
        label,
        classification["reason"],
        float(classification["confidence"]),
        orders,
    )


def _set_decision(
    state: GraphState,
    label: DecisionLabel,
    reason: str,
    confidence: float,
    orders,
) -> GraphState:
    event = state["event"]
    call_id = (
        event.telephony.call_id
        if event.telephony is not None
        else None
    )

    decision = Decision(
        event_id=event.event_id,
        call_id=call_id,
        label=label,
        reason=reason,
        confidence=max(0.0, min(1.0, confidence)),
        order_ids=[order.order_id for order in orders],
    )

    return {
        **state,
        "orders": orders,
        "decision": decision,
    }


def processed_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
