# autowx MCP tools

The standalone stdio server starts with:

```text
python -m autowx_mcp.server
```

MyBot registers this server for task-bound Codex CLI runs. The MyBot task context limits non-administrator calls to the originating conversation, and listener lifecycle functions remain reserved for the MyBot application.

- `list_functions`: filter the allowlisted SDK catalog by `query`, exact `category`, or exact `risk`.
- `get_function_schema`: return required argument names and catalog risk metadata.
- `plan_function_call`: validate arguments, serialize a redacted gateway preview, and issue a 120-second one-time token for every non-read-only call.
- `get_connection_status`: return the gateway URL and connected account names.
- `connect_gateway`: connect to `AUTOWX_GATEWAY_URL` or `ws://127.0.0.1:5177/ws`. This must establish a real connection; demo mode is rejected.
- `disconnect_gateway`: close the standalone connection.
- `call_sdk_function`: execute an allowlisted function. Non-read-only calls require the exact plan token. Tokens are bound to the function and arguments and are consumed on first use.

`AUTOWX_ACCOUNT` may select a default account. With multiple connected accounts and no default, pass `account` explicitly.

Planning is not approval. Never interpret a confirmation token as user consent; obtain explicit consent after presenting the exact plan.
