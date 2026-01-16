import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple


@dataclass
class TimeInfo:
    start: datetime
    end: datetime
    now: datetime
    progress: float
    remaining_str: str


def _local_tzinfo() -> datetime:
    return datetime.now().astimezone().tzinfo


def _midnight_local(d: date) -> datetime:
    tz = _local_tzinfo()
    return datetime.combine(d, time(0, 0, 0), tzinfo=tz)


def _format_hms(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_dhms(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"


def _clamp_day(year: int, month: int, day: int) -> int:
    last = calendar.monthrange(year, month)[1]
    return min(day, last)


def add_years(dt: datetime, years: int) -> datetime:
    year = dt.year + years
    day = _clamp_day(year, dt.month, dt.day)
    return dt.replace(year=year, day=day)


def add_months(dt: datetime, months: int) -> datetime:
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = _clamp_day(year, month, dt.day)
    return dt.replace(year=year, month=month, day=day)


def _diff_ymdhms(start: datetime, end: datetime) -> Tuple[int, int, int, int, int, int]:
    if end <= start:
        return 0, 0, 0, 0, 0, 0

    years = end.year - start.year
    candidate = add_years(start, years)
    if candidate > end:
        years -= 1
        candidate = add_years(start, years)

    months = end.month - candidate.month
    if months < 0:
        months += 12
    candidate = add_months(candidate, months)
    if candidate > end:
        months -= 1
        candidate = add_months(candidate, months)

    delta = end - candidate
    days = delta.days
    seconds = delta.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return years, months, days, hours, minutes, seconds


def _format_ymdhms(start: datetime, end: datetime) -> str:
    years, months, days, hours, minutes, seconds = _diff_ymdhms(start, end)
    return f"{years}y {months}m {days}d {hours:02d}:{minutes:02d}:{seconds:02d}"


def _progress(now: datetime, start: datetime, end: datetime) -> float:
    if now <= start:
        return 0.0
    if now >= end:
        return 1.0
    total = (end - start).total_seconds()
    if total <= 0:
        return 1.0
    return (now - start).total_seconds() / total


def day_info(now: Optional[datetime] = None) -> TimeInfo:
    if now is None:
        now = datetime.now().astimezone()
    today = now.date()
    start = _midnight_local(today)
    end = _midnight_local(today + timedelta(days=1))
    remaining = end - now
    return TimeInfo(start=start, end=end, now=now, progress=_progress(now, start, end), remaining_str=_format_hms(remaining))


def year_info(now: Optional[datetime] = None) -> TimeInfo:
    if now is None:
        now = datetime.now().astimezone()
    start = _midnight_local(date(now.year, 1, 1))
    end = _midnight_local(date(now.year + 1, 1, 1))
    remaining = end - now
    return TimeInfo(start=start, end=end, now=now, progress=_progress(now, start, end), remaining_str=_format_dhms(remaining))


def life_info(dob: date, now: Optional[datetime] = None, lifespan_years: int = 85) -> TimeInfo:
    if now is None:
        now = datetime.now().astimezone()
    start = _midnight_local(dob)
    end = add_years(start, lifespan_years)
    remaining = end - now
    return TimeInfo(start=start, end=end, now=now, progress=_progress(now, start, end), remaining_str=_format_ymdhms(now, end))
