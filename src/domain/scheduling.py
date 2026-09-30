from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config.loader import load_campaign_config


DAY_NAMES = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}


def get_timezone() -> ZoneInfo:
    config = load_campaign_config()
    return ZoneInfo(config["campana"]["zona_horaria"])


def is_call_window_open(moment: datetime) -> bool:
    config = load_campaign_config()
    schedule = config["ventana_llamadas"]
    local_moment = moment.astimezone(get_timezone())
    window = schedule.get(DAY_NAMES[local_moment.weekday()], [])

    if not window:
        return False

    start = _parse_time(window[0])
    end = _parse_time(window[1])

    return start <= local_moment.time() <= end


def next_call_window(moment: datetime) -> datetime:
    config = load_campaign_config()
    schedule = config["ventana_llamadas"]
    timezone = get_timezone()
    local_moment = moment.astimezone(timezone)

    for day_offset in range(8):
        candidate_date = local_moment.date() + timedelta(days=day_offset)
        window = schedule.get(DAY_NAMES[candidate_date.weekday()], [])

        if not window:
            continue

        candidate = datetime.combine(
            candidate_date,
            _parse_time(window[0]),
            tzinfo=timezone,
        )

        if candidate >= local_moment:
            return candidate

    raise RuntimeError("No call window found in campaign configuration.")


def schedule_within_call_window(
    reference: datetime,
    delay: timedelta,
) -> datetime:
    target = reference.astimezone(get_timezone()) + delay

    if is_call_window_open(target):
        return target

    return next_call_window(target)


def schedule_general_retry(reference: datetime) -> datetime:
    config = load_campaign_config()
    hours = int(config["reintentos"]["separacion_minima_horas"])
    return schedule_within_call_window(reference, timedelta(hours=hours))


def schedule_busy_retry(reference: datetime) -> datetime:
    config = load_campaign_config()
    minutes = int(config["reintentos"]["ocupado_minutos_min"])
    return schedule_within_call_window(reference, timedelta(minutes=minutes))


def schedule_cut_retry(reference: datetime) -> datetime:
    config = load_campaign_config()
    retry_config = config["reintentos"]
    minimum = timedelta(minutes=int(retry_config["cortada_minutos_min"]))
    maximum = timedelta(hours=int(retry_config["cortada_horas_max"]))

    earliest = reference.astimezone(get_timezone()) + minimum
    deadline = reference.astimezone(get_timezone()) + maximum

    if is_call_window_open(earliest):
        return earliest

    candidate = next_call_window(earliest)

    if candidate > deadline:
        raise ValueError("No valid call window exists within the cut-call deadline.")

    return candidate


def is_business_day(moment: datetime) -> bool:
    config = load_campaign_config()
    local_moment = moment.astimezone(get_timezone())
    return DAY_NAMES[local_moment.weekday()] in config["dias_habiles"]


def add_natural_hours(reference: datetime, hours: int) -> datetime:
    return reference.astimezone(get_timezone()) + timedelta(hours=hours)


def add_business_days(reference: datetime, days: int) -> datetime:
    config = load_campaign_config()
    timezone = get_timezone()
    current = reference.astimezone(timezone)

    remaining = days

    while remaining:
        current += timedelta(days=1)
        if DAY_NAMES[current.weekday()] in config["dias_habiles"]:
            remaining -= 1

    return current


def appointment_task_due(appointment_start: datetime) -> datetime:
    config = load_campaign_config()
    margin_hours = int(config["tareas"]["confirmar_visita_margen_horas"])
    return appointment_start.astimezone(get_timezone()) - timedelta(hours=margin_hours)


def default_task_due(reference: datetime) -> datetime:
    config = load_campaign_config()
    days = int(config["tareas"]["vencimiento_por_defecto_dias"])
    return reference.astimezone(get_timezone()) + timedelta(days=days)


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))
