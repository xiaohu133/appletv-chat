# AppleTV Chat (Apple TV 局域网剪贴板与对话输入助手)

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Web_UI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

专为 **安卓 (Android) / Windows / 非苹果设备用户** 量身打造的局域网 Apple TV 文本与剪贴板输入利器。

无需依赖 iPhone / iPad，只需在安卓手机或电脑浏览器中打开网页，即可通过**类似微信 / 聊天气泡**的极简对话框，将长网址、M3U8 播放源、Token、账号密码等文本**一键秒级同步注入到 Apple TV 电视屏幕输入框**中！

---

## ✨ 核心特性

- 💬 **对话式聊天 UI**：像发微信一样发送文本，自动记录历史发送消息、时间戳与状态，支持一键重发与复制。
- ⚡ **原生直写注入（零冗余字符）**：基于 Apple TV 官方 **Companion 协议**，直接写入文本框（`text_set`），100% 精准无误，不误触发屏幕虚拟键盘。
- 🧹 **极简辅助按键**：操作栏精简至最实用的「**清空电视输入**」与「**退格键 (Backspace)**」。
- 📺 **智能多端口与直连探测**：支持自动局域网扫描与手动 IP 探测（自适应 tvOS 动态分配端口），连接稳定抗干扰。
- 🔐 **一次配对，永久免密**：首次只需输入电视上显示的 4 位数字 PIN 码，凭据加密持久化存储在本地。
- 🐳 **轻量 Docker 容器**：开箱即用，资源占用极小（内存 < 30MB）。

---

## ⚡ 极速部署：Docker Compose 一键运行

在你的 NAS（飞牛 FnOS、群晖、绿联、极空间、1Panel、Portainer）或软路由中新建目录，保存以下 `docker-compose.yml`：

```yaml
services:
  appletv-chat:
    image: ghcr.io/xiaohu133/appletv-chat:latest
    container_name: appletv-chat
    restart: unless-stopped
    network_mode: host
    environment:
      - TZ=Asia/Shanghai
      - DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
```

在同级目录下执行启动命令：
```bash
docker compose up -d
```

启动成功后，在手机或电脑浏览器打开：👉 **`http://<你的设备IP>:8097`**

> 💡 **安卓手机体验提示**：在手机 Chrome / Edge 浏览器打开网页后，点击右上角菜单选择 **「添加到主屏幕」**，即可像原生 App 一样全屏打开使用！

---

## 📱 首次配对向导（仅需 10 秒）

1. 确保 Apple TV 开机并连接在同一局域网内；
2. 安卓手机打开 `http://<设备IP>:8097`，点击右上角的 **⚙️ 设置图标**；
3. 输入 Apple TV 的内网 IP（例如 `192.168.100.171`），点击 **【发起配对】**；
4. 此时 Apple TV 电视屏幕上会弹出一个 **4 位数字 PIN 码**；
5. 在手机弹窗中输入这 4 位数字并确认；
6. **配对成功！** 以后打开网页直接粘贴发送即可。

---

## 🛠️ 本地开发与源码构建

```bash
git clone https://github.com/xiaohu133/appletv-chat.git
cd appletv-chat
docker compose up -d --build
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
