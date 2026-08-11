# WeChatAuto4_X

WeChatAuto4_X 是 MyBot2 当前使用的微信 4.x 自动化底座。它负责 Windows UI Automation、消息和媒体操作以及 WebSocket 服务；AI 对话、人物记忆和任务调度位于仓库根目录的 `mybot_ui/`。

## 分层

- `WeChatAuto/`: .NET 自动化核心。
- `WebSocketServer/Server/`: 当前生产调试使用的无界面 WebSocket Server。
- `WebSocketServer/Server_UI/`: SDK 自带的服务管理 UI，不是 MyBot 2.0 UI。
- `wechatauto_py/`: Python 协议客户端和模型。
- `WeChatAuto.Tests/`: .NET 测试。
- `Examples/`: 独立示例。

## 环境

- Windows 10/11 x64
- 微信 4.x，已登录测试账号
- .NET SDK 10.x
- Python 3.13（仅 Python SDK 和 MyBot 2.0 需要）

## 构建

```powershell
cd sdk\WeChatAuto4_X
.\build.cmd
```

输出位于 `WebSocketServer\Server\bin\Debug\net10.0-windows`。

## 启动 Server

```powershell
.\run-server.cmd
```

统一开发地址为 `http://127.0.0.1:5177`，WebSocket 地址为 `ws://127.0.0.1:5177/ws`。脚本在当前终端前台运行服务，便于看到启动和错误日志；MyBot 2.0 的 `run.cmd` 会在需要时后台启动同一个可执行文件。

如果 5177 已由 `Server.exe` 监听，脚本会显示现有 PID 并正常退出，不会重复启动。双击运行时窗口会保留，按任意键关闭；自动化调用可设置 `MYBOT_NO_PAUSE=1` 跳过等待。

## 测试

```powershell
.\test.cmd
```

默认执行构建、Python SDK 编译检查和测试收集，不连接微信。Python SDK 和 .NET 的在线 UI 集成测试必须显式使用 `test.cmd -LiveWeChat`。

## 日志

- Server 操作日志：Server 输出目录下 `logs\server-operations-YYYYMMDD.jsonl`。
- 附件、截图和媒体诊断日志由对应 SDK 操作写入，不应记录原始 Base64 或密钥。
- 每个外部操作应包含开始、结束、成功状态和 `duration_ms`。
