import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel

from .storage import (
    get_devices, save_devices, get_history, add_history, 
    clear_history, delete_history_item, get_settings, update_settings
)
from .atv_manager import atv_mgr
from .android_manager import android_mgr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("appletv_chat")

app = FastAPI(title="TV Chat Input", description="Send clipboard & text to Apple TV and Android TV from mobile browser")

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "templates" / "index.html"

# Pydantic Schemas
class SendTextRequest(BaseModel):
    text: str
    device_id: Optional[str] = None
    auto_enter: Optional[bool] = None

class PairStartRequest(BaseModel):
    address: str
    name: Optional[str] = "Apple TV"

class PairFinishRequest(BaseModel):
    session_id: str
    pin: str

class AndroidConnectRequest(BaseModel):
    address: str
    port: Optional[int] = 5555
    name: Optional[str] = "安卓电视"

class SettingsRequest(BaseModel):
    default_device_id: Optional[str] = None
    auto_enter: Optional[bool] = None
    theme: Optional[str] = None

@app.get("/", response_class=FileResponse)
async def index():
    resp = FileResponse(str(HTML_FILE))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.get("/api/status")
async def get_status():
    devices = get_devices()
    settings = get_settings()
    return {
        "devices_count": len(devices),
        "devices": devices,
        "settings": settings
    }

@app.get("/api/devices")
async def list_devices():
    return get_devices()

@app.post("/api/scan")
async def scan_devices(address: Optional[str] = None):
    results = await atv_mgr.scan_devices(timeout=4, address=address)
    return {"ok": True, "results": results}

@app.post("/api/pair/start")
async def pair_start(req: PairStartRequest):
    res = await atv_mgr.start_pairing(req.address, req.name or "Apple TV")
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "发起配对失败"))
    return res

@app.post("/api/pair/finish")
async def pair_finish(req: PairFinishRequest):
    res = await atv_mgr.finish_pairing(req.session_id, req.pin)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "配对失败"))
    return res

@app.post("/api/android/connect")
async def connect_android_tv(req: AndroidConnectRequest):
    port = req.port or 5555
    res = await android_mgr.connect(req.address, port=port)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "连接失败"))
    
    target = res.get("target") or f"{req.address}:{port}"
    devices = get_devices()
    dev_id = f"adb_{target.replace(':', '_').replace('.', '_')}"
    
    existing = next((d for d in devices if d.get("id") == dev_id or d.get("address") == target), None)
    if existing:
        existing["name"] = req.name or existing.get("name", "安卓电视")
        existing["type"] = "androidtv"
        existing["status"] = res.get("status")
    else:
        devices.append({
            "id": dev_id,
            "name": req.name or "安卓电视",
            "type": "androidtv",
            "address": target,
            "port": port,
            "status": res.get("status")
        })
    save_devices(devices)
    return {
        "ok": True,
        "status": res.get("status"),
        "message": res.get("message"),
        "device": {
            "id": dev_id,
            "name": req.name or "安卓电视",
            "type": "androidtv",
            "address": target
        }
    }

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    devices = get_devices()
    new_devs = [d for d in devices if d.get("id") != device_id and d.get("identifier") != device_id]
    save_devices(new_devs)
    return {"ok": True, "message": "已移除该设备"}

def _get_target_device(device_id: Optional[str] = None):
    devices = get_devices()
    if not devices:
        return None
    if device_id:
        target = next((d for d in devices if d.get("id") == device_id or d.get("identifier") == device_id), None)
        if target:
            return target
    # Check default setting
    settings = get_settings()
    def_id = settings.get("default_device_id")
    if def_id:
        target = next((d for d in devices if d.get("id") == def_id or d.get("identifier") == def_id), None)
        if target:
            return target
    return devices[0]

@app.post("/api/send")
async def send_text(req: SendTextRequest):
    settings = get_settings()
    auto_enter = req.auto_enter if req.auto_enter is not None else settings.get("auto_enter", True)
    
    target_dev = _get_target_device(req.device_id)
    if not target_dev:
        return JSONResponse(status_code=400, content={"ok": False, "error": "尚未配对或连接任何电视设备"})

    dev_name = target_dev.get("name", "电视")
    dev_type = target_dev.get("type", "appletv")
    
    if dev_type == "androidtv":
        addr = target_dev.get("address")
        res = await android_mgr.send_text(addr, req.text, auto_enter=auto_enter)
    else:
        atv_id = target_dev.get("identifier") or target_dev.get("id")
        res = await atv_mgr.send_text(req.text, atv_id, auto_enter=auto_enter)
    
    # 记录到对话历史
    entry = add_history(
        text=req.text,
        success=bool(res.get("ok")),
        device_name=dev_name,
        enter=auto_enter
    )
    
    if not res.get("ok"):
        return JSONResponse(status_code=400, content={
            "ok": False,
            "error": res.get("error", "发送失败"),
            "entry": entry
        })
    
    return {
        "ok": True,
        "message": res.get("message", "发送成功"),
        "entry": entry
    }

@app.post("/api/clear")
async def clear_text(device_id: Optional[str] = None):
    target_dev = _get_target_device(device_id)
    if not target_dev:
        raise HTTPException(status_code=400, detail="未找到目标设备")

    if target_dev.get("type") == "androidtv":
        res = await android_mgr.clear_text(target_dev.get("address"))
    else:
        atv_id = target_dev.get("identifier") or target_dev.get("id")
        res = await atv_mgr.clear_text(atv_id)

    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "清空失败"))
    return res

@app.post("/api/remote/{action}")
async def remote_action(action: str, device_id: Optional[str] = None):
    target_dev = _get_target_device(device_id)
    if not target_dev:
        raise HTTPException(status_code=400, detail="未找到目标设备")

    if target_dev.get("type") == "androidtv":
        res = await android_mgr.send_remote_command(action, target_dev.get("address"))
    else:
        atv_id = target_dev.get("identifier") or target_dev.get("id")
        res = await atv_mgr.send_remote_command(action, atv_id)

    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "按键失败"))
    return res

@app.get("/api/history")
async def fetch_history():
    return get_history(limit=100)

@app.delete("/api/history/{item_id}")
async def delete_history(item_id: int):
    delete_history_item(item_id)
    return {"ok": True}

@app.delete("/api/history")
async def clear_all_history():
    clear_history()
    return {"ok": True}

@app.get("/api/settings")
async def fetch_settings():
    return get_settings()

@app.post("/api/settings")
async def save_app_settings(req: SettingsRequest):
    data = req.model_dump(exclude_unset=True)
    updated = update_settings(data)
    return {"ok": True, "settings": updated}
