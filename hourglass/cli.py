import argparse
import sys
from datetime import date, datetime
from typing import Dict

from . import __version__
from .config import get_countdown_timer, get_deadline_timer, get_dob, load_config
from . import timecalc


MODES = ["day", "year", "life"]


def _headless_snapshot(config: Dict) -> str:
    now = datetime.now().astimezone()
    dob = date.today()
    dob_str = get_dob(config)
    if dob_str:
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = date.today()

    day = timecalc.day_info(now)
    year = timecalc.year_info(now)
    life = timecalc.life_info(dob, now)
    countdown_cfg = get_countdown_timer(config)
    deadline_cfg = get_deadline_timer(config)

    lines = [
        f"now: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"DAY  done: {day.progress * 100:5.1f}%  remaining: {day.remaining_str}",
        f"YEAR done: {year.progress * 100:5.1f}%  remaining: {year.remaining_str}",
        f"LIFE done: {life.progress * 100:5.1f}%  remaining: {life.remaining_str}",
    ]
    if countdown_cfg and countdown_cfg["duration_seconds"] > 0:
        duration = countdown_cfg["duration_seconds"]
        remaining = min(duration, countdown_cfg["remaining_seconds"])
        done = remaining == 0
        remaining_str = "DONE" if done else timecalc.format_hms_seconds(remaining)
        progress = 1.0 if done else (duration - remaining) / max(1, duration)
        lines.append(f"COUNTDOWN done: {progress * 100:5.1f}%  remaining: {remaining_str}")
    if deadline_cfg:
        target_time = _parse_iso_local(deadline_cfg["target_local_datetime_iso"])
        set_time = _parse_iso_local(deadline_cfg["set_local_datetime_iso"])
        if target_time and set_time:
            deadline = timecalc.deadline_info(set_time, target_time, now)
            done = deadline.progress >= 1.0
            remaining_str = "DONE" if done else deadline.remaining_str
            lines.append(f"DEADLINE done: {deadline.progress * 100:5.1f}%  remaining: {remaining_str}")
    return "\n".join(lines)


def _parse_iso_local(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def parse_args(argv=None):
    epilog = (
        "Controls (interactive): q quit, space pause/resume, h help/settings. "
        "Dashboard shows DAY, YEAR, LIFE columns simultaneously."
    )
    parser = argparse.ArgumentParser(
        prog="hourglass",
        description="Full-screen terminal day/year/life dashboard",
        epilog=epilog,
    )
    parser.add_argument("mode", nargs="?", default="day", choices=MODES)
    parser.add_argument("--headless", action="store_true", help="print a numbers-only snapshot and exit")
    parser.add_argument("--version", action="version", version=f"hourglass {__version__}")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    config = load_config()
    if args.headless:
        print(_headless_snapshot(config))
        return 0

    try:
        from .ui import run

        run(args.mode, config)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
