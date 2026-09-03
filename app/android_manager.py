import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional

logger = logging.getLogger("appletv_chat.android")

class AndroidTVManager:
    def __init__(self):
        self.lock = asyncio.Lock()
        data_dir = os.environ.get("DATA_DIR", "/app/data")
        self.adb_home = os.path.join(data_dir, ".android")
        os.makedirs(self.adb_home, exist_ok=True)
        os.environ["HOME"] = data_dir
        os.environ["ADB_VENDOR_KEYS"] = self.adb_home

    async def _run_adb(self, *args: str, timeout: float = 8.0) -> tuple[int, str, str]:
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
            out = stdout.decode("utf-8", errors="ignore").strip()
            err = stderr.decode("utf-8", errors="ignore").strip()
            return proc.returncode or 0, out, err
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return -1, "", "ADB 命令超时"
        except FileNotFoundError:
            return -1, "", "系统未找到 adb 命令"
        except Exception as e:
            return -1, "", str(e)

    def _format_target(self, address: str, port: int = 5555) -> str:
        addr = address.strip()
        if ":" in addr and not addr.startswith("["):
            return addr
        return f"{addr}:{port}"

    async def connect(self, address: str, port: int = 5555) -> Dict[str, Any]:
        target = self._format_target(address, port)
        logger.info(f"ADB 连接: {target}")

        code, out, err = await self._run_adb("connect", target, timeout=5.0)
        full_res = f"{out} {err}".strip()

        if "connected to" in full_res.lower():
            state = await self.get_device_state(target)
            if state == "unauthorized":
                return {
                    "ok": True,
                    "target": target,
                    "status": "unauthorized",
                    "message": "已连通电视，请用电视遥控器在屏幕上点击【允许调试】！"
                }
            return {"ok": True, "target": target, "status": "connected", "message": "连接成功！"}
        elif "failed to authenticate" in full_res.lower() or "unauthorized" in full_res.lower():
            return {
                "ok": True,
                "target": target,
                "status": "unauthorized",
                "message": "电视屏幕正在弹出授权提示，请用遥控器点击【允许】。"
            }
        elif "unable to connect" in full_res.lower() or "cannot connect" in full_res.lower():
            return {
                "ok": False,
                "target": target,
                "status": "offline",
                "error": f"无法连通 {target}。请检查电视是否开机，并在【开发者选项】中开启【网络调试】！"
            }
        else:
            state = await self.get_device_state(target)
            if state == "device":
                return {"ok": True, "target": target, "status": "connected", "message": "连接成功！"}
            return {"ok": False, "target": target, "status": "error", "error": full_res or "连接失败"}

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
        if state != "device":
            res = await self.connect(target)
            if res.get("status") != "connected":
                return False

        # 确保 ADBKeyboard 已就绪
        try:
            code, out, _ = await self._run_adb("-s", target, "shell", "pm path com.android.adbkeyboard", timeout=2.0)
            if "package:" not in out:
                apk_path = Path(__file__).parent / "ADBKeyboard.apk"
                if apk_path.exists():
                    logger.info(f"正在为电视 {target} 自动安装 ADBKeyboard 输入助手...")
                    await self._run_adb("-s", target, "install", "-r", str(apk_path), timeout=15.0)
                    await self._run_adb("-s", target, "shell", "ime enable com.android.adbkeyboard/.AdbIME", timeout=2.0)
                    await self._run_adb("-s", target, "shell", "settings put secure default_input_method com.android.adbkeyboard/.AdbIME", timeout=2.0)
        except Exception as e:
            logger.warning(f"ADBKeyboard 检查/安装异常: {e}")

        return True

    async def send_text(self, target: str, text: str, auto_enter: bool = False) -> Dict[str, Any]:
        """向安卓电视注入文本，原生自适应中英文、特殊字符与长链接"""
        if not await self.ensure_connected(target):
            state = await self.get_device_state(target)
            if state == "unauthorized":
                return {"ok": False, "error": "电视未授权调试，请在电视屏幕上勾选始终允许并点击【允许】！"}
            return {"ok": False, "error": f"无法连接到电视 {target}，请检查电视开机与网络调试状态"}

        clean_text = text.strip()
        if not clean_text:
            return {"ok": True, "message": "空文本无需发送"}

        # 检查是否包含非 ASCII (如中文、日韩文、Emoji等)
        has_non_ascii = any(ord(c) > 127 for c in clean_text)
        
        if has_non_ascii:
            # 1. 确保 ADBKeyBoard 为活跃输入法
            await self._run_adb("-s", target, "shell", "settings put secure default_input_method com.android.adbkeyboard/.AdbIME", timeout=2.0)
            await self._run_adb("-s", target, "shell", "ime set com.android.adbkeyboard/.AdbIME", timeout=2.0)
            
            # 2. 转义单引号以安全传递给 shell
            escaped_text = clean_text.replace("'", "'\\''")
            broadcast_cmd = f"am broadcast -a ADB_INPUT_TEXT --es msg '{escaped_text}'"
            logger.info(f"正在发送中文广播: {clean_text} 到 {target}")
            code, out, err = await self._run_adb("-s", target, "shell", broadcast_cmd, timeout=4.0)
            if code != 0 or "result=0" not in out:
                logger.warning(f"ADB_INPUT_TEXT 广播未完全成功: {out} {err}")
        else:
            # 针对纯 ASCII、英文、数字、URL 或 Token，采用 input text 原生直写
            safe_str = ""
            for ch in clean_text:
                if ch == " ":
                    safe_str += "%s"
                elif ch in '&;<>()|*~`"\'\\$':
                    safe_str += f"\\{ch}"
                else:
                    safe_str += ch

            logger.info(f"正在发送 input text: {safe_str} 到 {target}")
            code, out, err = await self._run_adb("-s", target, "shell", f"input text '{safe_str}'", timeout=4.0)
            if code != 0:
                # 备选：如果 input text 失败，降级通过 ADB_INPUT_TEXT 发送
                escaped_text = clean_text.replace("'", "'\\''")
                await self._run_adb("-s", target, "shell", f"am broadcast -a ADB_INPUT_TEXT --es msg '{escaped_text}'", timeout=3.0)

        # 如果需要自动回车确认
        if auto_enter:
            await asyncio.sleep(0.15)
            # 发送 DPAD_CENTER (23) 和 ENTER (66) 确保各类 TV App 都能识别
            await self._run_adb("-s", target, "shell", "input keyevent 66", timeout=2.0)
            await self._run_adb("-s", target, "shell", "input keyevent 23", timeout=2.0)

        return {"ok": True, "message": "文本已注入电视！"}

    async def clear_text(self, target: str) -> Dict[str, Any]:
        """清空电视输入框：ADBKeyBoard 清空广播 + 移动到末尾后连续退格"""
        if not await self.ensure_connected(target):
            return {"ok": False, "error": "电视未连接"}

        # 1. 发送 ADBKeyBoard 清空广播
        await self._run_adb("-s", target, "shell", "am broadcast -a ADB_CLEAR_TEXT", timeout=2.0)

        # 2. 123 是 KEYCODE_MOVE_END，将光标移动到文本末尾，再发 25 次退格 (67)
        clear_cmd = "input keyevent 123"
        for _ in range(25):
            clear_cmd += " && input keyevent 67"
        
        await self._run_adb("-s", target, "shell", clear_cmd, timeout=4.0)
        return {"ok": True, "message": "已清空电视输入框"}

    async def send_remote_command(self, action: str, target: str) -> Dict[str, Any]:
        """发送遥控器按键"""
        if not await self.ensure_connected(target):
            return {"ok": False, "error": "电视未连接"}

        key_map = {
            "up": [19],                 # KEYCODE_DPAD_UP
            "down": [20],               # KEYCODE_DPAD_DOWN
            "left": [21],               # KEYCODE_DPAD_LEFT
            "right": [22],              # KEYCODE_DPAD_RIGHT
            "select": [23, 66],         # KEYCODE_DPAD_CENTER & KEYCODE_ENTER
            "ok": [23, 66],
            "enter": [66, 23],
            "back": [4],                # KEYCODE_BACK
            "home": [3],                # KEYCODE_HOME
            "backspace": [123, 67],     # KEYCODE_MOVE_END & KEYCODE_DEL
            "delete": [123, 67],
            "volume_up": [24],          # KEYCODE_VOLUME_UP
            "volume_down": [25],        # KEYCODE_VOLUME_DOWN
            "mute": [164],              # KEYCODE_VOLUME_MUTE
            "play_pause": [85],         # KEYCODE_MEDIA_PLAY_PAUSE
            "menu": [82]                # KEYCODE_MENU
        }

        codes = key_map.get(action.lower())
        if not codes:
            return {"ok": False, "error": f"未知按键: {action}"}

        for c in codes:
            await self._run_adb("-s", target, "shell", f"input keyevent {c}", timeout=2.0)

        return {"ok": True, "action": action}

android_mgr = AndroidTVManager()
