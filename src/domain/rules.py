from typing import Any

from .models import AMDResult, DecisionLabel, Event


def normalize_classification(
    event: Event,
    classification: dict[str, Any],
) -> dict[str, Any]:
    result = dict(classification)

    if event.type.value != "call.ended":
        return result

    telephony = event.telephony

    if telephony is None:
        return result

    sip_status_code = telephony.sip_status_code
    amd = telephony.amd

    if sip_status_code == 486:
        return _with_label(result, DecisionLabel.OCUPADO)

    if sip_status_code == 603:
        return _with_label(result, DecisionLabel.RECHAZADA)

    if sip_status_code in {408, 480} and not event.transcript:
        return _with_label(result, DecisionLabel.SIN_RESPUESTA)

    if amd is not None:
        if amd.result in {
            AMDResult.MACHINE_VM,
            AMDResult.MACHINE_UNAVAILABLE,
        }:
            return _with_label(result, DecisionLabel.BUZON)

        if amd.result == AMDResult.MACHINE_IVR:
            return _with_label(result, DecisionLabel.OTRO)

    if 500 <= sip_status_code <= 599:
        return _with_label(result, DecisionLabel.OTRO)

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
        if attempt_number < max_attempts:
            return "retry"

        return "fallback"

    return "none"


def _with_label(
    classification: dict[str, Any],
    label: DecisionLabel,
) -> dict[str, Any]:
    result = dict(classification)
    result["label"] = label.value

    return result