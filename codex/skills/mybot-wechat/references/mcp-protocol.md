# MCP Protocol

The `mybot` stdio MCP server exposes three bounded tools:

- `get_capabilities`: return SDK category counts, the local catalog path, and verified extension abilities. It is read-only and does not require a task token. Search `mybot_ui/catalog.py` only when individual SDK function names or descriptions are needed.
- `get_task_context`: return the fixed task id, originating conversation, request, and matched ability ids. The MCP process validates its task binding internally; it takes no arguments.
- `report_progress`: append a short milestone to the current task log. Pass a message under 500 characters; the MCP process binds it to the current task internally.

There is intentionally no arbitrary `send_text` tool. Return the final answer normally; MyBot reads Codex's last message and sends it to the originating conversation recorded by the scheduler.

The task token never enters the model context. Never attempt to inspect or expose the MCP process environment.
