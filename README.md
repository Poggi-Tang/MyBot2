# MyBot2

MyBot2 是面向 Windows 微信 4.x 的桌面自动聊天与自动化测试工具。它把 WeChatAuto4_X、文本/视觉模型、人物记忆、表情能力、文件任务和功能测试台整合到一个界面中。

> 本项目用于本人账号、测试账号和已获授权的会话。自动化操作可能受微信版本、界面语言和平台规则影响，请先在测试账号验证，不要用于骚扰、群发或绕过平台限制。

## 主要能力

- 选择私聊或群聊后持续自动回复，保留会话上下文并支持受控并发。
- 文本和视觉模型路由、图片理解与图生图、原始媒体附件处理。
- 自定义/收藏表情扫描、语义匹配和发送。
- 引用回复、文件收发、语音发送，以及带情绪转折和韵律控制的 Higgs 配音表演。
- 人格、示例对话、个人偏好和情景记忆。
- WeChatAuto4_X 功能列表及安全/完整测试模块。
- 可选 Codex CLI 异步任务和可复用能力包。
- 客户端、模型、MCP、Codex 和 Server 操作耗时日志。

## 快速部署

### Windows 安装包

普通用户可从 GitHub Releases 下载 `MyBot2-Setup-x.y.z-x64.exe`。安装向导可选择安装目录、内置 Python、SDK/快捷能力和可选 Codex CLI，也可当场填写主模型 API 或进入 MyBot 后再配置。默认不安装 Codex CLI；以后可在“系统配置 → 模型配置 → Codex CLI 扩展”中从 OpenAI 官方下载安装。

MyBot 启动后每 10 分钟检查一次 GitHub Release。发现新版本时，界面会显示“可更新”，下载按钮会同时获取安装包及 `.sha256` 文件，校验通过后退出当前版本、覆盖安装并重新启动。升级安装会保留安装目录中的 `config.json` 和 `data/`。

### 1. 准备环境

- Windows 10/11 x64
- 微信 4.x，并已登录自己的测试账号
- Python 3.13 x64（安装时勾选加入 `PATH`）
- .NET SDK 10.x
- 一个兼容 OpenAI API 的文本/视觉模型接口

### 2. 安装

```powershell
git clone https://github.com/Poggi-Tang/MyBot2.git
cd MyBot2
.\setup.cmd
```

`setup.cmd` 会创建 `.venv`、安装 Python 依赖、从 `config.example.json` 生成本机 `config.json`，并编译随仓库提供的 WeChatAuto4_X Server。

### 3. 配置

用文本编辑器打开 `config.json`，至少填写 `primary.base_url`、`primary.model` 和 `primary.api_key`。备用模型、生图、语音和 Codex 都是可选项，默认不会接管任何会话，也不会执行微信写入操作。

接口地址填写服务根地址，例如 `https://api.openai.com` 或服务商给出的兼容地址。`config.json` 是本机明文配置，已被 Git 忽略，请勿提交或发送给他人。

### 4. 检查并启动

```powershell
.\check-environment.cmd
.\run.cmd
```

启动器会在 `ws://127.0.0.1:5177/ws` 启动或复用 Server，握手成功后显示桌面界面。进入“自动聊天”选择允许接管的会话，确认模型测试通过，再点击“开始自动聊天”。选择状态可保存到本机配置。

## 测试

离线测试不会发送微信消息：

```powershell
.\test.cmd
```

界面中的完整测试会产生真实消息、文件或朋友圈操作，只应对测试账号和明确允许的会话逐项执行。

维护者可用以下命令构建与 GitHub Release 同名的 Windows 安装包：

```powershell
.\scripts\build-installer.ps1 -Version 2.3.0 -IncludeCodex
```

产物位于 `dist/`，包括安装程序和对应的 SHA256 文件。GitHub Actions 也会在推送 `v*` 标签后运行同一构建流程并上传这两个 Release Asset。

## 可选 Codex CLI

仓库不附带 Codex CLI 可执行文件。需要该功能时，进入“系统配置 → 模型配置 → Codex CLI 扩展”，点击“安装 CLI”。MyBot 会从 OpenAI 官方 Release 下载经过 SHA256 校验的 Windows 完整包，并安装到项目的 `data/codex/runtime`。

安装完成后，在同一页面填写 CLI 专用 API 地址、模型和密钥，测试通过后再启用任务调度。CLI 运行文件、`CODEX_HOME`、会话和配置都保留在当前项目内，不读取用户全局 Codex 配置。

## 目录

- `mybot_ui/`：桌面界面、自动聊天、模型、记忆、媒体和调度。
- `mybot_mcp/`：Codex 任务回调 MyBot 的 MCP 服务。
- `codex/skills/`：Codex 使用的 MyBot 技能。
- `extensions/`：可审核、可复用的快捷能力包。
- `sdk/`：构建所需的 WeChatAuto4_X 和 WeAutoCommon 源码。
- `tests/`：应用离线测试和显式在线探针。
- `data/`、`logs/`：首次运行后生成的私人数据，不进入版本库。

更多信息见 [环境准备](docs/ENVIRONMENT.md)、[开发与测试](docs/DEVELOPMENT.md)、[架构](docs/ARCHITECTURE.md)、[迭代说明](docs/ITERATION_NOTES.md) 和 [故障排查](docs/TROUBLESHOOTING.md)。

## 许可证

MyBot2 应用代码使用 [MIT License](LICENSE)。`sdk/` 中的 WeChatAuto.SDK 源码保留其上游 MIT 许可证和版权声明，详见 [sdk/LICENSE](sdk/LICENSE)。
