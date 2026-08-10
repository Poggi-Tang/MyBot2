# 环境准备

## 支持环境

- Windows 10/11 x64。
- 已登录的微信 4.x 测试账号。
- .NET SDK 10.x。
- Python 3.13 x64。
- PowerShell 5.1 或 7.x。
- 可选：兼容 OpenAI API 的备用/生图模型、本地语音服务、Codex CLI。

当前验证基线为 .NET SDK 10.0.302、Python 3.13、PySide6 6.11、websockets 16+、Pillow 12 和 pytest 9。

## 首次安装

```powershell
git clone https://github.com/Poggi-Tang/MyBot2.git
cd MyBot2
.\setup.cmd
```

脚本会创建 `.venv`、安装 Python 依赖、生成本机 `config.json`，并构建 `sdk/WeChatAuto4_X` 中的 Server。只准备 Python 环境时可运行 `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -SkipSdkBuild`。

## 本机配置

`config.example.json` 是无密钥、无联系人和无历史记录的模板，实际运行读取 `config.json`。主模型密钥是唯一必填凭据；备用模型、生图、语音和 Codex 均可选。默认自动聊天目标为空，Codex 默认关闭。

不要提交 `config.json`。运行时产生的 `data/`、`logs/`、`generated_images/` 和 SDK 输出也已被 Git 忽略。

## 环境自检

```powershell
.\check-environment.cmd
```

微信和 Server 运行后，可增加运行态检查：

```powershell
.\check-environment.cmd -RequireRunningServices
```

自检只显示密钥是否配置，不显示密钥内容。`.cmd` 入口仅为当前命令临时使用 PowerShell `ExecutionPolicy Bypass`，不会修改系统执行策略。
