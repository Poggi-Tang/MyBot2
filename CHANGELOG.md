# Changelog

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
