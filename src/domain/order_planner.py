import hashlib
from datetime import datetime

from .models import DecisionLabel, Event, EventType
from .orders import Order
from .scheduling import (
    add_business_days,
    add_natural_hours,
    appointment_task_due,
    default_task_due,
    schedule_busy_retry,
    schedule_cut_retry,
    schedule_general_retry,
    get_timezone,
)


QUEUE_STATUS = {
    DecisionLabel.VISITA_RESERVADA: "successful",
    DecisionLabel.DOCUMENTACION_ENVIADA: "completed",
    DecisionLabel.CALLBACK: "callback_requested",
    DecisionLabel.SIN_RESPUESTA: "no_answer",
    DecisionLabel.OCUPADO: "no_answer",
    DecisionLabel.BUZON: "no_answer",
    DecisionLabel.CORTADA: "needs_review",
    DecisionLabel.VISITA_SIN_CONFIRMAR: "needs_review",
    DecisionLabel.PERSONA_EQUIVOCADA: "failed",
    DecisionLabel.NO_CONTACTAR: "dnc",
    DecisionLabel.RECHAZADA: "refused",
    DecisionLabel.DOCUMENTACION_PENDIENTE: "completed",
    DecisionLabel.DESCARTADO: "skipped",
    DecisionLabel.OTRO: "needs_review",
}


def plan_event_orders(event: Event, label: DecisionLabel | None, state) -> list[Order]:
    if event.type == EventType.MESSAGE_RECEIVED:
        return _plan_message_orders(event, state)

    if label is None:
        return []

    orders = [_close_call_order(event, label, state)]

    if label == DecisionLabel.VISITA_RESERVADA:
        orders.append(_visit_task_order(event, state))
    elif label == DecisionLabel.DOCUMENTACION_ENVIADA:
        orders.extend(_documentation_orders(event, state))
    elif label == DecisionLabel.CALLBACK:
        orders.extend(_callback_orders(event, state))
    elif label == DecisionLabel.SIN_RESPUESTA:
        orders.append(_retry_call_order(event, "sin respuesta", state))
    elif label == DecisionLabel.OCUPADO:
        orders.append(_retry_or_fallback_order(event, label, state))
    elif label == DecisionLabel.BUZON:
        orders.append(_retry_or_fallback_order(event, label, state))
    elif label == DecisionLabel.CORTADA:
        orders.append(_cut_retry_order(event, state))
        if state["business_rules"].get("second_cut"):
            orders.append(_review_task_order(event, "segunda llamada cortada"))
    elif label == DecisionLabel.VISITA_SIN_CONFIRMAR:
        orders.append(_cut_retry_order(event, state))
        if state["business_rules"].get("second_cut"):
            orders.append(_review_task_order(event, "segunda llamada con visita acordada pero no reservada"))
    elif label == DecisionLabel.PERSONA_EQUIVOCADA:
        orders.append(_verify_phone_task_order(event, state))
    elif label == DecisionLabel.NO_CONTACTAR:
        orders.append(_dnc_order(event, state))
    elif label == DecisionLabel.RECHAZADA:
        orders.append(_fallback_whatsapp_order(event, state))
    elif label == DecisionLabel.DOCUMENTACION_PENDIENTE:
        orders.append(_documentation_email_task_order(event, state))
    elif label == DecisionLabel.OTRO:
        orders.append(_review_task_order(event, "evento no encaja en los casos soportados"))
    elif label == DecisionLabel.DESCARTADO:
        pass

    return orders


def _close_call_order(event: Event, label: DecisionLabel, state) -> Order:
    body = {
        "entry_id": event.campaign.entry_id,
        "status": QUEUE_STATUS[label],
        "etiqueta": label.value,
        "motivo": state["classification"]["reason"],
        "confianza": float(state["classification"]["confidence"]),
    }

    if event.telephony:
        body["duration_seconds"] = event.telephony.duration_seconds

    return _order(event, "cerrar_llamada", body)


def _retry_or_fallback_order(
    event: Event,
    label: DecisionLabel,
    state,
) -> Order:
    if state["business_rules"]["action"] == "retry":
        if label == DecisionLabel.OCUPADO:
            scheduled_at = schedule_busy_retry(event.occurred_at)
            reason = "línea comunicando, reintento corto"
        else:
            scheduled_at = schedule_general_retry(event.occurred_at)
            reason = "sin contacto efectivo, reintento según separación mínima"

        body = {
            "entry_id": event.campaign.entry_id,
            "telefono": event.lead.phone,
            "no_antes_de": scheduled_at.isoformat(),
            "motivo": reason,
            "nota_contexto": "no se llegó a hablar con el lead",
        }
        return _order(event, "programar_llamada", body)

    return _fallback_whatsapp_order(event, state)


