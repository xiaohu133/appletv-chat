import asyncio
import logging
import socket
import uuid
from typing import List, Dict, Any, Optional
import pyatv
from pyatv import scan, connect, pair
from pyatv.const import Protocol
from pyatv.conf import AppleTV, ManualService
from .storage import get_devices, save_devices, get_settings

logger = logging.getLogger("appletv_chat.atv")

def find_open_ports(host: str, timeout: float = 0.2) -> List[int]:
    """快速探测主机上可能作为 Apple TV 服务的开放 TCP 端口"""
    candidate_ports = [
        49947, 49152, 49153, 49154, 49155, 49156, 29798, 7000, 5000, 3689
    ]
    open_ports = []
    for port in candidate_ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            if s.connect_ex((host, port)) == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            s.close()
    
    if not open_ports:
        for port in range(49152, 49200):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.05)
            try:
                if s.connect_ex((host, port)) == 0:
                    open_ports.append(port)
            except Exception:
                pass
            finally:
                s.close()
    return open_ports

class AppleTVManager:
    def __init__(self):
        self.active_sessions: Dict[str, Any] = {}
        self.connected_atvs: Dict[str, Any] = {}
        self.lock = asyncio.Lock()

    async def scan_devices(self, timeout: int = 3, address: Optional[str] = None) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        results = []
        try:
            if address and address.strip():
                atvs = await scan(loop, timeout=timeout, hosts=[address.strip()])
            else:
                atvs = await scan(loop, timeout=timeout)
            
            paired_devs = {d.get("identifier"): d for d in get_devices() if d.get("identifier")}
            
            for atv in atvs:
                ident = atv.identifier or str(atv.address)
                paired_info = paired_devs.get(ident)
                results.append({
                    "identifier": ident,
                    "name": atv.name or "Apple TV",
                    "address": str(atv.address),
                    "model": atv.device_info.model_str if atv.device_info else "Apple TV",
                    "is_paired": bool(paired_info and paired_info.get("credentials")),
                    "services": [s.protocol.name for s in atv.services]
                })
        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
        return results

    async def start_pairing(self, address: str, name: str = "Apple TV") -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        clean_addr = address.strip()

        try:
            atvs = await scan(loop, timeout=2, hosts=[clean_addr])
            if atvs:
                conf = atvs[0]
                pairing_handler = await pair(conf, Protocol.Companion, loop)
                await pairing_handler.begin()
                
                session_id = str(uuid.uuid4())
                self.active_sessions[session_id] = {
                    "conf": conf,
                    "handler": pairing_handler,
                    "address": clean_addr,
                    "name": name or conf.name or "Apple TV",
                    "identifier": conf.identifier or clean_addr,
                    "port": None
                }
                return {
                    "ok": True,
                    "session_id": session_id,
                    "message": "请在电视屏幕上查看 4 位 PIN 码并在下方输入",
                    "name": conf.name or name
                }
        except Exception as e:
            logger.info(f"mDNS scan pairing failed, falling back to direct port probe: {e}")

        open_ports = find_open_ports(clean_addr)
        if not open_ports:
            return {"ok": False, "error": f"未在 {clean_addr} 检测到开放的 Apple TV 服务端口，请确认电视已开机且 IP 正确"}

        for port in open_ports:
            try:
                conf = AppleTV(clean_addr, name or "Apple TV")
                service = ManualService(f"companion_{port}", Protocol.Companion, port, {})
                conf.add_service(service)
                
                pairing_handler = await pair(conf, Protocol.Companion, loop)
                await asyncio.wait_for(pairing_handler.begin(), timeout=4)
                
                session_id = str(uuid.uuid4())
                self.active_sessions[session_id] = {
                    "conf": conf,
                    "handler": pairing_handler,
                    "address": clean_addr,
                    "name": name,
                    "identifier": f"atv_{clean_addr.replace('.', '_')}",
                    "port": port
                }
                return {
                    "ok": True,
                    "session_id": session_id,
                    "message": "电视屏幕已显示 4 位 PIN 码，请在下方输入",
                    "name": name
                }
            except Exception as e:
                logger.warning(f"Port {port} companion pair attempt failed: {e}")
                continue

        return {"ok": False, "error": f"已连上 {clean_addr} 但未能触发 PIN 码，请确认 Apple TV 设置中已允许「隔空播放与遥控器」"}

    async def finish_pairing(self, session_id: str, pin: Any) -> Dict[str, Any]:
        session = self.active_sessions.get(session_id)
        if not session:
            return {"ok": False, "error": "配对会话已超时或失效，请重新点击配对"}
        
        handler = session["handler"]
        port = session.get("port")
        try:
            pin_int = int(str(pin).strip())
            handler.pin(pin_int)
            await handler.finish()
            
            credentials = handler.service.credentials
            if not credentials:
                return {"ok": False, "error": "未获取到有效配对凭据，请确认输入的 4 位 PIN 码正确"}
            
            devices = get_devices()
            ident = session["identifier"]
            devices = [d for d in devices if d.get("identifier") != ident and d.get("address") != session["address"]]
            
            new_dev = {
                "id": ident,
                "identifier": ident,
                "name": session["name"],
                "address": session["address"],
                "protocol": "Companion",
                "port": port,
                "credentials": credentials
            }
            devices.append(new_dev)
            save_devices(devices)
            
            from .storage import update_settings
            update_settings({"default_device_id": ident})
            self.active_sessions.pop(session_id, None)
            
            return {
                "ok": True,
                "message": f"🎉 成功配对 {session['name']}！",
                "device": new_dev
            }
        except Exception as e:
            logger.error(f"Pairing finish error: {e}", exc_info=True)
            return {"ok": False, "error": f"配对校验失败: {str(e)}"}

    async def _get_connected_atv(self, device_id: Optional[str] = None):
        devices = get_devices()
        if not devices:
            raise ValueError("尚未配对任何 Apple TV，请先在右上角进行配对")
        
        target = None
        if device_id:
            for d in devices:
                if d.get("id") == device_id or d.get("identifier") == device_id or d.get("address") == device_id:
                    target = d
                    break
        
        if not target:
            settings = get_settings()
            def_id = settings.get("default_device_id")
            if def_id:
                for d in devices:
                    if d.get("id") == def_id or d.get("identifier") == def_id:
                        target = d
                        break
            if not target:
                target = devices[0]

        ident = target.get("identifier") or target.get("address")
        
        async with self.lock:
            existing = self.connected_atvs.get(ident)
            if existing:
                try:
                    if existing.device_info or existing.remote_control:
                        return existing
                except Exception:
                    self.connected_atvs.pop(ident, None)

            loop = asyncio.get_running_loop()
            addr = target.get("address")
            creds = target.get("credentials")
            saved_port = target.get("port")

            # 1. 尝试 mDNS 重连
            try:
                atvs = await scan(loop, timeout=2, hosts=[addr] if addr else None, identifier=target.get("identifier"))
                if atvs:
                    conf = atvs[0]
                    conf.set_credentials(Protocol.Companion, creds)
                    atv = await connect(conf, loop)
                    self.connected_atvs[ident] = atv
                    return atv
            except Exception as e:
                logger.info(f"mDNS connect failed, trying direct manual connect: {e}")

            # 2. 直连端口
            ports_to_try = []
            if saved_port:
                ports_to_try.append(saved_port)
            open_ports = find_open_ports(addr)
            for p in open_ports:
                if p not in ports_to_try:
                    ports_to_try.append(p)

            for port in ports_to_try:
                try:
                    conf = AppleTV(addr, target.get("name", "Apple TV"))
                    service = ManualService(f"companion_{port}", Protocol.Companion, port, {})
                    conf.add_service(service)
                    conf.set_credentials(Protocol.Companion, creds)
                    
                    atv = await asyncio.wait_for(connect(conf, loop), timeout=4)
                    self.connected_atvs[ident] = atv
                    if port != saved_port:
                        target["port"] = port
                        save_devices(devices)
                    return atv
                except Exception as e:
                    logger.warning(f"Connect port {port} failed: {e}")
                    continue

            raise ValueError(f"无法建立与 Apple TV ({target.get('name', '')} - {addr}) 的连接，请确认电视已开机并在局域网内")

    async def send_text(self, text: str, device_id: Optional[str] = None, auto_enter: bool = False) -> Dict[str, Any]:
        """向 Apple TV 当前活动的输入框精准写入文本（纯净注入，绝不误触键盘字符）"""
        if not text:
            return {"ok": False, "error": "文本内容不能为空"}
        
        try:
            atv = await self._get_connected_atv(device_id)
            
            if hasattr(atv, "keyboard") and atv.keyboard:
                # 纯净文本直写，替换当前输入框内容
                await atv.keyboard.text_set(text)
            else:
                raise RuntimeError("当前 Apple TV 未处于键盘可输入状态，请先在电视上点击输入框")

            return {"ok": True, "message": "已成功注入文本到 Apple TV"}
        except Exception as e:
            logger.error(f"Send text error: {e}", exc_info=True)
            if device_id in self.connected_atvs:
                self.connected_atvs.pop(device_id, None)
            return {"ok": False, "error": f"发送失败: {str(e)}"}

    async def clear_text(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """清空当前输入框内容"""
        try:
            atv = await self._get_connected_atv(device_id)
            if hasattr(atv, "keyboard") and atv.keyboard:
                await atv.keyboard.text_clear()
                return {"ok": True, "message": "已清空输入框"}
            else:
                return {"ok": False, "error": "当前未处于键盘输入状态"}
        except Exception as e:
            return {"ok": False, "error": f"清空失败: {str(e)}"}

    async def send_remote_command(self, action: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """发送常用遥控按键"""
        try:
            atv = await self._get_connected_atv(device_id)
            rc = atv.remote_control
            
            actions_map = {
                "up": rc.up,
                "down": rc.down,
                "left": rc.left,
                "right": rc.right,
                "select": rc.select,
                "menu": rc.menu,
                "back": rc.menu,
                "home": rc.home,
                "top_menu": rc.top_menu,
                "play_pause": rc.play_pause,
                "volume_up": rc.volume_up,
                "volume_down": rc.volume_down
            }
            
            if action == "backspace":
                if hasattr(atv, "keyboard") and atv.keyboard:
                    try:
                        curr = await atv.keyboard.text_get() or ""
                        if curr:
                            await atv.keyboard.text_set(curr[:-1])
                        else:
                            await rc.menu()
                    except Exception:
                        await rc.menu()
                else:
                    await rc.menu()
                return {"ok": True, "action": action}

            func = actions_map.get(action.lower())
            if not func:
                return {"ok": False, "error": f"未知遥控按键: {action}"}
            
            await func()
            return {"ok": True, "action": action}
        except Exception as e:
            logger.error(f"Remote command error: {e}", exc_info=True)
            return {"ok": False, "error": f"按键发送失败: {str(e)}"}

atv_mgr = AppleTVManager()
