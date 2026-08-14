---
name: mybot-easyuiauto
description: Control and inspect the MyBot Windows desktop application through the Easy UIAuto MCP using stable MyBot-prefixed AutomationIds. Use when locating MyBot controls, navigating its docked windows, configuring chat/models/security, managing memory/MCP/Skills, starting or stopping automatic chat, running tests, restarting components, or auditing MyBot UI automation coverage.
---

# MyBot Easy UIAuto

Control MyBot through exact AutomationIds. Avoid coordinate clicks whenever UI Automation exposes the target.

## Core Procedure

1. Activate WeChat when the MyBot dock is hidden; MyBot follows WeChat foreground visibility.
2. Call Easy UIAuto `list_windows` and identify the visible MyBot window.
3. Call `find_control` with the exact `automation_id` from [references/automation-ids.md](references/automation-ids.md).
4. Call `check_control_visibility` immediately before interaction.
5. Interact only when `is_interactable=true`. Re-find the control after switching a page, opening a dialog, refreshing a table, or restarting.
6. Read back the control state or resulting status before claiming success.

Use exact AutomationId matching. Do not select a control only by label when an ID exists. Do not cache runtime handles across page refreshes.

## Choose A Workflow

Read [references/workflows.md](references/workflows.md) for the requested MyBot operation. Read [references/automation-ids.md](references/automation-ids.md) only for exact IDs or inventory lookup.

Run `python scripts/audit_automation_ids.py --check` from this Skill directory when UI automation coverage may have changed. Run it with `--write` after verified UI changes to regenerate the inventory reference.

## Safety

- Treat API keys, real file paths, account names, chat content, memory, and administrator settings as private.
- Never reveal a password-mode field value through UIA.
- Require explicit authorization before sending a message, publishing Moments, deleting memory, removing MCP/Skills, restarting MyBot/Server, closing MyBot, or changing security/administrator settings.
- Keep live message and Moments writes limited to the user-approved test conversation/account.
- Prefer a dry inspection or MyBot's simulated-message test when the user asks only to verify UI control.
- Do not repeatedly click a control while waiting. Check the resulting state once, then wait or diagnose.
- UIA recovery must never close or restart WeChat, terminate `Weixin.exe`/`WeChat.exe`, sign out the account, or otherwise disturb its login state. Stop MyBot automation and disconnect its Server channel; reconnect only after the user confirms WeChat is manually operable.

## Platform Boundary

The notification-area icon is hosted by Windows Explorer, so Qt cannot inject a MyBot AutomationId into the tray icon itself. Locate that icon through the Windows Shell by its `MyBot2` tooltip. Once the menu opens, use the MyBot-marked menu/action identifiers documented in the reference where the UIA provider exposes them.
