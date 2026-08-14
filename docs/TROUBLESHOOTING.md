# 故障排查

## 双击 run.cmd 后连接失败

1. 先运行 `.\setup.cmd`，确认 SDK 已成功构建。
2. 运行 `.\check-environment.cmd` 查看 Python、.NET、配置和 Server 路径。
3. 用 `Get-NetTCPConnection -State Listen -LocalPort 5177` 检查端口。
4. 端口被其他程序占用时，MyBot2 会显示 PID 并停止，不会强制结束无关进程。
5. 查看根目录 `crash.log`、`runtime.log` 和 Server 输出目录的日志。

## 微信窗口消失但仍登录

Server 默认每 1.5 秒检查主窗口；连续两次发现窗口隐藏或最小化后，会尝试显示或还原，但不会置顶。日志中的 `window_restored` 或 `window_restore_failed` 会记录 PID、句柄、状态和耗时。不要将检查间隔改到 500 毫秒以下。

## 自动聊天没有回复

- UI 顶部应显示已连接账号，开始按钮应显示运行状态。
- 确认已选择会话，且主模型测试通过。
- 依次检查是否收到消息、是否命中去重、是否冷却、模型是否成功、发送是否成功。
- 客户端操作记录在 `logs/client-operations-YYYYMMDD.jsonl`，界面诊断在 `runtime.log`。
- 任一 SDK/UIA 命令超时后，客户端会立即停止监听、轮询和发送，断开自动化通道并清空当前任务。确认微信可以正常手动操作后，再手动连接并重新选择接管会话。
- 恢复过程不会退出或重启微信、不会注销微信账号，也不会自动恢复上次接管的会话。禁止把结束 `Weixin.exe`/`WeChat.exe` 或重新登录作为自动恢复步骤。

## 图片或文件无法处理

- 图片理解和图生图应使用微信原始媒体，而不是聊天区域截图。
- 文件进入 `data/attachments/` 或 `data/codex/tasks/<task-id>/inputs/`。
- 先确认 SDK 返回原图或原文件路径，再检查模型或 Codex 调度。

## Codex 任务不可用

公开仓库默认关闭 Codex，且不附带其大体积可执行文件。安装官方 Codex CLI 和项目所需代理后，在 `config.json` 配置两个可执行文件路径并启用 `codex.enabled`。普通自动聊天不依赖 Codex。
