# WeChatAuto4_X integration

This directory contains the WeChatAuto4_X source required by MyBot2. It provides Windows UI Automation and the local WebSocket Server used by the Python desktop application.

Build the Server from the repository root with `setup.cmd`, or directly:

```powershell
.\scripts\build.ps1
```

The output used by MyBot2 is:

```text
WebSocketServer\Server\bin\Debug\net10.0-windows\Server.exe
```

The Server listens on `127.0.0.1:5177` by default. Its source is bundled for repeatable deployment; generated `bin`, `obj`, diagnostics, and operation logs are intentionally excluded.

This SDK component retains the upstream MIT license and copyright notice in `../LICENSE`.
