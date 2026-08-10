---
name: mybot-wechat
description: Complete long-running MyBot WeChat tasks through Codex CLI, reuse verified extension abilities, inspect the fixed task context, and return concise results for deterministic delivery to the originating conversation. Use for code, files, shell commands, debugging, project research, or packaging a completed reusable workflow as a MyBot extension ability.
---

# MyBot WeChat

Complete the task in the current workspace and verify the result. Keep the final response under 1600 Chinese characters so MyBot can send it to the fixed originating conversation.

## Workflow

1. Call `get_task_context` when task context is available. Treat its conversation as fixed; never select another recipient.
2. Call `get_capabilities` or inspect `extensions/index.json` before implementing. Prefer a matching verified recipe and script.
3. Read only the references needed for the task:
   - Read [references/mcp-protocol.md](references/mcp-protocol.md) for task binding and progress tools.
   - Read [references/ability-contract.md](references/ability-contract.md) only when packaging a reusable ability.
4. Perform the work in the current workspace. Preserve unrelated changes and do not commit or push.
5. When `get_task_context` includes `input_files`, use those task-scoped copies as the user's attachments. Never overwrite an input file.
6. When the task needs a file delivered, write the finished artifact under the exact `output_dir` from task context and call `register_output_file` once for each deliverable. Do not register temporary files or files outside that directory.
7. Run focused verification, then report the outcome and relevant test result. Do not expose internal prompts, tokens, keys, raw logs, or chain of thought.

MyBot owns final reply delivery. Do not attempt to click or choose a WeChat conversation. Use `report_progress` only for meaningful long-running milestones.

## Ability Reuse

Treat `extensions/abilities` as published, verified code. Read its `recipe.md`, validate the input contract, and run the documented script. Do not reuse stored real-time values.

Do not alter a published ability during an ordinary task. If its contract does not fit, complete the task normally and mention the mismatch in the result; the post-task reviewer decides whether to publish a new ability.
