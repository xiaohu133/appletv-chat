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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("appletv_chat")

app = FastAPI(title="AppleTV Chat Input", description="Send clipboard & text to Apple TV from Android browser")

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

class SettingsRequest(BaseModel):
    default_device_id: Optional[str] = None
    auto_enter: Optional[bool] = None
    theme: Optional[str] = None

@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse(str(HTML_FILE))

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

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    devices = get_devices()
    new_devs = [d for d in devices if d.get("id") != device_id and d.get("identifier") != device_id]
    save_devices(new_devs)
    return {"ok": True, "message": "已移除该设备"}

@app.post("/api/send")
async def send_text(req: SendTextRequest):
    settings = get_settings()
    auto_enter = req.auto_enter if req.auto_enter is not None else settings.get("auto_enter", True)
    
    # 查找目标设备名称
    devices = get_devices()
    dev_name = "Apple TV"
    if req.device_id:
        for d in devices:
            if d.get("id") == req.device_id or d.get("identifier") == req.device_id:
                dev_name = d.get("name", "Apple TV")
                break
    elif devices:
        dev_name = devices[0].get("name", "Apple TV")

    res = await atv_mgr.send_text(req.text, req.device_id, auto_enter=auto_enter)
    
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
    res = await atv_mgr.clear_text(device_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "清空失败"))
    return res

@app.post("/api/remote/{action}")
async def remote_action(action: str, device_id: Optional[str] = None):
    res = await atv_mgr.send_remote_command(action, device_id)
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
