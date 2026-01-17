import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, Optional


def get_config_path() -> Path:
    system = platform.system().lower()
    if system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata)
        else:
            base = Path.home() / "AppData" / "Roaming"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hourglass" / "config.json"


def load_config() -> Dict[str, Any]:
    path = get_config_path()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return {}


def save_config(data: Dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def get_dob(config: Dict[str, Any]) -> Optional[str]:
    dob = config.get("dob")
    if isinstance(dob, str) and len(dob) == 10:
        return dob
    return None


def set_dob(config: Dict[str, Any], dob: str) -> None:
    config["dob"] = dob
    save_config(config)


def get_countdown_timer(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = config.get("countdown_timer")
    if not isinstance(raw, dict):
        return None
    duration = raw.get("duration_seconds")
    remaining = raw.get("remaining_seconds")
    is_running = raw.get("is_running")
    if not isinstance(duration, int):
        return None
    if not isinstance(remaining, int):
        return None
    if not isinstance(is_running, bool):
        return None
    return {
        "duration_seconds": max(0, duration),
        "remaining_seconds": max(0, remaining),
        "is_running": is_running,
    }


def set_countdown_timer(config: Dict[str, Any], duration_seconds: int, remaining_seconds: int, is_running: bool) -> None:
    config["countdown_timer"] = {
        "duration_seconds": max(0, int(duration_seconds)),
        "remaining_seconds": max(0, int(remaining_seconds)),
        "is_running": bool(is_running),
    }
    save_config(config)


def clear_countdown_timer(config: Dict[str, Any]) -> None:
    if "countdown_timer" in config:
        config.pop("countdown_timer")
        save_config(config)


def get_deadline_timer(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = config.get("deadline_timer")
    if not isinstance(raw, dict):
        return None
    target = raw.get("target_local_datetime_iso")
    set_time = raw.get("set_local_datetime_iso")
    if not isinstance(target, str):
        return None
    if not isinstance(set_time, str):
        return None
    return {
        "target_local_datetime_iso": target,
        "set_local_datetime_iso": set_time,
    }


def set_deadline_timer(config: Dict[str, Any], target_local_datetime_iso: str, set_local_datetime_iso: str) -> None:
    config["deadline_timer"] = {
        "target_local_datetime_iso": target_local_datetime_iso,
        "set_local_datetime_iso": set_local_datetime_iso,
    }
    save_config(config)


def clear_deadline_timer(config: Dict[str, Any]) -> None:
    if "deadline_timer" in config:
        config.pop("deadline_timer")
        save_config(config)
