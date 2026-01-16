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
