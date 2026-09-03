import asyncio
import logging
import os
import shlex
import subprocess
from typing import Dict, Any, Optional, List

logger = logging.getLogger("appletv_chat.android")

class AndroidTVManager:
    def __init__(self):
        self.lock = asyncio.Lock()
        data_dir = os.environ.get("DATA_DIR", "/app/data")
        self.adb_home = os.path.join(data_dir, ".android")
        os.makedirs(self.adb_home, exist_ok=True)
        os.environ["HOME"] = data_dir
        os.environ["ADB_VENDOR_KEYS"] = self.adb_home

    async def _run_adb(self, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        cmd = ["adb"] + list(args)
        env = os.environ.copy()
        env["HOME"] = os.environ.get("DATA_DIR", "/app/data")
        env["ADB_VENDOR_KEYS"] = self.adb_home

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout.decode("utf-8", errors="ignore").strip(), stderr.decode("utf-8", errors="ignore").strip()
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return -1, "", "ADB 命令执行超时"
        except FileNotFoundError:
            return -1, "", "系统未安装 adb 命令"
        except Exception as e:
            return -1, "", str(e)

    def _format_target(self, address: str, port: int = 5555) -> str:
        addr = address.strip()
        if ":" in addr and not addr.startswith("["):
            return addr
        return f"{addr}:{port}"

    async def connect(self, address: str, port: int = 5555) -> Dict[str, Any]:
        target = self._format_target(address, port)
        logger.info(f"正在尝试连接安卓电视 ADB: {target}")

        code, out, err = await self._run_adb("connect", target, timeout=6.0)
        full_res = f"{out} {err}".strip()
        logger.info(f"ADB connect {target} 返回: {full_res}")

        if "connected to" in full_res.lower():
            state = await self.get_device_state(target)
            if state == "unauthorized":
                return {
                    "ok": True,
                    "target": target,
                    "status": "unauthorized",
                    "message": "已连接到电视，电视屏幕正在提示授权确认！请用遥控器点击【允许这台计算机调试】。"
                }
            return {
                "ok": True,
                "target": target,
                "status": "connected",
                "message": "连接成功！"
            }
        elif "failed to authenticate" in full_res.lower() or "unauthorized" in full_res.lower():
            return {
                "ok": True,
                "target": target,
                "status": "unauthorized",
                "message": "已向电视发起握手，电视屏幕正在弹出授权确认，请用遥控器点击【允许】。"
            }
        elif "unable to connect" in full_res.lower() or "cannot connect" in full_res.lower():
            return {
                "ok": False,
                "target": target,
                "status": "offline",
                "error": f"无法连接到 {target}。请确认电视已开机，并已在【设置 - 开发者模式】中开启【网络调试】！"
            }
        else:
            state = await self.get_device_state(target)
            if state == "device":
                return {"ok": True, "target": target, "status": "connected", "message": "连接成功！"}
            elif state == "unauthorized":
                return {
                    "ok": True,
                    "target": target,
                    "status": "unauthorized",
                    "message": "连接成功，请在电视屏幕上点击【允许调试】。"
                }
            return {
                "ok": False,
                "target": target,
                "status": "error",
                "error": full_res or "连接安卓电视失败"
            }

    async def get_device_state(self, target: str) -> str:
        code, out, err = await self._run_adb("devices", timeout=3.0)
        lines = out.splitlines()
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == target:
                return parts[1]
        return "not_found"

    async def ensure_connected(self, target: str) -> bool:
        state = await self.get_device_state(target)
        if state == "device":
            return True
        res = await self.connect(target)
        return res.get("status") == "connected"

    async def send_text(self, target: str, text: str, auto_enter: bool = False) -> Dict[str, Any]:
        if not await self.ensure_connected(target):
            state = await self.get_device_state(target)
            if state == "unauthorized":
                return {"ok": False, "error": "电视未授权调试，请用遥控器在电视屏幕上点击【允许】！"}
            return {"ok": False, "error": f"无法连通电视 {target}，请检查电视是否开机或网络调试是否开启"}

        success = False
        # 1. 尝试剪贴板注入 (支持中文、Emoji、长URL、符号)
        escaped_for_shell = text.replace("'", "'\\''")
        clip_cmd = f"cmd clipboard set text '{escaped_for_shell}'"
        code, out, err = await self._run_adb("-s", target, "shell", clip_cmd, timeout=3.0)
        
        if code == 0:
            code_paste, _, _ = await self._run_adb("-s", target, "shell", "input keyevent 279", timeout=2.0)
            if code_paste == 0:
                success = True

        # 2. 回退到直接 input text
        if not success:
            safe_text = ""
            for ch in text:
                if ch == " ":
                    safe_text += "%s"
                elif ch in '&;<>()|*~`"\'\\':
                    safe_text += f"\\{ch}"
                else:
                    safe_text += ch
            code_input, _, _ = await self._run_adb("-s", target, "shell", f"input text '{safe_text}'", timeout=3.0)
            success = (code_input == 0)

        # 3. 如果需要回车确认 (auto_enter)
        if auto_enter and success:
            await asyncio.sleep(0.15)
            await self._run_adb("-s", target, "shell", "input keyevent 66", timeout=2.0)

        if success:
            return {"ok": True, "message": "文本已注入安卓电视！"}
        return {"ok": False, "error": "向安卓电视注入文本失败"}

    async def clear_text(self, target: str) -> Dict[str, Any]:
        if not await self.ensure_connected(target):
            return {"ok": False, "error": "电视未连接"}

        del_cmds = " && ".join(["input keyevent 67"] * 25)
        await self._run_adb("-s", target, "shell", del_cmds, timeout=3.0)
        return {"ok": True, "message": "已清空电视输入"}

    async def send_remote_command(self, action: str, target: str) -> Dict[str, Any]:
        if not await self.ensure_connected(target):
            return {"ok": False, "error": "电视未连接"}

        key_map = {
            "backspace": "67",
            "delete": "67",
            "enter": "66",
            "select": "66",
            "back": "4",
            "home": "3",
            "up": "19",
            "down": "20",
            "left": "21",
            "right": "22",
            "play_pause": "85",
            "volume_up": "24",
            "volume_down": "25"
        }

        key_code = key_map.get(action.lower())
        if not key_code:
            return {"ok": False, "error": f"未知按键操作: {action}"}

        code, _, err = await self._run_adb("-s", target, "shell", f"input keyevent {key_code}", timeout=2.0)
        if code == 0:
            return {"ok": True, "action": action}
        return {"ok": False, "error": err or "按键发送失败"}

android_mgr = AndroidTVManager()
