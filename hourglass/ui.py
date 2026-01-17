import curses
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from . import timecalc
from .config import (
    clear_countdown_timer,
    clear_deadline_timer,
    get_config_path,
    get_countdown_timer,
    get_deadline_timer,
    get_dob,
    set_countdown_timer,
    set_deadline_timer,
    set_dob,
)
from .sand import SandColumn

MIN_INNER_WIDTH = 10
MAX_INNER_WIDTH = 25
COLUMN_GAP = 4
LABEL_LINES = 3
HEADER_LINES = 1
MIN_COLUMN_HEIGHT = 8
BOTTOM_PADDING = 1


@dataclass
class ColumnState:
    label: str
    mode: str
    sand: SandColumn
    progress: float = 0.0
    remaining: str = ""


@dataclass
class CountdownState:
    duration_seconds: int = 0
    remaining_seconds: int = 0
    is_running: bool = False
    configured: bool = False
    done_flash: bool = False


@dataclass
class DeadlineState:
    target_time: Optional[datetime] = None
    set_time: Optional[datetime] = None
    configured: bool = False
    done_flash: bool = False


class UIState:
    def __init__(self, config: Dict) -> None:
        self.config = config
        self.paused = False
        self.pane_open = False
        self.pane_view = "menu"
        self.pane_index = 0
        self.pane_error = ""
        self.input_digits = ""
        self.input_error = ""
        self.input_prev_view = "menu"
        self.last_keydebug = ""
        self.last_time_update = 0.0
        self.time_info: Optional[Dict[str, timecalc.TimeInfo]] = None
        self.last_countdown_tick = 0.0
        self.last_flash_toggle = 0.0
        self.flash_on = False
        self.countdown = CountdownState()
        self.deadline = DeadlineState()
        self.columns = [
            ColumnState("DAY", "day", SandColumn()),
            ColumnState("YEAR", "year", SandColumn()),
            ColumnState("LIFE", "life", SandColumn()),
        ]
        self.countdown_column = ColumnState("COUNTDOWN", "countdown", SandColumn())
        self.deadline_column = ColumnState("DEADLINE", "deadline", SandColumn())


def _prompt_dob(config: Dict) -> date:
    while True:
        raw = input("Enter date of birth (YYYY-MM-DD): ").strip()
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d").date()
            set_dob(config, parsed.isoformat())
            return parsed
        except ValueError:
            print("Invalid date format. Try again.")


def _ensure_dob(config: Dict) -> date:
    dob_str = get_dob(config)
    if dob_str:
        try:
            return datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            return _prompt_dob(config)
    return _prompt_dob(config)


def _local_tzinfo():
    return datetime.now().astimezone().tzinfo


def _parse_iso_local(text: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_local_tzinfo())
    return parsed


def _digits_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def _format_countdown_digits(digits: str) -> str:
    slots = ["_"] * 6
    for idx, ch in enumerate(digits[:6]):
        slots[idx] = ch
    return f"{slots[0]}{slots[1]}:{slots[2]}{slots[3]}:{slots[4]}{slots[5]}"


def _format_deadline_digits(digits: str) -> str:
    slots = ["_"] * 12
    for idx, ch in enumerate(digits[:12]):
        slots[idx] = ch
    return (
        f"{slots[0]}{slots[1]}{slots[2]}{slots[3]}-"
        f"{slots[4]}{slots[5]}-"
        f"{slots[6]}{slots[7]} "
        f"{slots[8]}{slots[9]}:"
        f"{slots[10]}{slots[11]}"
    )


def _parse_countdown_digits(digits: str) -> Optional[int]:
    if len(digits) != 6:
        return None
    hours = int(digits[0:2])
    minutes = int(digits[2:4])
    seconds = int(digits[4:6])
    if minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _parse_deadline_digits(digits: str) -> Optional[datetime]:
    if len(digits) != 12:
        return None
    year = int(digits[0:4])
    month = int(digits[4:6])
    day = int(digits[6:8])
    hour = int(digits[8:10])
    minute = int(digits[10:12])
    try:
        return datetime(year, month, day, hour, minute, tzinfo=_local_tzinfo())
    except ValueError:
        return None


