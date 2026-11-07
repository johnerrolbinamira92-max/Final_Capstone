from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MANILA = ZoneInfo("Asia/Manila")
PHONE_PATTERN = re.compile(r"^(?:\+63|0)9\d{9}$")
SLOT_TIMES = tuple(
    time(hour=hour, minute=minute)
    for hour in range(9, 17)
    for minute in (0, 30)
)


def normalize_phone(value: str) -> str:
    return re.sub(r"[\s-]", "", value.strip())


def valid_phone(value: str) -> bool:
    return bool(PHONE_PATTERN.fullmatch(normalize_phone(value)))


def validate_message(value: str) -> str | None:
    if len(value.strip()) < 10:
        return "Please write at least 10 characters."
    return None


def valid_schedule(value: datetime, now: datetime | None = None) -> bool:
    current = now or datetime.now(MANILA)
    localized = value.astimezone(MANILA)
    return (
        localized > current
        and localized <= current + timedelta(days=31)
        and localized.weekday() < 5
        and localized.time().replace(second=0, microsecond=0) in SLOT_TIMES
    )


def available_dates(today: date | None = None) -> tuple[date, date]:
    current = today or datetime.now(MANILA).date()
    return current, current + timedelta(days=30)


def combine_schedule(day: date, slot: time) -> datetime:
    return datetime.combine(day, slot, tzinfo=MANILA)


def format_slot(slot: time) -> str:
    return datetime.combine(date.today(), slot).strftime("%-I:%M %p")
