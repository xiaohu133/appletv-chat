import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_DIR = Path(os.environ.get('DATA_DIR', '/app/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEVICES_FILE = DATA_DIR / 'devices.json'
HISTORY_FILE = DATA_DIR / 'history.json'
SETTINGS_FILE = DATA_DIR / 'settings.json'

def load_json(file_path: Path, default_val: Any) -> Any:
    if not file_path.exists():
        return default_val
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default_val

def save_json(file_path: Path, data: Any):
    try:
        tmp = file_path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(file_path)
    except Exception as e:
        print(f"Error saving {file_path}: {e}")

def get_devices() -> List[Dict[str, Any]]:
    devs = load_json(DEVICES_FILE, [])
    for d in devs:
        if "type" not in d:
            d["type"] = "appletv"
        name = d.get("name", "")
        if not name or "\ufffd" in name:
            d["name"] = "索尼电视" if d.get("type") == "androidtv" else "Apple TV"
    return devs

def save_devices(devices: List[Dict[str, Any]]):
    save_json(DEVICES_FILE, devices)

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    hist = load_json(HISTORY_FILE, [])
    return hist[-limit:]

def add_history(text: str, success: bool = True, device_name: str = "", enter: bool = False) -> Dict[str, Any]:
    hist = load_json(HISTORY_FILE, [])
    entry = {
        "id": int(time.time() * 1000),
        "text": text,
        "time": time.strftime("%H:%M:%S"),
        "date": time.strftime("%m-%d"),
        "success": success,
        "device_name": device_name,
        "enter": enter
    }
    hist.append(entry)
    if len(hist) > 200:
        hist = hist[-200:]
    save_json(HISTORY_FILE, hist)
    return entry

def clear_history():
    save_json(HISTORY_FILE, [])

def delete_history_item(item_id: int):
    hist = load_json(HISTORY_FILE, [])
    hist = [h for h in hist if h.get("id") != item_id]
    save_json(HISTORY_FILE, hist)

def get_settings() -> Dict[str, Any]:
    return load_json(SETTINGS_FILE, {
        "default_device_id": "",
        "auto_enter": False,
        "theme": "dark"
    })

def update_settings(settings: Dict[str, Any]):
    curr = get_settings()
    curr.update(settings)
    save_json(SETTINGS_FILE, curr)
    return curr
