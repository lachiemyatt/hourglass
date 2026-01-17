# hourglass

A full-screen terminal dashboard that shows DAY, YEAR, and LIFE progress side by side with live ASCII bars and a subtle sand stream.

## Requirements

- Python 3.11+
- A real terminal (Terminal.app, iTerm, Kitty, etc). Curses will not run in non-TTY runners.
- `pipx` is recommended for installing from GitHub.

## Install from GitHub

macOS:

```bash
brew install pipx
pipx ensurepath
# restart terminal
pipx install "git+https://github.com/lachiemyatt/hourglass.git"
hourglass
```

Linux:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
# restart shell
pipx install "git+https://github.com/lachiemyatt/hourglass.git"
hourglass
```

## Update / Uninstall

```bash
pipx uninstall hourglass
pipx install "git+https://github.com/lachiemyatt/hourglass.git"
```

## Controls

- q: quit
- h: open Help/Settings (interactive menu)
- arrows + Enter: navigate menu
- space: pause/resume day/year/life/deadline (countdown only starts from settings)

## Timers

- Countdown (duration): set in Help/Settings. Digits-only entry auto-formats `HH:MM:SS`. Confirming starts it immediately. It persists paused at the last remaining time across restarts.
- Deadline: set a target local datetime in Help/Settings. Digits-only entry auto-formats `YYYY-MM-DD HH:MM`. It continues correctly across restarts.
- DONE state: column flashes until reset/clear.

## Headless

- `hourglass --headless` prints a snapshot and exits (CI-friendly).

## Notes

- The dashboard always shows DAY, YEAR, and LIFE together.
- Life mode asks for a date of birth once and stores it in a config file.
- Feb 29 is clamped to Feb 28 when adding years in non-leap years.
- Optional COUNTDOWN and DEADLINE timers can be configured in the settings pane.
- Resize the terminal taller for the best visual effect.
- macOS Terminal keypad should work in modal entry. For key debug: `HOURGLASS_KEYDEBUG=1 hourglass` logs to `~/Library/Application Support/hourglass/keydebug.log`.
- Config location:
  - macOS: `~/Library/Application Support/hourglass/config.json`
  - Linux: `~/.config/hourglass/config.json`
  - Windows: `%APPDATA%\\hourglass\\config.json`
