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

    processed = state["store"].get_processed_event(event.idempotency_key)

    if processed is not None:
        return {
            **state,
            "is_valid": True,
            "is_duplicate": True,
            "is_other_organization": False,
            "processed_label": processed["label"],
        }

    is_dnc = (
        event.type == EventType.CALL_ENDED
        and state["store"].is_dnc(event.lead.contact_id)
    )

    return {
        **state,
        "is_valid": True,
        "is_duplicate": False,
        "is_other_organization": False,
        "is_dnc": is_dnc,
    }


def classify_call(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    if (
        state.get("is_duplicate")
        or state.get("is_other_organization")
        or state.get("is_dnc")
    ):
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

    return {
        **state,
        "classification": normalize_classification(
            event,
            classification.model_dump(mode="json"),
        ),
    }


def apply_business_rules(state: GraphState) -> GraphState:
    if not state.get("is_valid"):
        return state

    if (
        state.get("is_duplicate")
        or state.get("is_other_organization")
        or state.get("is_dnc")
    ):
        return state

    event = state["event"]

    if event.type != EventType.CALL_ENDED:
        return state

    classification = state["classification"]
    label = DecisionLabel(classification["label"])
    store = state["store"]

    previous_cut_calls = 0

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

    attempt_number = store.register_call_attempt(event.lead.contact_id)

    config = load_campaign_config()
    max_attempts = int(config["reintentos"]["max_intentos"])

    business_rules = {
        "attempt_number": attempt_number,
        "action": "none",
    }

    retryable_labels = {
        DecisionLabel.OCUPADO,
        DecisionLabel.SIN_RESPUESTA,
        DecisionLabel.BUZON,
        DecisionLabel.CORTADA,
        DecisionLabel.VISITA_SIN_CONFIRMAR,
    }

    if label in retryable_labels:
        business_rules["action"] = (
            "retry" if attempt_number < max_attempts else "fallback"
        )

    if label in {
        DecisionLabel.CORTADA,
        DecisionLabel.VISITA_SIN_CONFIRMAR,
    }:
        business_rules["second_cut"] = previous_cut_calls >= 1

    if label in {
        DecisionLabel.RECHAZADA,
        DecisionLabel.NO_CONTACTAR,
        DecisionLabel.OTRO,
    }:
        business_rules["action"] = {
            DecisionLabel.RECHAZADA: "fallback",
            DecisionLabel.NO_CONTACTAR: "dnc",
            DecisionLabel.OTRO: "review",
        }[label]

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
        return _set_decision(
            state,
            label,
            "Reentrega del mismo evento; se reutiliza la decisión original sin emitir nuevas órdenes.",
            1.0,
            [],
        )

    if state.get("is_dnc"):
        return _set_decision(
            state,
            DecisionLabel.NO_APLICA,
            "El lead está marcado como no contactar y no se emiten nuevas órdenes.",
            1.0,
            [],
        )

    if event.type == EventType.MESSAGE_RECEIVED:
        orders = plan_event_orders(event, None, state)
        return _set_decision(
            state,
            DecisionLabel.NO_APLICA,
            "Mensaje recibido del lead; se cancelan los recordatorios pendientes.",
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
    call_id = event.telephony.call_id if event.telephony else None

    return {
        **state,
        "orders": orders,
        "decision": Decision(
            event_id=event.event_id,
            call_id=call_id,
            label=label,
            reason=reason,
            confidence=max(0.0, min(1.0, confidence)),
            order_ids=[order.order_id for order in orders],
        ),
    }


def processed_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
