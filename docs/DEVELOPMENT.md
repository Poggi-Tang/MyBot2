# 开发与测试

## 启动

```powershell
.\run.cmd
```

脚本读取本机 `config.json`。5177 端口已有对应 Server 时复用；未监听时启动配置中的 `Server.exe`，WebSocket 稳定握手后才显示 MyBot2 界面。若端口属于其他程序，启动器会报告 PID 和路径并停止，不会结束无关进程。

## 离线验证

```powershell
.\test.cmd
```

默认重新构建 SDK Server 并运行应用 pytest。该流程不发送微信消息、文件或朋友圈。

## 受控在线验证

```powershell
.\test.cmd -SkipSdkBuild -Live
```

在线探针要求测试微信已登录、Server 已连接，并且目标会话属于使用者自己的测试范围。写入类能力应在界面测试模块中核对目标和参数后逐项运行。

## 修改归属

- 微信窗口、控件、消息、表情、文件、语音、引用或撤回：`sdk/WeChatAuto4_X`。
- WebSocket 命令与序列化：SDK Server，并补协议测试。
- 自动回复、人格、记忆、并发、模型与工具选择：`mybot_ui/`。
- 通用耗时任务：优先沉淀到 `extensions/abilities/`，由 MCP 登记结果。

跨层修改至少验证 SDK 编译和应用离线测试；涉及真实微信操作时，再对测试账号执行最小范围在线验证。
