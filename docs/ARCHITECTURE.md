# 架构

## 运行链路

```text
微信 4.x
  <-> WeChatAuto (.NET UI Automation)
  <-> WebSocket Server :5177/ws
  <-> Python Gateway
  <-> 自动聊天与任务调度
  <-> 文本/视觉模型、可选语音服务、可选 Codex CLI/MCP
```

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `mybot_ui/` | 界面、自动聊天、提示词、模型、记忆、附件、表情与任务编排 |
| `mybot_mcp/` | Codex 完成任务后回调 MyBot 的 MCP 接口 |
| `codex/skills/` | Codex 面向 MyBot 工作区的能力说明 |
| `extensions/` | 已审核、可复用的快捷能力包 |
| `sdk/WeChatAuto4_X/` | 微信 UI Automation 与 WebSocket Server |
| `sdk/WeAutoCommon/` | SDK 公共组件 |
| `tests/` | 离线应用测试和显式在线探针 |
| `data/` | 运行状态与每个会话的私人工作空间，不是源码 |

## 固定契约

- WebSocket：`ws://127.0.0.1:5177/ws`。
- 语音服务：默认 `http://127.0.0.1:50001`，可选。
- Server 输出：`sdk/WeChatAuto4_X/WebSocketServer/Server/bin/Debug/net10.0-windows`。
- 本机配置：根目录 `config.json`，明文可编辑但不进入版本库。
- 运行日志：客户端 `logs/`，Server 输出目录中的 `logs/`。

`main.py` 负责单实例和崩溃诊断，`mybot_ui/api.py` 负责 WebSocket，`app_v2.py` 编排界面和工作流，`chat_engine.py` 负责模型与上下文，`auto_chat.py` 负责入站去重和发送回声跟踪。原始媒体由 `attachments.py` 保存，图片哈希语义缓存在 `image_understanding.py`，人物和情景记忆分别由 `personal_memory.py`、`episodic_memory.py` 管理。
