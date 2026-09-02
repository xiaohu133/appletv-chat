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

## 🚀 飞牛 NAS (FnOS) 图形化极速部署（免命令行，推荐）

如果你使用 **飞牛 NAS (FnOS)**，无需连接 SSH 敲命令，直接在飞牛桌面通过图形化 Compose 一键部署：

1. 打开飞牛 NAS 桌面，进入 **「Docker」** 应用；
2. 在左侧菜单栏点击 **「Compose」** ➔ 点击顶部 **「➕ 添加项目」**；
3. **项目名称**：填写 `appletv-chat`；
4. **项目路径**：选择一个存放目录（如 `/vol1/1000/docker/appletv-chat`）；
5. 在右侧 **YAML 编辑框** 中，完整粘贴以下内容：

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
      # 配对凭据与配置数据持久化目录
      - ./data:/app/data
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
```

6. 勾选 **「创建后立即启动」**，点击底部的 **「确定 / 创建」** 即可完成部署！

---

## ⚡ 通用 Docker Compose 命令行部署（群晖 / 绿联 / 软路由 / Linux）

在任意支持 Docker 的设备中新建目录，创建 `docker-compose.yml` 并粘贴上方配置，随后在同级目录下执行：

```bash
docker compose up -d
```

> ⚠️ **关键参数说明**：
> - `network_mode: host`：**必须开启 Host 网络模式**。因为 Apple TV 的局域网设备探测与通信依赖局域网组播/同一子网直连。
> - `./data:/app/data`：用于持久化存储 Apple TV 的配对凭据，避免容器重启后丢失配对信息。

---

## 📱 首次配对向导（仅需 10 秒，以后永久免密）

1. 确保 Apple TV 开机并连接在同一局域网内；
2. 手机或电脑浏览器打开：👉 **`http://<你的NAS_IP>:8097`**；
3. 点击右上角的 **⚙️ 设置图标**；
4. 在下方输入框填入 Apple TV 的内网 IP（例如 `192.168.100.171`），点击 **【发起配对】**；
5. 此时 Apple TV 电视屏幕上会弹出一个 **4 位数字 PIN 码**；
6. 在手机弹窗中输入这 4 位数字并确认；
7. **配对成功！** 以后打开网页直接粘贴发送即可。

> 💡 **安卓手机使用小技巧**：在手机 Chrome / Edge 浏览器打开网页后，点击浏览器右上角菜单选择 **「添加到主屏幕」**，即可像原生 App 一样直接从手机桌面全屏使用！

---

## 🛠️ 本地源码构建开发

```bash
git clone https://github.com/xiaohu133/appletv-chat.git
cd appletv-chat
docker compose up -d --build
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。
