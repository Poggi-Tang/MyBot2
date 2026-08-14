# Changelog

## 2.7.0 Beta 1 - 2026-08-14

### Added

- Added a Python UIA conversation scanner and message listener with OCR-assisted message analysis and quote-menu control.
- Added a mandatory first-connection conversation initialization scan so group/private metadata is validated on every process start.
- Added one-click NewAPI connection import with project-local defaults for chat, reasoning and image models.
- Added stable MyBot AutomationIDs and a companion easyuiauto Skill for precise UI control.
- Added modular backend, routing, controller and conversation-action service boundaries.

### Changed

- Moved conversation type detection and message listening away from the legacy .NET path to the Python UIA implementation.
- Quote replies now locate the target message, open WeChat's context menu and select the OCR-recognized quote command.
- Automatic conversation recovery waits for initialization and title refresh before restoring listeners or queued work.

### Fixed

- Prevented missing or stale WeChat title controls from silently classifying conversations as private.
- Retried transient conversation switches without consuming unread-message state or losing queued replies.
- Fixed quote and realtime reply failures while WeChat rebuilds the active conversation panel.
- Prevented non-visual creation requests such as writing poems, plans or copy from being routed to image generation.
- Improved rapid-message intake, reference handling, attachment routing and restart behavior.

## 2.6.1 Beta 1 - 2026-08-12

### Changed

- Replaced the redundant toolbar status light with a normal `运行` navigation button.
- The Run button now opens tasks, connection details and tests without changing color for connection or task state.
- Active and queued task state remains visible exclusively through the dynamic segmented task container below the toolbar.

### Fixed

- Removed duplicate yellow/green state signaling from the first navigation button while preserving task-cell colors and automatic container visibility.

## 2.6.0 Beta 1 - 2026-08-12

### Added

- Added a unified extension registry for project-local MCP servers and Skills, including JSON/directory import, removal and enable/disable controls.
- Added switch artwork for extension state controls and project-local synchronization of enabled Skills into the Codex runtime.

### Changed

- Consolidated the feature window into `功能列表 / MCP / Skill`; automatically matched and validated abilities now appear as Skill metadata instead of a separate “快捷能力” concept.
- The Skill table now shows source type, triggers, validation, usage count and runtime state alongside managed project Skills.
- Codex CLI command construction now includes only enabled MCP servers and supports imported command- or URL-based MCP configurations.
- Codex prompts and status text consistently refer to matched Skills.

### Fixed

- Kept feature-page switching as an immediate cached show/hide operation without synchronous registry or window enumeration work.
- Preserved built-in MCP and Skill protection while allowing imported extensions to be removed safely.

## 2.5.0 Beta 1 - 2026-08-12

### Added

- Replaced the monolithic desktop window with a compact six-button toolbar and independent docked windows for status, knowledge, abilities, MCP, Skill and settings.
- Docked windows follow the visible WeChat frame, dynamically hide when WeChat loses focus, restore with the previous page and keep settings exactly aligned to the WeChat height.
- Added project-local MCP and Skill visibility, daily personal workspaces, tray controls, administrator security boundaries and the application-managed Codex CLI extension.
- Added Boson/Higgs voice configuration, voice selection and voice-actor performance planning before synthesis.
- Added project SVG controls for combo boxes and numeric steppers, plus the supplied application and settings artwork.
- Added an About page with product, version, release channel, GitHub project and update controls.

### Changed

- Updated the interface to a compact WeChat-style light theme with transparent labels, multiline persona editing and responsive tool-window docking.
- Page switching now performs only cached window hide/show operations; CLI, memory and Skill refreshes run at initialization or through explicit refresh actions.
- The system tray menu now has visible hover, pressed, disabled and separator states.
- Software update controls now live in About instead of Security Management.

### Fixed

- Removed visible docking gaps caused by Windows invisible frame margins and matched tool-window height to the DWM-visible WeChat frame.
- Fixed foreground visibility behavior across the main WeChat window, WeChat child windows and MyBot tool windows.
- Fixed group mention recognition, duplicate sticker limits, voice-list loading, local voice assets and Codex project-runtime detection.
- Fixed combo-box, spin-box and label background rendering inconsistencies across light surfaces.
- Fixed rapid-message capture, explicit voice routing, automatic Server recovery and cross-process outgoing-message echo suppression.

## 2.4.1 - 2026-08-12

### Added

- The supplied WeChat bubble logo is now used for the application window, taskbar, tray, shortcuts and installer.
- MyBot stays available in the Windows notification area after its window is closed, with actions to restore, restart or close the application completely.
- Installed shortcuts now launch the compiled, console-free `MyBot2.exe` entry point instead of `run.cmd`.

### Fixed

- Existing project-local Codex CLI installations under `tools/codex` are recognized when the new `data/codex/runtime` directory has not been installed yet.
- The compatibility fallback remains restricted to the current MyBot project and never reads a global Codex installation.

## 2.4.0 - 2026-08-12

### Changed

- Codex CLI is now an application-managed extension under System Configuration > Model Configuration and is never bundled in the Windows installer.
- The in-app installer downloads the current Windows x64 package, checksum and Responses proxy from OpenAI's latest official Codex Release.
- CLI API and runtime controls stay disabled until installation completes; all runtime, home, task, session and API state remains project-local.
- Release packages are smaller and no longer require a separate build-time Codex download.

### Fixed

- First-launch installer option application no longer prints localized text through the Windows console code page, preventing startup and CI failures on English Windows hosts.

## 2.3.1 - 2026-08-12

### Fixed

- Manual overwrite installs now detect and stop the running MyBot frontend before replacing application files.
- Installer process shutdown is bounded by a grace period and fails clearly instead of waiting indefinitely.
- First launch now applies pending installer choices before the launcher requires `config.json`.
- Deferred API setup no longer blocks the first application launch.
- Environment checks now accept the configured local WebSocket port instead of requiring port 5177.

## 2.3.0 - 2026-08-12

### Added

- Optional Codex CLI extension with official download, SHA256 verification, project-local runtime and independent API configuration.
- Automatic GitHub Release checks every ten minutes with an in-app update indicator.
- Verified installer download and silent overwrite-update handoff.
- Windows installer design with optional Python runtime, feature SDK resources, reusable abilities and Codex CLI components.
- Automated GitHub Release workflow for installer and checksum assets.

### Changed

- Codex CLI no longer depends on a globally installed executable, global `CODEX_HOME` or the primary chat model configuration.
- Release versions now follow the documented three-level `2.x.x` policy.

## 2.2.0 - 2026-08-12

### Added

- Higgs TTS voice-actor planning with emotional segmentation and performance intensity controls.
- Side-by-side group and private conversation lists.

### Fixed

- Prevented cached group metadata from triggering startup rescans.
- Prevented SDK exact-match search from activating the chat-history button.
