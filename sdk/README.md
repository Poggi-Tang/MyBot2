# WECHATAUTO.SDK - 面向AI的现代化微信RPA自动化框架

[![.NET](https://img.shields.io/badge/.NET-6.0%2B-blue)](https://dotnet.microsoft.com/)
[![Python](https://img.shields.io/badge/Python-3.13%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

WeChatAuto.SDK 是一款面向 AI 的微信RPA自动化 SDK，基于 .NET 与 UI 自动化技术开发。它专为集成人工智能（如 LLM 上下文交互）场景设计。SDK 提供丰富直观的 API，支持 .NET 现代化特性，比如依赖注入，也提供官方Python SDK，让你轻松在现有系统中集成进微信自动化流程。

## ✨ 特性

- 💬 **完善的消息与社交能力** - 支持发送文字、表情、文件、@提醒、转发消息、群管理、朋友圈操作与通讯录管理，并提供消息监听等常用能力；所有重要接口均覆盖单元测试。
  
- 🛡️ **降低风控风险** - 支持纯软件自动化与结合硬件键鼠模拟器的方案，可根据业务需求与安全等级选择更稳健的执行方式。

- 🚀 **多实例与分布式支持** - 可同时管理多个微信客户端，既可作为本机 SDK 使用，也可通过 WebSocket 长连接实现一台应用控制多台机器的多个微信或多应用控制同一个微信。

- 🔧 **微信版本兼容** - 兼容旧版（如 3.9.12.xx）与新版（如 4.1.11.xx）微信，并持续更新以适配新版客户端。

- 🧩 **多语言支持** - 原生使用 .NET 开发，同时提供官方 Python SDK，方便不同语言生态集成。

- 🔌 **易于集成与高可靠性** - 支持依赖注入，轻量SDK，易嵌入现有系统；采用工业级线程管理与稳定性设计，降低 UI 自动化卡死风险。

- 🤖 **AI 友好** - 原生支持 LLM 上下文对接并内置 MCP Server，便于接入主流智能体与平台，助力智能应用集成微信自动化/RPA闭环与扩展。


> 👉 如果觉得有帮助，欢迎点赞、Star和Fork本项目，以免失联，感谢支持！

> 👉 如果需要体验WeChatAuto.SDK的通力，我架设了一个测试导航机器人，欢迎添加微信好友体验，👉 [我要体验](./MD/Experience.md)


## 🎉 重要说明!!


**WeChatAuto.SDK** 提供两个版本的SDK:

---

#### ⚡ 微信 4.1.xx（微信最新版本）

- 基于微信 4.1.xx 最新微信客户端的持续演进版本，支持 .NET 与 Python 双平台;
- 微信4.1.xx版本为**UI Tree + OCR** 混合自动化解决方案，OCR使用的是本地onnx-runtime模型[RapidOCRCSharp，有需要的也请给RapidOCRSharp点一个赞👍](https://github.com/RapidAI/RapidOCRCSharp)  ;
- 开源情况：核心代码 - 100%开源，文档、视频 - 100%开源,业务代码 - 80%开源 (20%的api属于vip独有);

**使用指南**

👉 完整的文档请参考: ... 完成中 ...

👉 我的最新版微信没有UI Tree,这个怎么办？ 请参考: [我的最新版微信没有UI Tree,这个怎么办？](https://github.com/scottfly189/WeChatAuto.SDK/issues/3)

👉 WechatAuto4x.SDK源码请考：[WechatAuto4x.SDK源码](https://github.com/scottfly189/WeChatAuto.SDK/tree/master/WeChatAuto4_X)

👉 如需体验最新版的微信自动化RAP，请点击链接进入: 👉 [我要体验](./MD/Experience.md)

---

#### 🧱 微信 3.9.12.xx

- 纯UI Tree自动化解决方案;
- 仅支持 .NET 平台;
- 源码 100% 开源;
- 文档 100% 开源;

**使用指南**

👉 完整的文档请参考: [WeChatAuto.SDK 3.9.12.xx文档](https://scottfly189.github.io/WeChatAuto.SDK/)

👉 安装不上微信客户端3.9.12.xx？ 请参考: [如何安装3.9.12.xx等微信低版本客户端](https://github.com/scottfly189/WeChatAuto.SDK/issues/2)

👉 SDK源码与DEMO项目演示，请参考: [3.9.12.xx源码及DEMO项目](https://github.com/scottfly189/WeChatAuto.SDK/tree/master/WeChatAuto3_9_12_xx)


## ✨ 代码演示

下面的示例代码都基于**WechatAuto.SDK 4.x 最新微信**版本，分.net与python两个版本演示了如何使用SDK进行微信自动化操作。

#### 🚀 .NET 自动化微信最新版本演示

- 新建一个.net10控制台项目

```csharp
dotnet new console -n demo
```

- 修改项目属性，打开 demo.csproj 文件，把```TargetFramework```修改为```net10.0-windows```,如果你使用的是.net6.0或.net7.0，请把```TargetFramework```修改为```net6.0-windows```或```net7.0-windows```，如下所示:
```xml
<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>

</Project>

```

- 安装依赖包
  
```bash
dotnet add package Microsoft.Extensions.DependencyInjection
dotnet add package WeChatAuto4x.SDK
```

- 把OCR模型文件放到项目根目录下(我这里是:```D:\repo\WeChatAuto.SDK\test\demo\bin\Debug\net10.0-windows\models```)，OCR模型文件下载地址：[模型文件下载](https://github.com/scottfly189/WeChatAuto.SDK/tree/master/Tools)

> 注：直接拷贝models文件夹到项目根目录下即可，或者在代码中指定模型文件路径。

- 在 Program.cs 中编写如下代码：

```csharp
using WeChatAuto.Services;
using WeChatAuto.Components;
using Microsoft.Extensions.DependencyInjection;

var serviceProvider = WeAutomation.Initialize(options =>
{
    options.DebugMode = false;   // 可选，在生产环境建议关闭
    options.EnableOCR = true;    // 必须打开
});

using var clientFactory = serviceProvider.GetRequiredService<WeChatClientFactory>();
//检查打开有几个微信
var wechat_list = clientFactory.GetWeChatClientNames();
Console.WriteLine($"电脑上打开微信{wechat_list.Count()}个: {string.Join(',',wechat_list)}");

// 打开第一个微信，发送消息
var client = clientFactory.GetWeChatClient(wechat_list.First());
// 给好友 AI.Net_test 发送文本消息
await client.SendMessage("AI.Net_test","hello world!!");
... 更多功能请参考文档
```

#### 🚀 Python 自动化微信最新版本演示

>注：python SDK 不依赖 .NET，直接使用python即可。

1. 首先下载WeChatAuto4x.SDK的WebSocket Server端，并打开，具体方法如下：
   - 下载地址：[WeChatAuto4x.SDK WebSocket Server](https://github.com/scottfly189/WeChatAuto.SDK/releases/download/1.2.9/Server_Community.rar)
   - 解压后，双击运行 Server.exe
   - 显示在```Now listening on: http://localhost:5000```监听,如下所示：
   ```
      keys Size = 18385
      info: Program[0]
            总共打开微信 1 个：Alex
      info: Microsoft.Hosting.Lifetime[14]
            Now listening on: http://localhost:5000
      info: Microsoft.Hosting.Lifetime[0]
            Application started. Press Ctrl+C to shut down.
      info: Microsoft.Hosting.Lifetime[0]
            Hosting environment: Production
      info: Microsoft.Hosting.Lifetime[0]
            Content root path: C:\Users\Administrator\Downloads\Server_Community\Server
   ```

2. 新建一个python项目
```
uv init demo-python
cd demo-python
```
3. 安装wechatauto4x.sdk依赖
```
uv add wechat-auto4x-sdk
```
4. 在项目根目录下创建或编辑 main.py 文件，编写如下代码：

```python
import asyncio

from wechat_auto_sdk import WeChatClient
from wechat_auto_sdk import WeChatConfig
from wechat_auto_sdk import WechatFactory

DEFAULT_URI = "ws://localhost:5000/ws"

async def wechat_automation():
    async with WechatFactory.create_factory(DEFAULT_URI,WeChatConfig(
        # 这里可以设置一些配置信息
    )) as factory:
        await factory.initialize()
        wechat_list = factory.client_list
        print(
            f"连接服务器({DEFAULT_URI})共有微信客户端{len(wechat_list)}个:{list(wechat_list.keys())}"
        )
        client: WeChatClient = wechat_list["Alex"] # 得到某个微信客户端，支持多微信
        # 给群 DroidMirror官方技术支持 发送文本消息，并@两个好友
        await client.send_message("DroidMirror官方技术支持","hello world!",at_user=["AI.Net_test","智影工坊"])

def main():
    asyncio.run(wechat_automation())


if __name__ == "__main__":
    main()

```

5. 运行 main.py 文件
```
uv run .\main.py
```

## 🙈 FAQ(问题解答)

我收集了一些常见问题和解答，方便大家快速上手和解决问题，👉 具体请参考：[FAQ](./MD/faq.md)

## 📋 系统要求

- Windows 操作系统,不支持Linux和MacOS;
- .NET 6.0 或更高版本 (注：python SDK 不依赖 .NET)
- **风控风险**：频繁操作可能触发微信风控机制，建议：
   - 使用键鼠模拟器降低风险
   - 控制操作频率
   - 避免短时间内大量操作

## 🎈 关于键鼠模拟器

键鼠模拟器是一类专门的硬件设备，能够模拟物理键盘和鼠标的真实输入。相较于直接调用 PostMessage、SetInput 等 API 进行注入，这类传统软件方式往往会留下可被识别的痕迹，极易被微信等应用检测为自动化行为并引发风控。而键鼠模拟器通过硬件底层发送信号，模拟出的输入和人手操作无异，从而高度还原人类使用方式，在风控安全性和隐蔽性方面具备天然优势。

实际测试表明，在微信某些高敏感操作场景（比如群聊内加好友）下，借助键鼠模拟器能有效降低被风控的概率。需要注意的是，即便是手动操作，部分极端高风险情况下也有可能触发风控。因此，强烈建议在高敏感度和易风控场景优先考虑且规范使用键鼠模拟器，以获得更稳定和安全的自动化体验。

本 SDK 同时支持纯软件自动化以及结合硬件键鼠模拟器的自动化操作，满足不同业务需求和安全等级场景下的使用选择。

关于键鼠模拟器更深度的了解，请参见：[键鼠模拟器](https://github.com/scottfly189/SKSimulator)


## 😊 关于VIP

Wechatauto.SDK分为社区版和VIP版，社区版是完全开源的，VIP版则提供更多的功能和更深入的技术支持。

社区版与VIP版本在代码层面，主要区别在于：VIP版本比社区版本多了20%的API接口，这些接口主要是一些高级功能和扩展能力，旨在为VIP客户提供更简单、更强大的微信自动化能力。

**🎉 VIP 客户可享受以下专属服务保障：**
- 💡 **BUG 优先响应**：出现 Bug 或有新的 Enhancement ，第一时间响应、定位和解决，保障 VIP 项目的稳定运行;
- 🚀 **专属 VIP 私有仓库**：VIP 客户将获专属私有仓库，会不定期提供丰富的应用层扩展与独享内容;
- 🚀 **一对一的专属vip服务**: 这是你加入 VIP 的核心理由,微信自动化能力由 WeChatAuto.SDK 提供深度支持，业务系统由你自由扩展，实现技术与业务的高效分工;

如需升级成为 VIP，或了解 VIP 具体权益和支持方案，👉[请与我联系](https://github.com/scottfly189/scottfly189/blob/main/vip.md)。

> 我这么考虑的：社区版其实可以完成大部分的微信自动化需求，适合大多数用户使用，而如果用到VIP版本，干嘛不请我吃一顿饭以获取更及时更好的技术服务呢？毕竟您对微信自动化开发已经深入到这种程度了，我相信你一顿饭的价值获取一个技术partner是很值得的😊

---

## 🎁 WechatAuto.SDK入门视频

下面的视频以wechatauto.sdk4.x微信最新版来讲解

... 正在完成中


---

## 📝 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 🙏 致谢

在这里感谢那些还在为自由和正义而奋斗的人们🎉🎉

---


## ⚒️ 免责声明

本 SDK 仅供学习和研究使用，请遵守微信使用条款，不得用于任何违法违规用途。使用本 SDK 产生的任何后果由使用者自行承担。