def _keydebug_enabled() -> bool:
    return os.environ.get("HOURGLASS_KEYDEBUG") == "1"


def _keydebug_log(raw_repr: str, raw_type: str, keyname: str, decoded: str, seq: str) -> str:
    line = f"{datetime.now().isoformat()} raw={raw_repr} type={raw_type} keyname={keyname} decoded={decoded} seq={seq}"
    if not _keydebug_enabled():
        return line
    path = get_config_path().parent / "keydebug.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        lines.append(line)
        if len(lines) > 500:
            lines = lines[-500:]
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    return line


def _decode_modal_key(stdscr, key) -> Tuple[str, Optional[str], str]:
    seq = ""
    raw_repr = repr(key)
    raw_type = type(key).__name__
    keyname = ""
    decoded_kind = "ignore"
    decoded_value: Optional[str] = None

    try:
        if isinstance(key, int):
            keyname = curses.keyname(key).decode("ascii", "ignore")
    except curses.error:
        keyname = ""

    if isinstance(key, str):
        if len(key) > 1:
            digits = _digits_only(key)
            if digits:
                decoded_kind = "digit"
                decoded_value = digits
        elif key.isdigit():
            decoded_kind = "digit"
            decoded_value = key
        elif key in ("\n", "\r"):
            decoded_kind = "enter"
        elif key == "\x1b":
            seq = key
        elif key in ("\b", "\x7f"):
            decoded_kind = "backspace"
    elif isinstance(key, int):
        if key in (curses.KEY_ENTER, 10, 13):
            decoded_kind = "enter"
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            decoded_kind = "backspace"
        elif key == 27:
            seq = "\x1b"
        elif 0 <= key <= 255:
            ch = chr(key)
            if ch.isdigit():
                decoded_kind = "digit"
                decoded_value = ch
            elif ch in ("\n", "\r"):
                decoded_kind = "enter"
            elif ch == "\x1b":
                seq = "\x1b"

    if seq:
        extra = ""
        for _ in range(3):
            try:
                nxt = stdscr.get_wch()
            except curses.error:
                break
            if isinstance(nxt, int):
                if 0 <= nxt <= 255:
                    extra += chr(nxt)
                else:
                    extra += ""
            else:
                extra += nxt
        seq += extra
        if seq == "\x1b":
            decoded_kind = "esc"
        elif seq.startswith("\x1bO") and len(seq) >= 3:
            code = seq[2]
            keypad_map = {
                "p": "0",
                "q": "1",
                "r": "2",
                "s": "3",
                "t": "4",
                "u": "5",
                "v": "6",
                "w": "7",
                "x": "8",
                "y": "9",
                "M": "enter",
            }
            mapped = keypad_map.get(code)
            if mapped == "enter":
                decoded_kind = "enter"
            elif mapped is not None:
                decoded_kind = "digit"
                decoded_value = mapped
        elif seq.startswith("\x1b["):
            decoded_kind = "ignore"

    decoded = decoded_kind if decoded_value is None else f"{decoded_kind}:{decoded_value}"
    debug_line = _keydebug_log(raw_repr, raw_type, keyname, decoded, repr(seq))
    return decoded_kind, decoded_value, debug_line


def _get_deadline_info(deadline: DeadlineState, now: datetime) -> Optional[timecalc.TimeInfo]:
    if not deadline.configured or deadline.set_time is None or deadline.target_time is None:
        return None
    return timecalc.deadline_info(deadline.set_time, deadline.target_time, now)


def _get_all_time_info(now: datetime, dob: date, deadline: DeadlineState) -> Dict[str, timecalc.TimeInfo]:
    info = {
        "day": timecalc.day_info(now),
        "year": timecalc.year_info(now),
        "life": timecalc.life_info(dob, now),
    }
    deadline_info = _get_deadline_info(deadline, now)
    if deadline_info is not None:
        info["deadline"] = deadline_info
    return info


def _format_header(info: Dict[str, timecalc.TimeInfo]) -> str:
    now_str = info["day"].now.strftime("%Y-%m-%d %H:%M:%S")
    day_pct = info["day"].progress * 100
    year_pct = info["year"].progress * 100
    life_pct = info["life"].progress * 100
    return f"now: {now_str} | day {day_pct:5.1f}% | year {year_pct:5.1f}% | life {life_pct:5.1f}%"


