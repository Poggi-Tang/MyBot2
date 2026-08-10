# Extension Ability Contract

Create an ability candidate only inside the current candidate workspace. A publishable candidate contains:

```text
manifest.json
recipe.md
scripts/<ability>.py
tests/test_<ability>.py
```

`manifest.json` must contain:

```json
{
  "reusable": true,
  "id": "lowercase-slug",
  "name": "short name",
  "description": "stable reusable purpose",
  "triggers": ["natural language trigger"]
}
```

Requirements:

- Parameterize every varying input with `argparse`.
- Use only Python standard library unless the recipe declares a project dependency.
- Keep output deterministic and machine-readable where practical.
- Never include contact names, conversations, raw messages, absolute user paths, credentials, API keys, or captured real-time values.
- Do not make tests access the network, WeChat, or external services.
- Document applicability, parameters, command, output, dependencies, and failure behavior in `recipe.md`.
- Run `python -m compileall -q scripts tests` and `python -m unittest discover -s tests -p "test_*.py"`.

The host independently repeats validation, scans for secrets and conversation-specific terms, and refuses overwrite of an existing published ability.