def _retry_call_order(event: Event, reason: str, state) -> Order:
    scheduled_at = schedule_general_retry(event.occurred_at)
    body = {
        "entry_id": event.campaign.entry_id,
        "telefono": event.lead.phone,
        "no_antes_de": scheduled_at.isoformat(),
        "motivo": reason,
    }
    return _order(event, "programar_llamada", body)


def _cut_retry_order(event: Event, state) -> Order:
    scheduled_at = schedule_cut_retry(event.occurred_at)
    context = state["classification"].get("context_note")
    if not context:
        context = _transcript_context(event)

    body = {
        "entry_id": event.campaign.entry_id,
        "telefono": event.lead.phone,
        "no_antes_de": scheduled_at.isoformat(),
        "motivo": "la llamada se cortó durante la cualificación",
        "nota_contexto": context,
    }
    return _order(event, "programar_llamada", body)


def _callback_orders(event: Event, state) -> list[Order]:
    raw = state["classification"].get("callback_requested_at")
    requested = _parse_callback_time(raw, event.occurred_at)

    if requested is None:
        requested = schedule_general_retry(event.occurred_at)

    if _is_in_call_window(requested):
        return [_program_call_order(event, requested, "callback solicitado")]

    orders = [
        _program_call_order(
            event,
            _next_valid_window(requested),
            "callback solicitado fuera de la ventana de llamadas",
        ),
        _fallback_notice_order(event, requested),
    ]
    return orders


def _program_call_order(
    event: Event,
    scheduled_at: datetime,
    reason: str,
) -> Order:
    return _order(
        event,
        "programar_llamada",
        {
            "entry_id": event.campaign.entry_id,
            "telefono": event.lead.phone,
            "no_antes_de": scheduled_at.astimezone(get_timezone()).isoformat(),
            "motivo": reason,
            "nota_contexto": " ".join(
                message.message
                for message in event.transcript
                if message.role == "user"
            ),
        },
    )


def _documentation_orders(event: Event, state) -> list[Order]:
    lead_when = add_natural_hours(
        event.occurred_at,
        int(state_config(state, "recordatorios", "documentacion_lead_horas")),
    )
    commercial_when = add_business_days(
        event.occurred_at,
        int(state_config(state, "recordatorios", "seguimiento_comercial_dias_habiles")),
    )

    lead_order = _order(
        event,
        "programar_recordatorio",
        {
            "contact_id": event.lead.contact_id,
            "canal": "whatsapp_lead",
            "plantilla": "recordatorio_documentacion",
            "cuando": lead_when.isoformat(),
            "cancelar_si": "lead_responde",
        },
        suffix="lead",
    )

    commercial_order = _order(
        event,
        "programar_recordatorio",
        {
            "contact_id": event.lead.contact_id,
            "canal": "tarea_comercial",
            "tipo_tarea": "llamar_a_mano",
            "cuando": commercial_when.isoformat(),
            "cancelar_si": "lead_responde",
        },
        suffix="comercial",
    )

    state["store"].save_reminder(
        _reminder_id(lead_order.idempotency_key),
        event.lead.contact_id,
        "whatsapp_lead",
        event.occurred_at.isoformat(),
    )
    state["store"].save_reminder(
        _reminder_id(commercial_order.idempotency_key),
        event.lead.contact_id,
        "tarea_comercial",
        event.occurred_at.isoformat(),
    )

    return [lead_order, commercial_order]


def _visit_task_order(event: Event, state) -> Order:
    appointment = event.agent_outcome.appointment
    due = appointment_task_due(appointment.start_time)
    return _order(
        event,
        "crear_tarea",
        {
            "contact_id": event.lead.contact_id,
            "call_id": event.telephony.call_id if event.telephony else None,
            "tipo": "confirmar_visita_direccion",
            "titulo": "Confirmar dirección de la visita",
            "detalle": f"Confirmar la dirección exacta antes de la visita del {appointment.start_time.isoformat()}.",
            "vence_el": due.isoformat(),
            "asignada_a": "comercial_asignado",
        },
    )