def _pane_menu_items(state: UIState) -> List[str]:
    if state.pane_view == "menu":
        return [
            "Resume",
            "Set/Manage Countdown Timer",
            "Set/Manage Deadline Timer",
            "Controls",
            "Config path info",
        ]
    if state.pane_view == "controls":
        return ["Back"]
    if state.pane_view == "config":
        return ["Back"]
    if state.pane_view == "countdown":
        return [
            "Set duration (HH:MM:SS)",
            "Start/Pause",
            "Reset to original duration",
            "Clear timer",
            "Back",
        ]
    if state.pane_view == "deadline":
        return [
            "Set deadline (YYYY-MM-DD HH:MM)",
            "Clear timer",
            "Back",
        ]
    return ["Back"]


def _pane_body_lines(state: UIState, info: Dict[str, timecalc.TimeInfo]) -> List[str]:
    if state.pane_view == "controls":
        return [
            "Controls:",
            "q: quit",
            "space: pause/resume day/year/life/deadline",
            "h: open/close help/settings",
            "Arrow keys + Enter: select menu items",
            "Countdown has its own start/pause control.",
            "Life mode clamps Feb 29 to Feb 28 in non-leap years.",
        ]
    if state.pane_view == "config":
        return [f"Config: {get_config_path()}"]
    if state.pane_view == "countdown":
        countdown = state.countdown
        if countdown.configured:
            duration_str = timecalc.format_hms_seconds(countdown.duration_seconds)
            remaining_str = "DONE" if countdown.remaining_seconds == 0 else timecalc.format_hms_seconds(countdown.remaining_seconds)
            running_str = "yes" if countdown.is_running else "no"
            return [
                "Countdown Timer",
                f"Configured: yes",
                f"Duration: {duration_str}",
                f"Remaining: {remaining_str}",
                f"Running: {running_str}",
            ]
        return ["Countdown Timer", "Configured: no"]
    if state.pane_view == "deadline":
        deadline = state.deadline
        if deadline.configured and deadline.target_time and deadline.set_time:
            deadline_info = info.get("deadline")
            remaining = "DONE"
            if deadline_info is not None:
                remaining = "DONE" if deadline_info.progress >= 1.0 else deadline_info.remaining_str
            return [
                "Deadline Timer",
                "Configured: yes",
                f"Target: {deadline.target_time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Set at: {deadline.set_time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Remaining: {remaining}",
            ]
        return ["Deadline Timer", "Configured: no"]
    return [
        "Help / Settings",
        "Use arrow keys to select and Enter to activate.",
    ]


