# MyBot UI Workflows

Always run `list_windows`, find by exact `automation_id`, call `check_control_visibility`, then interact only when `is_interactable=true`. Re-find controls after navigation or refresh.

## Window Navigation

MyBot's compact toolbar is `MyBot.MainWindow`. Open the required docked window with:

- Run: `MyBot.MainWindow.nav_run_button`
- Knowledge: `MyBot.MainWindow.nav_knowledge_button`
- Features: `MyBot.MainWindow.nav_features_button`
- Settings: `MyBot.MainWindow.nav_settings_button`

Bring WeChat to the foreground first when MyBot is hidden. A selected tool window docks against WeChat and may appear on either side depending on available screen space.

## Automatic Chat

1. Open Settings and select the conversation-configuration tab.
2. Refresh targets if needed, then inspect `MyBot.MainWindow.auto_chat_group_targets` and `MyBot.MainWindow.auto_chat_private_targets`.
3. Select only explicitly approved conversations.
4. Start with `MyBot.MainWindow.auto_chat_start`; stop with `MyBot.MainWindow.auto_chat_stop`.
5. For the compact shortcut, use `MyBot.MainWindow.dock_auto_chat_toggle` and verify its checked/state result.

Do not toggle repeatedly while the connection or listener is changing state.

## Account And Server

1. Open Settings.
2. Select `MyBot.MainWindow.account_combo` and verify `MyBot.MainWindow.uri_input` when connecting.
3. Use `MyBot.MainWindow.connect_button` to connect or disconnect, then read the visible connection status.
4. Use `MyBot.MainWindow.restart_server_button` only after explicit approval. Re-list windows and wait for reconnection.
5. Use `MyBot.MainWindow.restart_app_button` only after explicit approval. All prior UIA handles become invalid.

## UIA Failure Recovery

1. Stop automatic chat and disconnect MyBot's automation channel.
2. Do not close, restart, terminate, or sign out WeChat. Preserve the current WeChat process and login state.
3. Do not use `ClickNotifyIcon` repeatedly as a repair loop and do not issue more SDK commands while the circuit is open.
4. Wait for the user to confirm that WeChat can be clicked and conversations can be switched manually.
5. Reconnect MyBot manually, refresh conversations, and explicitly select the conversations for this run. Never restore a previous takeover automatically.

## Memory And Daily Workspaces

1. Open Knowledge.
2. Search through `MyBot.MainWindow.memory_search` and select a person in `MyBot.MainWindow.memory_people`.
3. Edit the named profile fields and save with `MyBot.MainWindow.memory_save_button`.
4. Delete only with explicit approval through `MyBot.MainWindow.memory_delete_button`, then handle the confirmation dialog.
5. Choose a date in `MyBot.MainWindow.daily_date_combo`; inspect messages in `MyBot.MainWindow.daily_message_table` and files in `MyBot.MainWindow.daily_file_list`.
6. Open the workspace or selected file with the corresponding `daily_open_*` button.

## MCP And Skills

1. Open Features and switch the inner tab to MCP or Skill through `MyBot.MainWindow.feature_tabs` / its tab bar.
2. Inspect `MyBot.MainWindow.mcp_table` or `MyBot.MainWindow.skill_table`.
3. Dynamic enable controls use stable IDs based on extension IDs:
   - `MyBot.MainWindow.mcp_<extension_id>_toggle`
   - `MyBot.MainWindow.skill_<extension_id>_toggle`
4. Re-find a toggle after refreshing the table.
5. Import, remove, enable, or disable only the requested extension. Removal requires explicit authorization and confirmation.

## Model, CLI, Voice, Security, And Updates

1. Open Settings and navigate the settings tab bar.
2. Fill primary/backup/image model fields by their exact named IDs from `automation-ids.md`.
3. Import NewAPI JSON through the import button; in the dialog use:
   - `MyBot.NewApiImportDialog.payload`
   - `MyBot.NewApiImportDialog.show_payload`
   - `MyBot.NewApiImportDialog.configure_button`
4. Never read back or disclose password-mode API key fields.
5. Configure CLI through `codex_*`, voice through `voice_*`, and security through `security_*` controls.
6. Treat administrator/security changes as sensitive writes requiring explicit authorization.
7. Check updates with `MyBot.MainWindow.check_update_button`; downloading/installing an update is an external write and restart operation.

## Reply Policy

Open the reply-policy dialog from Settings. Edit named `policy_*` and `profile_*` controls, then save using `MyBot.ReplyPolicyDialog.save_all_button`. Use `MyBot.ReplyPolicyDialog.cancel_button` to discard. Do not infer or overwrite existing persona/profile content without a specific user request.

## Testing

1. Open Run and the test tab.
2. Prefer the safe or simulated-message test for non-live verification.
3. For simulated conversation tests, use `test_target`, `test_message`, and `test_conversation_scenario`; the target must already be an approved managed conversation.
4. Run full/live actions only when explicitly requested. Never publish Moments or send a live message merely to test navigation.
5. Read `MyBot.MainWindow.test_table` and progress/status fields to confirm the result.

## Tray

Find the Shell-hosted icon by tooltip `MyBot2`. Right-click once. Menu properties are marked as:

- `MyBot.Tray.menu`
- `MyBot.Tray.show_action`
- `MyBot.Tray.restart_action`
- `MyBot.Tray.close_action`

Some Windows UIA providers expose Shell menu items by label rather than the QAction property. In that case, use these exact labels only after confirming the `MyBot2` tray icon opened the menu.
