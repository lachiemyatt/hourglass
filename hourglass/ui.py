import curses
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional

from . import timecalc
from .config import get_config_path, get_dob, set_dob
from .sand import SandColumn

MIN_INNER_WIDTH = 15
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


class UIState:
    def __init__(self, config: Dict) -> None:
        self.config = config
        self.paused = False
        self.help = False
        self.last_time_update = 0.0
        self.time_info: Optional[Dict[str, timecalc.TimeInfo]] = None
        self.columns = [
            ColumnState("DAY", "day", SandColumn()),
            ColumnState("YEAR", "year", SandColumn()),
            ColumnState("LIFE", "life", SandColumn()),
        ]


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


def _get_all_time_info(config: Dict, now: datetime, dob: date) -> Dict[str, timecalc.TimeInfo]:
    return {
        "day": timecalc.day_info(now),
        "year": timecalc.year_info(now),
        "life": timecalc.life_info(dob, now),
    }


def _format_header(info: Dict[str, timecalc.TimeInfo]) -> str:
    now_str = info["day"].now.strftime("%Y-%m-%d %H:%M:%S")
    day_pct = info["day"].progress * 100
    year_pct = info["year"].progress * 100
    life_pct = info["life"].progress * 100
    return f"now: {now_str} | day {day_pct:5.1f}% | year {year_pct:5.1f}% | life {life_pct:5.1f}%"


def _draw_help(stdscr, rows: int, cols: int) -> None:
    lines = [
        "Controls:",
        "q: quit",
        "space: pause/resume",
        "h: toggle help",
        "1/2/3: no-op",
        "",
        "Life mode uses DOB and clamps Feb 29 to Feb 28 in non-leap years.",
        "",
        f"Config: {get_config_path()}",
    ]
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


def _numbers_only_view(canvas, info: Dict[str, timecalc.TimeInfo], cols: int) -> None:
    header = _format_header(info)
    for i, ch in enumerate(header[:cols]):
        canvas[0][i] = ch

    lines = [
        f"DAY  done: {info['day'].progress * 100:5.1f}%  remaining: {info['day'].remaining_str}",
        f"YEAR done: {info['year'].progress * 100:5.1f}%  remaining: {info['year'].remaining_str}",
        f"LIFE done: {info['life'].progress * 100:5.1f}%  remaining: {info['life'].remaining_str}",
    ]
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


def _draw_column_border(canvas, x: int, y: int, width: int, height: int) -> None:
    top = y
    bottom = y + height - 1
    left = x
    right = x + width - 1

    for col in range(left + 1, right):
        if 0 <= top < len(canvas):
            canvas[top][col] = "-"
        if 0 <= bottom < len(canvas):
            canvas[bottom][col] = "-"
    if 0 <= top < len(canvas):
        canvas[top][left] = "+"
        canvas[top][right] = "+"
    if 0 <= bottom < len(canvas):
        canvas[bottom][left] = "+"
        canvas[bottom][right] = "+"

    for row in range(top + 1, bottom):
        if 0 <= row < len(canvas):
            if 0 <= left < len(canvas[0]):
                canvas[row][left] = "|"
            if 0 <= right < len(canvas[0]):
                canvas[row][right] = "|"


def _draw_fill(canvas, inner_left: int, inner_right: int, inner_top: int, inner_bottom: int, progress: float) -> int:
    inner_h = inner_bottom - inner_top + 1
    fill_rows = int(inner_h * progress)
    if fill_rows <= 0:
        return inner_bottom
    if fill_rows > inner_h:
        fill_rows = inner_h
    fill_top = inner_bottom - fill_rows + 1
    for row in range(inner_bottom, fill_top - 1, -1):
        depth = row - fill_top + 1
        if depth <= 2:
            ch = "."
        elif depth <= 5:
            ch = "+"
        else:
            ch = "#"
        for col in range(inner_left, inner_right + 1):
            if 0 <= row < len(canvas) and 0 <= col < len(canvas[0]):
                canvas[row][col] = ch
    return fill_top


def _layout_columns(cols: int) -> Optional[Dict[str, int]]:
    min_col_width = MIN_INNER_WIDTH + 2
    min_total = min_col_width * 3 + COLUMN_GAP * 2
    if cols < min_total:
        return None

    available = cols - COLUMN_GAP * 2 - 2 * 3
    inner_base = available // 3
    if inner_base < MIN_INNER_WIDTH:
        return None

    extras = available - inner_base * 3
    inner_widths = [inner_base] * 3
    for i in range(extras):
        inner_widths[i % 3] += 1

    col_widths = [w + 2 for w in inner_widths]
    group_width = sum(col_widths) + COLUMN_GAP * 2
    start_x = max(0, (cols - group_width) // 2)

    positions = []
    x = start_x
    for w in col_widths:
        positions.append((x, w))
        x += w + COLUMN_GAP

    return {
        "positions": positions,
        "inner_widths": inner_widths,
    }


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
    last_time = time.time()
    frame_delay = 1.0 / 24.0

    try:
        while True:
            now = time.time()
            dt = now - last_time
            last_time = now

            ch = stdscr.getch()
            if ch != -1:
                if ch in (ord("q"), ord("Q")):
                    break
                if ch == ord(" "):
                    state.paused = not state.paused
                    if not state.paused:
                        state.last_time_update = 0.0
                if ch in (ord("h"), ord("H")):
                    state.help = not state.help

            rows, cols = stdscr.getmaxyx()
            canvas = [[" " for _ in range(cols)] for _ in range(rows)]

            if state.paused:
                if state.time_info is None:
                    state.time_info = _get_all_time_info(config, datetime.now().astimezone(), dob)
            else:
                if now - state.last_time_update >= 1.0 or state.time_info is None:
                    state.time_info = _get_all_time_info(config, datetime.now().astimezone(), dob)
                    state.last_time_update = now

            info = state.time_info
            if info is None:
                info = _get_all_time_info(config, datetime.now().astimezone(), dob)

            min_rows = HEADER_LINES + LABEL_LINES + MIN_COLUMN_HEIGHT + BOTTOM_PADDING
            layout = _layout_columns(cols)
            if rows < min_rows or layout is None:
                _numbers_only_view(canvas, info, cols)
                for col_state in state.columns:
                    col_state.sand.reset()
            else:
                header = _format_header(info)
                for i, ch in enumerate(header[:cols]):
                    canvas[0][i] = ch

                col_height = rows - HEADER_LINES - LABEL_LINES - BOTTOM_PADDING
                top_border = HEADER_LINES + LABEL_LINES

                for idx, col_state in enumerate(state.columns):
                    col_info = info[col_state.mode]
                    col_state.progress = col_info.progress
                    col_state.remaining = col_info.remaining_str

                    col_x, col_width = layout["positions"][idx]
                    inner_width = layout["inner_widths"][idx]
                    label_lines = [
                        col_state.label,
                        f"done: {col_state.progress * 100:5.1f}%",
                        f"remaining: {col_state.remaining}",
                    ]
                    _draw_column_label(canvas, col_x, col_width, label_lines, HEADER_LINES)
                    _draw_column_border(canvas, col_x, top_border, col_width, col_height)

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

            if state.help:
                _draw_help(stdscr, rows, cols)

            stdscr.refresh()
            time.sleep(frame_delay)
    finally:
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