def _draw_input_modal(stdscr, rows: int, cols: int, state: UIState) -> None:
    if state.pane_view == "countdown_input":
        title = "ENTER DURATION (HH:MM:SS)"
        formatted = _format_countdown_digits(state.input_digits)
    else:
        title = "ENTER DEADLINE (YYYY-MM-DD HH:MM)"
        formatted = _format_deadline_digits(state.input_digits)

    caret = ">" if state.flash_on else " "
    hint = "Digits only. Backspace delete. Enter confirm. Esc cancel."
    lines = [title, "", f"{caret} {formatted}", "", hint]
    if state.input_error:
        lines.extend(["", f"Error: {state.input_error}"])
    if _keydebug_enabled() and state.last_keydebug:
        lines.extend(["", f"Key: {state.last_keydebug}"])

    width = min(cols - 2, max(len(line) for line in lines) + 4)
    height = len(lines) + 2
    start_y = max(0, (rows - height) // 2)
    start_x = max(0, (cols - width) // 2)

    for y in range(height):
        for x in range(width):
            ch = " "
            if y == 0 or y == height - 1:
                ch = "-"
            if x == 0 or x == width - 1:
                ch = "|"
            if (y == 0 or y == height - 1) and (x == 0 or x == width - 1):
                ch = "+"
            try:
                stdscr.addch(start_y + y, start_x + x, ch)
            except curses.error:
                pass

    for i, line in enumerate(lines):
        line = line[: max(0, width - 4)]
        line_x = start_x + 2
        if i == 2:
            line_x = start_x + max(2, (width - len(line)) // 2)
        try:
            stdscr.addstr(start_y + 1 + i, line_x, line)
        except curses.error:
            pass


def _draw_pane(stdscr, rows: int, cols: int, state: UIState, info: Dict[str, timecalc.TimeInfo]) -> None:
    if state.pane_view in ("countdown_input", "deadline_input"):
        _draw_input_modal(stdscr, rows, cols, state)
        return
    menu_items = _pane_menu_items(state)
    if state.pane_index >= len(menu_items):
        state.pane_index = max(0, len(menu_items) - 1)
    body_lines = _pane_body_lines(state, info)

    lines = []
    lines.extend(body_lines)
    if body_lines:
        lines.append("")
    for idx, item in enumerate(menu_items):
        prefix = ">" if idx == state.pane_index else " "
        lines.append(f"{prefix} {item}")
    if state.pane_error:
        lines.append("")
        lines.append(f"Error: {state.pane_error}")

    width = min(cols - 2, max(len(line) for line in lines) + 4)
    height = len(lines) + 2
    start_y = max(0, (rows - height) // 2)
    start_x = max(0, (cols - width) // 2)

    for y in range(height):
        for x in range(width):
            ch = " "
            if y == 0 or y == height - 1:
                ch = "-"
            if x == 0 or x == width - 1:
                ch = "|"
            if (y == 0 or y == height - 1) and (x == 0 or x == width - 1):
                ch = "+"
            try:
                stdscr.addch(start_y + y, start_x + x, ch)
            except curses.error:
                pass

    for i, line in enumerate(lines):
        line = line[: max(0, width - 4)]
        try:
            stdscr.addstr(start_y + 1 + i, start_x + 2, line)
        except curses.error:
            pass


def _numbers_only_view(
    canvas,
    info: Dict[str, timecalc.TimeInfo],
    cols: int,
    countdown: CountdownState,
    deadline: DeadlineState,
) -> None:
    header = _format_header(info)
    for i, ch in enumerate(header[:cols]):
        canvas[0][i] = ch

    lines = [
        f"DAY  done: {info['day'].progress * 100:5.1f}%  remaining: {info['day'].remaining_str}",
        f"YEAR done: {info['year'].progress * 100:5.1f}%  remaining: {info['year'].remaining_str}",
        f"LIFE done: {info['life'].progress * 100:5.1f}%  remaining: {info['life'].remaining_str}",
    ]
    if countdown.configured:
        done = countdown.remaining_seconds == 0
        remaining = "DONE" if done else timecalc.format_hms_seconds(countdown.remaining_seconds)
        done_mark = " (DONE)" if done else ""
        progress = 1.0 if done else (countdown.duration_seconds - countdown.remaining_seconds) / max(1, countdown.duration_seconds)
        lines.append(f"COUNTDOWN done: {progress * 100:5.1f}%  remaining: {remaining}{done_mark}")
    if deadline.configured and "deadline" in info:
        deadline_info = info["deadline"]
        done = deadline_info.progress >= 1.0
        remaining = "DONE" if done else deadline_info.remaining_str
        done_mark = " (DONE)" if done else ""
        lines.append(f"DEADLINE done: {deadline_info.progress * 100:5.1f}%  remaining: {remaining}{done_mark}")
    for idx, line in enumerate(lines):
        row = 1 + idx
        if row >= len(canvas):
            break
        for i, ch in enumerate(line[:cols]):
            canvas[row][i] = ch


def _draw_column_label(canvas, x: int, width: int, label_lines: list, start_row: int) -> None:
    for i, text in enumerate(label_lines):
        row = start_row + i
        if not (0 <= row < len(canvas)):
            continue
        text = text[:width]
        start_x = x + max(0, (width - len(text)) // 2)
        for j, ch in enumerate(text):
            xx = start_x + j
            if 0 <= xx < len(canvas[0]):
                canvas[row][xx] = ch


def _draw_column_border(canvas, x: int, y: int, width: int, height: int, flash: bool = False) -> None:
    top = y
    bottom = y + height - 1
    left = x
    right = x + width - 1
    horiz = "=" if flash else "-"
    vert = "!" if flash else "|"
    corner = "*" if flash else "+"

    for col in range(left + 1, right):
        if 0 <= top < len(canvas):
            canvas[top][col] = horiz
        if 0 <= bottom < len(canvas):
            canvas[bottom][col] = horiz
    if 0 <= top < len(canvas):
        canvas[top][left] = corner
        canvas[top][right] = corner
    if 0 <= bottom < len(canvas):
        canvas[bottom][left] = corner
        canvas[bottom][right] = corner

    for row in range(top + 1, bottom):
        if 0 <= row < len(canvas):
            if 0 <= left < len(canvas[0]):
                canvas[row][left] = vert
            if 0 <= right < len(canvas[0]):
                canvas[row][right] = vert


def _draw_fill(
    canvas,
    inner_left: int,
    inner_right: int,
    inner_top: int,
    inner_bottom: int,
    progress: float,
    flash: bool = False,
) -> int:
    inner_h = inner_bottom - inner_top + 1
    fill_rows = int(inner_h * progress)
    if fill_rows <= 0:
        return inner_bottom
    if fill_rows > inner_h:
        fill_rows = inner_h
    fill_top = inner_bottom - fill_rows + 1
    for row in range(inner_bottom, fill_top - 1, -1):
        depth = row - fill_top + 1
        if flash:
            ch = "*"
        elif depth <= 2:
            ch = "."
        elif depth <= 5:
            ch = "+"
        else:
            ch = "#"
        for col in range(inner_left, inner_right + 1):
            if 0 <= row < len(canvas) and 0 <= col < len(canvas[0]):
                canvas[row][col] = ch
    return fill_top


def _layout_columns(cols: int, count: int) -> Optional[Dict[str, int]]:
    min_col_width = MIN_INNER_WIDTH + 2
    min_total = min_col_width * count + COLUMN_GAP * (count - 1)
    if cols < min_total:
        return None

    available = cols - COLUMN_GAP * (count - 1) - 2 * count
    min_needed = MIN_INNER_WIDTH * count
    if available < min_needed:
        return None

    inner_widths = [MIN_INNER_WIDTH] * count
    extra = available - min_needed
    idx = 0
    while extra > 0:
        if inner_widths[idx] < MAX_INNER_WIDTH:
            inner_widths[idx] += 1
            extra -= 1
        idx = (idx + 1) % count
        if idx == 0 and all(width >= MAX_INNER_WIDTH for width in inner_widths):
            break

    col_widths = [w + 2 for w in inner_widths]
    positions = []
    x = 0
    for w in col_widths:
        positions.append((x, w))
        x += w + COLUMN_GAP

    return {
        "positions": positions,
        "inner_widths": inner_widths,
    }


def _visible_columns(state: UIState) -> List[ColumnState]:
    columns = list(state.columns)
    if state.countdown.configured:
        columns.append(state.countdown_column)
    if state.deadline.configured:
        columns.append(state.deadline_column)
    return columns


def _toggle_countdown_running(state: UIState, config: Dict) -> Optional[str]:
    if not state.countdown.configured:
        return "Countdown timer is not configured."
    if state.countdown.remaining_seconds == 0:
        return "Countdown is DONE. Reset to start again."
    state.countdown.is_running = not state.countdown.is_running
    state.last_countdown_tick = 0.0
    set_countdown_timer(
        config,
        state.countdown.duration_seconds,
        state.countdown.remaining_seconds,
        state.countdown.is_running,
    )
    return None


def _reset_countdown(state: UIState, config: Dict) -> Optional[str]:
    if not state.countdown.configured:
        return "Countdown timer is not configured."
    state.countdown.remaining_seconds = state.countdown.duration_seconds
    state.countdown.is_running = False
    state.countdown.done_flash = False
    state.last_countdown_tick = 0.0
    set_countdown_timer(
        config,
        state.countdown.duration_seconds,
        state.countdown.remaining_seconds,
        state.countdown.is_running,
    )
    return None


def _clear_countdown(state: UIState, config: Dict) -> None:
    state.countdown = CountdownState()
    state.countdown_column.sand.reset()
    state.last_countdown_tick = 0.0
    clear_countdown_timer(config)


def _set_deadline(state: UIState, config: Dict, target_time: datetime) -> None:
    now = datetime.now().astimezone()
    state.deadline.target_time = target_time
    state.deadline.set_time = now
    state.deadline.configured = True
    state.deadline.done_flash = False
    set_deadline_timer(config, target_time.isoformat(), now.isoformat())


def _clear_deadline(state: UIState, config: Dict) -> None:
    state.deadline = DeadlineState()
    state.deadline_column.sand.reset()
    state.time_info = None
    clear_deadline_timer(config)


def run(_mode: str, config: Dict) -> None:
    dob = _ensure_dob(config)

    stdscr = curses.initscr()
    sys.stdout.write("\x1b[?1049h")
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    stdscr.nodelay(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    state = UIState(config)
    countdown_cfg = get_countdown_timer(config)
    if countdown_cfg and countdown_cfg["duration_seconds"] > 0:
        duration = countdown_cfg["duration_seconds"]
        remaining = min(duration, countdown_cfg["remaining_seconds"])
        state.countdown.duration_seconds = duration
        state.countdown.remaining_seconds = remaining
        state.countdown.is_running = False
        state.countdown.configured = True
        if countdown_cfg["is_running"] or remaining != countdown_cfg["remaining_seconds"]:
            set_countdown_timer(config, duration, remaining, False)

    deadline_cfg = get_deadline_timer(config)
    if deadline_cfg:
        target_time = _parse_iso_local(deadline_cfg["target_local_datetime_iso"])
        set_time = _parse_iso_local(deadline_cfg["set_local_datetime_iso"])
        if target_time and set_time:
            state.deadline.target_time = target_time
            state.deadline.set_time = set_time
            state.deadline.configured = True
    last_time = time.time()
    frame_delay = 1.0 / 24.0

    try:
        while True:
            now = time.time()
            dt = now - last_time
            last_time = now

            if state.pane_open and state.pane_view in ("countdown_input", "deadline_input"):
                try:
                    ch = stdscr.get_wch()
                except curses.error:
                    ch = None
            else:
                ch = stdscr.getch()
                if ch == -1:
                    ch = None

            if ch is not None:
                if (isinstance(ch, str) and ch.lower() == "q") or (
                    isinstance(ch, int) and 0 <= ch <= 255 and chr(ch).lower() == "q"
                ):
                    break
                if state.pane_open:
                    if state.pane_view in ("countdown_input", "deadline_input"):
                        try:
                            kind, value, debug_line = _decode_modal_key(stdscr, ch)
                        except Exception:
                            kind, value, debug_line = "ignore", None, "decode_error"
                        state.last_keydebug = debug_line if _keydebug_enabled() else ""
                        max_len = 6 if state.pane_view == "countdown_input" else 12
                        if kind == "digit" and value:
                            digits = _digits_only(value)
                            if digits:
                                room = max_len - len(state.input_digits)
                                state.input_digits += digits[:room]
                        elif kind == "backspace":
                            state.input_digits = state.input_digits[:-1]
                        elif kind == "esc":
                            state.pane_view = state.input_prev_view
                            state.input_digits = ""
                            state.input_error = ""
                            state.last_keydebug = ""
                        elif kind == "enter":
                            if state.pane_view == "countdown_input":
                                seconds = _parse_countdown_digits(state.input_digits)
                                if seconds is None:
                                    state.input_error = "Enter 6 digits (HHMMSS)."
                                elif seconds < 1:
                                    state.input_error = "Duration must be at least 1 second."
                                else:
                                    state.countdown.duration_seconds = seconds
                                    state.countdown.remaining_seconds = seconds
                                    state.countdown.is_running = True
                                    state.countdown.configured = True
                                    state.countdown.done_flash = False
                                    state.last_countdown_tick = 0.0
                                    set_countdown_timer(config, seconds, seconds, True)
                                    state.pane_open = False
                                    state.pane_view = "menu"
                                    state.pane_index = 0
                                    state.input_digits = ""
                                    state.input_error = ""
                                    state.last_keydebug = ""
                            else:
                                target = _parse_deadline_digits(state.input_digits)
                                if target is None:
                                    state.input_error = "Enter 12 digits (YYYYMMDDHHMM)."
                                else:
                                    _set_deadline(state, config, target)
                                    state.time_info = None
                                    state.pane_view = state.input_prev_view
                                    state.pane_index = 0
                                    state.input_digits = ""
                                    state.input_error = ""
                                    state.last_keydebug = ""
                        else:
                            pass
                    else:
                        menu_items = _pane_menu_items(state)
                        if ch in (ord("h"), ord("H")):
                            state.pane_open = False
                            state.pane_error = ""
                        elif ch == curses.KEY_UP:
                            state.pane_index = (state.pane_index - 1) % len(menu_items)
                        elif ch == curses.KEY_DOWN:
                            state.pane_index = (state.pane_index + 1) % len(menu_items)
                        elif ch in (curses.KEY_ENTER, 10, 13):
                            selection = menu_items[state.pane_index]
                            state.pane_error = ""
                            if state.pane_view == "menu":
                                if selection == "Resume":
                                    state.pane_open = False
                                elif selection == "Set/Manage Countdown Timer":
                                    state.pane_view = "countdown"
                                    state.pane_index = 0
                                elif selection == "Set/Manage Deadline Timer":
                                    state.pane_view = "deadline"
                                    state.pane_index = 0
                                elif selection == "Controls":
                                    state.pane_view = "controls"
                                    state.pane_index = 0
                                elif selection == "Config path info":
                                    state.pane_view = "config"
                                    state.pane_index = 0
                            elif state.pane_view in ("controls", "config"):
                                if selection == "Back":
                                    state.pane_view = "menu"
                                    state.pane_index = 0
                            elif state.pane_view == "countdown":
                                if selection.startswith("Set duration"):
                                    state.input_prev_view = "countdown"
                                    state.pane_view = "countdown_input"
                                    state.input_digits = ""
                                    state.input_error = ""
                                    state.last_keydebug = ""
                                elif selection == "Start/Pause":
                                    error = _toggle_countdown_running(state, config)
                                    if error:
                                        state.pane_error = error
                                elif selection == "Reset to original duration":
                                    error = _reset_countdown(state, config)
                                    if error:
                                        state.pane_error = error
                                elif selection == "Clear timer":
                                    _clear_countdown(state, config)
                                elif selection == "Back":
                                    state.pane_view = "menu"
                                    state.pane_index = 0
                            elif state.pane_view == "deadline":
                                if selection.startswith("Set deadline"):
                                    state.input_prev_view = "deadline"
                                    state.pane_view = "deadline_input"
                                    state.input_digits = ""
                                    state.input_error = ""
                                    state.last_keydebug = ""
                                elif selection == "Clear timer":
                                    _clear_deadline(state, config)
                                elif selection == "Back":
                                    state.pane_view = "menu"
                                    state.pane_index = 0
                else:
                    if ch == ord(" "):
                        state.paused = not state.paused
                        if not state.paused:
                            state.last_time_update = 0.0
                    if ch in (ord("h"), ord("H")):
                        state.pane_open = True
                        state.pane_view = "menu"
                        state.pane_index = 0
                        state.pane_error = ""
                        state.input_digits = ""
                        state.input_error = ""
                        state.last_keydebug = ""

            if now - state.last_flash_toggle >= 0.5:
                state.flash_on = not state.flash_on
                state.last_flash_toggle = now

            if state.countdown.is_running and state.countdown.remaining_seconds > 0:
                if state.last_countdown_tick == 0.0:
                    state.last_countdown_tick = now
                if now - state.last_countdown_tick >= 1.0:
                    ticks = int(now - state.last_countdown_tick)
                    state.last_countdown_tick += ticks
                    remaining = max(0, state.countdown.remaining_seconds - ticks)
                    if remaining != state.countdown.remaining_seconds:
                        state.countdown.remaining_seconds = remaining
                        if remaining == 0:
                            state.countdown.is_running = False
                            state.countdown.done_flash = True
                        set_countdown_timer(
                            config,
                            state.countdown.duration_seconds,
                            state.countdown.remaining_seconds,
                            state.countdown.is_running,
                        )
            else:
                state.last_countdown_tick = 0.0
                if state.countdown.configured and state.countdown.remaining_seconds == 0:
                    state.countdown.done_flash = True

            rows, cols = stdscr.getmaxyx()
            canvas = [[" " for _ in range(cols)] for _ in range(rows)]

            if state.paused:
                if state.time_info is None:
                    state.time_info = _get_all_time_info(datetime.now().astimezone(), dob, state.deadline)
            else:
                if now - state.last_time_update >= 1.0 or state.time_info is None:
                    state.time_info = _get_all_time_info(datetime.now().astimezone(), dob, state.deadline)
                    state.last_time_update = now

            info = state.time_info
            if info is None:
                info = _get_all_time_info(datetime.now().astimezone(), dob, state.deadline)

            visible_columns = _visible_columns(state)
            min_rows = HEADER_LINES + LABEL_LINES + MIN_COLUMN_HEIGHT + BOTTOM_PADDING
            layout = _layout_columns(cols, len(visible_columns))
            if rows < min_rows or layout is None:
                _numbers_only_view(canvas, info, cols, state.countdown, state.deadline)
                for col_state in visible_columns:
                    col_state.sand.reset()
            else:
                header = _format_header(info)
                for i, ch in enumerate(header[:cols]):
                    canvas[0][i] = ch

                col_height = rows - HEADER_LINES - LABEL_LINES - BOTTOM_PADDING
                top_border = HEADER_LINES + LABEL_LINES

                for idx, col_state in enumerate(visible_columns):
                    flash = False
                    if col_state.mode in ("day", "year", "life"):
                        col_info = info[col_state.mode]
                        col_state.progress = col_info.progress
                        col_state.remaining = col_info.remaining_str
                    elif col_state.mode == "countdown":
                        remaining = state.countdown.remaining_seconds
                        duration = max(1, state.countdown.duration_seconds)
                        done = remaining == 0
                        col_state.progress = 1.0 if done else (duration - remaining) / duration
                        col_state.remaining = "DONE" if done else timecalc.format_hms_seconds(remaining)
                        flash = state.countdown.done_flash and state.flash_on
                    elif col_state.mode == "deadline":
                        deadline_info = info.get("deadline")
                        if deadline_info is None:
                            deadline_info = _get_deadline_info(state.deadline, datetime.now().astimezone())
                        if deadline_info is not None:
                            done = deadline_info.progress >= 1.0
                            col_state.progress = 1.0 if done else deadline_info.progress
                            col_state.remaining = "DONE" if done else deadline_info.remaining_str
                            if done:
                                state.deadline.done_flash = True
                            else:
                                state.deadline.done_flash = False
                            flash = state.deadline.done_flash and state.flash_on
                        else:
                            col_state.progress = 0.0
                            col_state.remaining = "--"

                    col_x, col_width = layout["positions"][idx]
                    inner_width = layout["inner_widths"][idx]
                    label_lines = [
                        col_state.label,
                        f"done: {col_state.progress * 100:5.1f}%",
                        f"remaining: {col_state.remaining}",
                    ]
                    _draw_column_label(canvas, col_x, col_width, label_lines, HEADER_LINES)
                    _draw_column_border(canvas, col_x, top_border, col_width, col_height, flash=flash)

                    inner_left = col_x + 1
                    inner_right = inner_left + inner_width - 1
                    inner_top = top_border + 1
                    inner_bottom = top_border + col_height - 2

                    surface_row = _draw_fill(
                        canvas,
                        inner_left,
                        inner_right,
                        inner_top,
                        inner_bottom,
                        col_state.progress,
                        flash=flash,
                    )

                    col_state.sand.update(
                        dt,
                        inner_left,
                        inner_right,
                        inner_top,
                        surface_row,
                        state.paused,
                    )
                    col_state.sand.render(canvas, grain_ch=".", sparkle_ch="*")

            stdscr.erase()
            for y in range(rows):
                try:
                    stdscr.addstr(y, 0, "".join(canvas[y]))
                except curses.error:
                    pass

            if state.pane_open:
                _draw_pane(stdscr, rows, cols, state, info)

            stdscr.refresh()
            time.sleep(frame_delay)
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