def _verify_phone_task_order(event: Event, state) -> Order:
    return _task_order(
        event,
        "verificar_telefono",
        "Verificar teléfono",
        "La persona que contestó indicó que no es el lead.",
        state,
    )


def _documentation_email_task_order(event: Event, state) -> Order:
    return _task_order(
        event,
        "enviar_documentacion_email",
        "Enviar documentación por email",
        "El lead solicitó documentación y rechazó WhatsApp.",
        state,
    )


def _review_task_order(event: Event, reason: str) -> Order:
    return _task_order(
        event,
        "revisar_llamada",
        "Revisar llamada",
        reason,
        None,
    )


def _task_order(
    event: Event,
    task_type: str,
    title: str,
    detail: str,
    state,
) -> Order:
    config = load_campaign_config_from_state(state)
    days = int(config["tareas"]["vencimiento_por_defecto_dias"])
    due = default_task_due(event.occurred_at)

    return _order(
        event,
        "crear_tarea",
        {
            "contact_id": event.lead.contact_id,
            "call_id": event.telephony.call_id if event.telephony else None,
            "tipo": task_type,
            "titulo": title,
            "detalle": detail,
            "vence_el": due.isoformat(),
            "asignada_a": "comercial_asignado",
        },
        suffix=task_type,
    )


def _fallback_whatsapp_order(event: Event, state) -> Order:
    config = load_campaign_config_from_state(state)
    template = "primer_toque_respaldo"
    return _order(
        event,
        "enviar_plantilla_whatsapp",
        {
            "organization_id": config["campana"]["organization_id"],
            "telefono": event.lead.phone,
            "plantilla": template,
            "parametros": {},
            "idioma": event.lead.language or "es",
        },
    )


def _fallback_notice_order(event: Event, requested: datetime) -> Order:
    return _order(
        event,
        "enviar_plantilla_whatsapp",
        {
            "organization_id": event.organization_id,
            "telefono": event.lead.phone,
            "plantilla": "aviso_cambio_hora",
            "parametros": {"hora_solicitada": requested.isoformat()},
            "idioma": event.lead.language or "es",
        },
        suffix="aviso",
    )


def _dnc_order(event: Event, state) -> Order:
    state["store"].save_dnc(
        event.lead.contact_id,
        event.lead.phone,
        "todos",
        event.occurred_at.isoformat(),
    )
    return _order(
        event,
        "marcar_no_contactar",
        {
            "telefono": event.lead.phone,
            "contact_id": event.lead.contact_id,
            "canal": "todos",
            "motivo": state["classification"]["reason"],
            "origen": "call.ended",
        },
    )


def _plan_message_orders(event: Event, state) -> list[Order]:
    orders: list[Order] = []

    for reminder in state["store"].get_pending_reminders(event.lead.contact_id):
        reminder_id = reminder["reminder_id"]
        orders.append(
            _order(
                event,
                "cancelar_recordatorio",
                {
                    "reminder_id": reminder_id,
                    "motivo": "El lead respondió por WhatsApp.",
                },
                suffix=reminder_id,
            )
        )
        state["store"].cancel_reminder(reminder_id)

    return orders


def _transcript_context(event: Event) -> str:
    return " ".join(
        message.message
        for message in event.transcript
        if message.role == "user"
    )[:1000]


def _parse_callback_time(raw: str | None, reference: datetime) -> datetime | None:
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=get_timezone())

    return parsed.astimezone(get_timezone())


def _is_in_call_window(moment: datetime) -> bool:
    from .scheduling import is_call_window_open
    return is_call_window_open(moment)


def _next_valid_window(moment: datetime) -> datetime:
    from .scheduling import next_call_window
    return next_call_window(moment)


def _order(
    event: Event,
    operation: str,
    body: dict,
    suffix: str | None = None,
) -> Order:
    key = f"{event.idempotency_key}:{operation}"
    if suffix:
        key = f"{key}:{suffix}"

    return Order(
        order_id=_order_id(key),
        event_id=event.event_id,
        operation=operation,
        idempotency_key=key,
        body=body,
    )


def _order_id(key: str) -> str:
    return "ord_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _reminder_id(key: str) -> str:
    return "rem_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def state_config(state, *keys):
    config = load_campaign_config_from_state(state)
    for key in keys:
        config = config[key]
    return config


def load_campaign_config_from_state(state):
    from ..config.loader import load_campaign_config
    return load_campaign_config()
