from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config.loader import load_campaign_config


DAY_NAMES = {
    0: "lunes",
    1: "martes",
    2: "miércoles",
    3: "jueves",
    4: "viernes",
    5: "sábado",
    6: "domingo",
}


def get_timezone() -> ZoneInfo:
    config = load_campaign_config()
    timezone_name = config["campana"]["zona_horaria"]

    return ZoneInfo(timezone_name)


def is_call_window_open(moment: datetime) -> bool:
    config = load_campaign_config()
    schedule = config["ventana_llamadas"]

    local_moment = moment.astimezone(get_timezone())
    day_name = DAY_NAMES[local_moment.weekday()]
    window = schedule.get(day_name)

    if not window:
        return False

    start = _parse_time(window[0])
    end = _parse_time(window[1])

    current_time = local_moment.time()

    return start <= current_time <= end


def next_call_window(moment: datetime) -> datetime:
    config = load_campaign_config()
    schedule = config["ventana_llamadas"]

    local_moment = moment.astimezone(get_timezone())

    for day_offset in range(8):
        candidate_date = local_moment.date() + timedelta(days=day_offset)
        day_name = DAY_NAMES[candidate_date.weekday()]
        window = schedule.get(day_name)

        if not window:
            continue

        start = _parse_time(window[0])
        candidate = datetime.combine(
            candidate_date,
            start,
            tzinfo=get_timezone(),
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


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")

    return time(
        hour=int(hour),
        minute=int(minute),
    )

def get_general_separation_hours() -> int:
    config = load_campaign_config()

    return int(config["reintentos"]["separacion_minima_horas"])


def get_busy_retry_range() -> tuple[int, int]:
    config = load_campaign_config()

    retry_config = config["reintentos"]

    return (
        int(retry_config["ocupado_minutos_min"]),
        int(retry_config["ocupado_minutos_max"]),
    )


def schedule_busy_retry(reference: datetime) -> datetime:
    minimum_minutes, _ = get_busy_retry_range()

    return schedule_within_call_window(
        reference,
        timedelta(minutes=minimum_minutes),
    )


def schedule_general_retry(reference: datetime) -> datetime:
    return schedule_within_call_window(
        reference,
        timedelta(hours=get_general_separation_hours()),
    )