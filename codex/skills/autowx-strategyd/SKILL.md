---
name: autowx-strategyd
description: Plan and safely execute MyBot WeChat SDK operations through the standalone autowx MCP. Use when a request needs searching AutoWX functions, completing SDK arguments, inspecting call risk, reading WeChat state, or performing an explicitly approved message, contact, group, listener, window, or Moments action.
---

# AutoWX Strategyd

Use the `autowx` MCP as a controlled WeChat SDK boundary. Read [references/mcp-tools.md](references/mcp-tools.md) before the first call.

## Workflow

1. Call `get_connection_status`. Call `connect_gateway` only when disconnected and execution is required.
2. Search with `list_functions`; do not guess function names.
3. Call `get_function_schema` and collect every required argument from the request or current context.
4. Call `plan_function_call` for the exact function and arguments.
5. For read-only calls, execute with `call_sdk_function` after checking the preview.
6. For any reversible, write, or high-risk call, show the target, effect, and risk to the user. Execute only after explicit approval, using the returned one-time token and unchanged arguments.
7. Inspect the returned `ok` and `value`. Do not claim success from a plan or from a failed gateway result.

The MyBot application exclusively owns message-listener lifecycle. Never call listener add, pause, resume, timed-listener, or listening-target mutation functions through autowx. Non-administrator tasks are restricted by the MCP to their originating conversation; do not attempt account-wide reads or another target.

Prefer the least powerful function that completes the request. Never use a batch, deletion, membership, call, forwarding, auto-accept, or Moments operation when a narrower read-only operation is sufficient. Do not retry a write automatically after an ambiguous timeout or error.

If multiple accounts are connected, pass the explicitly selected account. Treat account names, chat content, local paths, API keys, tokens, and returned personal data as private; disclose only what the user requested.
