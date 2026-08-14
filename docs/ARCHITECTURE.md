# 架构

## 运行链路

```text
微信 4.x
  <-> Python UIA 消息监听/消息解析/引用菜单 OCR
  <-> WeChatAuto (.NET 其余 UI Automation)
  <-> WebSocket Server :5177/ws
  <-> Python backend ports/adapters
  <-> 自动聊天与任务调度
  <-> 文本/视觉模型、可选语音服务、可选 Codex CLI/MCP
```

## 分层与依赖方向

```text
Qt View (`app_v2.py`)
  -> ApplicationBackend
       -> WeChatAutomationPort -> GatewayWeChatAutomation -> Gateway
       -> ModelOperationsPort  -> ModelOperations -> ChatModelClient
       -> ServerLifecyclePort  -> WindowsServerLifecycle -> Server.exe/Win32
       -> ApplicationServices
            -> ConversationMemoryPort
            -> PersonalMemoryPort / EpisodicMemoryPort / DailyWorkspacePort
            -> AttachmentWorkspacePort
            -> ExtensionManagementPort -> ExtensionManagement -> ExtensionRegistry
            -> CodexOperationsPort -> CodexOperations -> CodexRuntimeManager/CodexCliRunner
            -> TaskExecutors
            -> MemoryController -> memory/workspace state DTOs
            -> ExtensionController -> MCP/Skill state DTOs
            -> ConversationTaskController -> queue/concurrency state machine
            -> ConversationRouteController -> structured RouteDecision
            -> ConversationActionExecutor -> registered action handlers
                 -> ConversationActionHost -> Qt/application adapters
            -> ConversationScanner -> Python UIA conversation discovery
```

- `app_v2.py` 是 Qt View 和界面事件 Controller；它读取控件状态、提交接口请求并渲染结果，不创建具体业务存储、模型客户端、Gateway、CLI 或线程池。
- `backend.py` 是无 Qt 依赖的组合根，定义类型化 Port、应用服务容器、任务执行器和基础设施适配器。
- 微信功能统一通过 `WeChatCommand` 调度，不允许 View 直接调用具体 `Gateway.call()`。
- 模型功能通过 `ModelOperationsPort` 调度，不允许 View 构造具体模型客户端。
- 记忆、日期工作区、附件、MCP/Skill 和 Codex CLI 均由 `ApplicationServices` 装配，通过各自 Port 暴露给界面。
- `MemoryController` 负责人物搜索、详情、日期工作区查询以及画像增删改；Qt 层只渲染 DTO 和显示确认框。
- `ExtensionController` 负责组合 CLI 运行态、MCP/Skill 注册态及自动匹配能力，Qt 层不直接读写注册表。
- `ConversationTaskController` 是对话任务队列、单会话并发计数、任务占用/释放和耗时状态的唯一生产态所有者。
- `ConversationRouteController` 按固定优先级输出 `RouteDecision`，集中处理安全拒绝、修图续接、实时工具、Codex 和显式回复类型判断。
- `ConversationActionExecutor` 根据 `RouteDecision` 调度已注册的安全拒绝、修图、实时工具、Codex、生图、表情、拍一拍和模型回复 handler；它只依赖 `ConversationActionHost`，不依赖 Qt 窗口类型。
- `ConversationScanner` 使用 Python `uiautomation` 直接扫描微信会话列表，并通过固定 AutomationID 的顶部标题人数准确区分群聊和私聊；.NET SDK 不再承担会话类型分类。
- `WeChatMessageService` 使用 DebugTool 算法直接监听会话变化、分析消息气泡和识别发送者；监听和发送共享操作锁，避免 UIA 并发操作微信。
- 引用回复由 Python UIA 在当前消息页从新到旧查找，找不到时向上翻页；右键后仅匹配 `Name=Weixin`、`ClassName=mmui::XMenu` 的窗口，并通过 OCR 点击“引用”。WebSocket Server 不再公开 .NET 普通消息监听命令，也不再解析 `ChatRefer`。
- 功能按业务边界使用类型化接口，不建设接收任意字符串的全局“万能总线”；只有微信 SDK 原生函数因其协议本身使用 `WeChatCommand`。
- Server 进程发现、停止、启动、端口等待及开发 DLL 同步只能存在于 `ServerLifecyclePort` 实现。
- MCP 是对外适配器，不是应用内部唯一调用方式；UI 与 MCP 应复用同一应用服务契约。
- 依赖方向只能从 View 指向接口，不允许后台模块依赖 PySide6 或具体窗口类型。

## 当前迁移边界

本轮完成的是模块化和依赖倒置基础，不把单文件机械拆分冒充完整 MVC：

- 已移出 View：依赖装配、路径解析、Gateway、模型客户端、Server 生命周期、记忆/工作区/附件存储创建、记忆管理命令与查询、MCP/Skill 管理、Codex 运行时与 Runner 创建、对话队列状态机、路由选择、动作 handler 调度和后台线程池生命周期。
- 仍在 View/Controller：自动对话的异步发送结果衔接、语音/图片/表情的 Qt 回调适配，以及把应用状态转换为 Qt 控件状态。
- 下一阶段继续把异步发送结果和会话完成状态抽为无 Qt 的应用服务；Qt 层最终只绑定信号、实现 `ConversationActionHost` 适配并渲染状态快照。

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `mybot_ui/app_v2.py` | Qt View、事件绑定及待继续抽离的流程 Controller，不实现基础设施或依赖装配 |
| `mybot_ui/backend.py` | 应用服务契约、组合根、任务执行器及微信/模型/Server 适配器 |
| `mybot_ui/controllers.py` | 无 Qt 的记忆、扩展和对话队列 Controller，以及 View DTO |
| `mybot_ui/conversation_actions.py` | 无 Qt 的对话动作执行器、动作 handler 注册和宿主 Port |
| `mybot_ui/conversation_scanner.py` | 独立 Python UIA 会话扫描器，返回群聊/私聊结构化结果 |
| `mybot_ui/wechat_message_service.py` | Python UIA 消息监听、跨页引用定位和操作互斥 |
| `mybot_ui/wechat_message_analysis.py` | 消息类型、方向、发送者和引用元数据分析 |
| `mybot_ui/wechat_menu_ocr.py` | 微信右键菜单区域裁剪与“引用”OCR 定位 |
| `mybot_ui/` 其余模块 | 自动聊天、提示词、模型、记忆、附件、表情与任务编排 |
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

`main.py` 负责单实例和崩溃诊断，`mybot_ui/api.py` 负责 WebSocket，`backend.py` 隔离应用接口与基础设施，`app_v2.py` 负责界面交互，`chat_engine.py` 负责模型与上下文，`auto_chat.py` 负责入站去重和发送回声跟踪。原始媒体由 `attachments.py` 保存，图片哈希语义缓存在 `image_understanding.py`，人物和情景记忆分别由 `personal_memory.py`、`episodic_memory.py` 管理。
