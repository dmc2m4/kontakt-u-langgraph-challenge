from typing import Any

from .models import AMDResult, DecisionLabel, Event


def deterministic_classification(
    event: Event,
) -> dict[str, Any] | None:
    if event.telephony is None:
        return None

    transcript = " ".join(
        message.message.lower()
        for message in event.transcript
        if message.role == "user"
    )

    if _explicit_no_contact_request(transcript):
        return _classification(
            DecisionLabel.NO_CONTACTAR,
            "El lead pidió explícitamente no volver a ser contactado.",
            0.99,
        )

    if event.agent_outcome and event.agent_outcome.appointment:
        return _classification(
            DecisionLabel.VISITA_RESERVADA,
            "La llamada terminó con una cita creada en el CRM.",
            1.0,
        )

    sip_status_code = event.telephony.sip_status_code
    amd = event.telephony.amd

    if sip_status_code == 486:
        return _classification(
            DecisionLabel.OCUPADO,
            "486 Busy Here: la línea comunica.",
            0.99,
        )

    if sip_status_code == 603:
        return _classification(
            DecisionLabel.RECHAZADA,
            "603 Decline: la llamada fue rechazada activamente antes de descolgar.",
            0.99,
        )

    if sip_status_code in {408, 480} and not event.transcript:
        return _classification(
            DecisionLabel.SIN_RESPUESTA,
            f"{sip_status_code}: no hubo respuesta ni conversación.",
            0.99,
        )

    if amd:
        if amd.result in {
            AMDResult.MACHINE_VM,
            AMDResult.MACHINE_UNAVAILABLE,
        }:
            return _classification(
                DecisionLabel.BUZON,
                "La detección AMD indica buzón o máquina no disponible.",
                0.99,
            )

        if amd.result == AMDResult.MACHINE_IVR:
            return _classification(
                DecisionLabel.OTRO,
                "La detección AMD indica una máquina IVR, que no encaja en los casos soportados.",
                0.99,
            )

    if 500 <= sip_status_code <= 599:
        return _classification(
            DecisionLabel.OTRO,
            f"SIP {sip_status_code}: fallo de trunk sin un caso soportado.",
            0.99,
        )

    return None


def normalize_classification(
    event: Event,
    classification: dict[str, Any],
) -> dict[str, Any]:
    result = dict(classification)
    deterministic = deterministic_classification(event)

    if deterministic is not None:
        result.update(deterministic)

    return result


def determine_retry(
    label: DecisionLabel,
    attempt_number: int,
    max_attempts: int,
) -> str:
    if label in {
        DecisionLabel.OCUPADO,
        DecisionLabel.SIN_RESPUESTA,
        DecisionLabel.BUZON,
    }:
        return "retry" if attempt_number < max_attempts else "fallback"

    return "none"


def _classification(
    label: DecisionLabel,
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "label": label.value,
        "reason": reason,
        "confidence": confidence,
        "callback_requested_at": None,
        "context_note": None,
    }



def _explicit_no_contact_request(transcript: str) -> bool:
    phrases = (
        "no me llaméis más",
        "no me llamen más",
        "no me llames más",
        "no quiero que me llaméis",
        "no quiero que me llamen",
        "no quiero que me contactéis",
        "no quiero que me contacten",
        "no quiero que me contactes",
        "no me contactéis más",
        "no me contacten más",
        "no me contactes más",
        "darme de baja",
        "dadme de baja",
    )
    return any(phrase in transcript for phrase in phrases)
